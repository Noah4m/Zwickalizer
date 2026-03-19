import json
import sys
import types
import unittest
from pathlib import Path


openai_stub = types.ModuleType("openai")


class APIError(Exception):
    pass


class RateLimitError(APIError):
    pass


class AuthenticationError(APIError):
    pass


class OpenAI:
    def __init__(self, *args, **kwargs):
        pass


openai_stub.APIError = APIError
openai_stub.RateLimitError = RateLimitError
openai_stub.AuthenticationError = AuthenticationError
openai_stub.OpenAI = OpenAI
sys.modules.setdefault("openai", openai_stub)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_agent import MCPEnabledChatAgent, looks_incomplete_after_tools


class FakeFunction:
    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = json.dumps(arguments)


class FakeToolCall:
    def __init__(self, tool_call_id: str, name: str, arguments: dict):
        self.id = tool_call_id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        payload = {"role": "assistant"}
        if self.content is not None:
            payload["content"] = self.content
        if self.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in self.tool_calls
            ]
        return payload


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, message):
        self.choices = [FakeChoice(message)]


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.responses:
            raise AssertionError("No fake responses remaining.")
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = types.SimpleNamespace(completions=FakeCompletions(responses))


class FakeToolbox:
    def __init__(self, result, tool_name="db_find_tests", description="Find tests for a customer and test type."):
        self.result = result
        self.calls = []
        self.tool_name = tool_name
        self.description = description

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def openai_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": self.tool_name,
                    "description": self.description,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    def call(self, public_name, arguments):
        self.calls.append((public_name, arguments))
        return self.result


class ChatAgentTests(unittest.TestCase):
    def test_retries_when_post_tool_reply_is_only_a_progress_message(self):
        placeholder = (
            'I will now retrieve all tensile test data for "Company_3" from the MCP database. '
            "Please hold on a moment."
        )
        final_answer = "I found 2 tensile tests for Company_3. The most recent test was run on 2026-02-14."

        responses = [
            FakeResponse(
                FakeMessage(
                    placeholder,
                    tool_calls=[
                        FakeToolCall(
                            "call_1",
                            "db_find_tests",
                            {"customer": "Company_3", "testType": "tensile"},
                        )
                    ],
                )
            ),
            FakeResponse(FakeMessage(placeholder)),
            FakeResponse(FakeMessage(final_answer)),
        ]
        client = FakeClient(responses)
        toolbox = FakeToolbox(
            json.dumps(
                {
                    "tests": [
                        {"testId": "T-100", "customer": "Company_3", "testType": "tensile"},
                        {"testId": "T-101", "customer": "Company_3", "testType": "tensile"},
                    ]
                }
            )
        )
        agent = MCPEnabledChatAgent(
            api_key="test-key",
            model="test-model",
            mcp_server_root="/tmp/mcp",
            client=client,
            toolbox_factory=lambda _: toolbox,
        )

        answer = agent.answer("all tests of type tensile", "engineer", [])

        self.assertEqual(answer, final_answer)
        self.assertEqual(
            toolbox.calls,
            [("db_find_tests", {"customer": "Company_3", "testType": "tensile"})],
        )
        self.assertEqual(len(client.chat.completions.requests), 3)

        second_request_messages = client.chat.completions.requests[1]["messages"]
        tool_message = next(message for message in second_request_messages if message["role"] == "tool")
        self.assertIn('"result": {"tests": [', tool_message["content"])
        self.assertNotIn('\\"tests\\"', tool_message["content"])

    def test_incomplete_message_detector_is_conservative(self):
        self.assertTrue(looks_incomplete_after_tools("Please hold on while I retrieve the data."))
        self.assertFalse(looks_incomplete_after_tools("No matching tensile tests were found for Company_3."))

    def test_value_array_tool_sends_only_summary_to_model_and_plot_to_client(self):
        final_answer = "I plotted 2 value arrays for the requested test. Result 1 ranges from 0 to 10 and Result 2 ranges from 5 to 15."
        responses = [
            FakeResponse(
                FakeMessage(
                    "Let me retrieve and plot the stored value arrays.",
                    tool_calls=[
                        FakeToolCall(
                            "call_1",
                            "db_get_test_value_arrays",
                            {"test_id": "T-200", "values_limit": 4},
                        )
                    ],
                )
            ),
            FakeResponse(FakeMessage(final_answer)),
        ]
        client = FakeClient(responses)
        toolbox = FakeToolbox(
            json.dumps(
                {
                    "testId": "T-200",
                    "strict": True,
                    "count": 2,
                    "valuesLimit": 4,
                    "valueArrays": [[0, 10, float("nan"), 4], [5, 15, 8, 7]],
                }
            ),
            tool_name="db_get_test_value_arrays",
            description="Return value arrays for a test.",
        )
        agent = MCPEnabledChatAgent(
            api_key="test-key",
            model="test-model",
            mcp_server_root="/tmp/mcp",
            client=client,
            toolbox_factory=lambda _: toolbox,
        )

        response = agent.respond("plot the value arrays for test T-200", "engineer", [])

        self.assertEqual(response.answer, final_answer)
        self.assertEqual(len(response.analysis), 2)
        self.assertEqual(response.analysis[1]["type"], "chart")
        self.assertEqual(len(response.analysis[1]["data"]["series"]), 2)
        self.assertEqual(response.analysis[1]["data"]["points"][2]["series_1"], None)
        self.assertEqual(response.tool_calls[0]["result"]["plotShownToUser"], True)
        self.assertEqual(response.tool_calls[0]["result"]["valueArrays"][0][2], None)
        self.assertEqual(response.tool_calls[0]["result"]["seriesSummaries"][0]["min"], 0.0)
        self.assertEqual(response.tool_calls[0]["result"]["seriesSummaries"][1]["max"], 15.0)

        second_request_messages = client.chat.completions.requests[1]["messages"]
        tool_message = next(message for message in second_request_messages if message["role"] == "tool")
        self.assertIn('"plotShownToUser": true', tool_message["content"])
        self.assertIn('"seriesSummaries"', tool_message["content"])
        self.assertNotIn('"valueArrays"', tool_message["content"])
        self.assertNotIn("NaN", tool_message["content"])


if __name__ == "__main__":
    unittest.main()
