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

from chat_agent import MAX_PLOT_POINTS, MCPEnabledChatAgent


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
    def test_forces_final_answer_turn_after_tool_results(self):
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
        self.assertEqual(len(client.chat.completions.requests), 2)

        second_request_messages = client.chat.completions.requests[1]["messages"]
        tool_message = next(message for message in second_request_messages if message["role"] == "tool")
        self.assertIn('"result": {"tests": [', tool_message["content"])
        self.assertNotIn('\\"tests\\"', tool_message["content"])
        self.assertNotIn("tools", client.chat.completions.requests[1])
        self.assertEqual(second_request_messages[-1]["role"], "system")
        self.assertIn("Answer the user's latest request now", second_request_messages[-1]["content"])

    def test_value_columns_tool_sends_only_summary_to_model_and_plot_values_to_client(self):
        final_answer = "I plotted the returned force curves. The first series runs from 1 to 4 and the second from 2 to 5."
        responses = [
            FakeResponse(
                FakeMessage(
                    "Let me retrieve the value columns and plot them.",
                    tool_calls=[
                        FakeToolCall(
                            "call_1",
                            "db_get_test_value_columns",
                            {"test_id": "T-300", "values_limit": 4},
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
                    "testId": "T-300",
                    "strict": True,
                    "includeValues": True,
                    "count": 2,
                    "valuesLimit": 4,
                    "valueColumns": [
                        {
                            "name": "Force",
                            "childId": "{TABLE}.{COL-1}_Value",
                            "sourceDocumentId": "doc-1",
                            "values": [1, 4, float("nan"), 3],
                        },
                        {
                            "name": "Force",
                            "childId": "{TABLE}.{COL-2}_Value",
                            "sourceDocumentId": "doc-2",
                            "duplicate": True,
                            "values": [2, 5, 4, 3],
                        },
                    ],
                }
            ),
            tool_name="db_get_test_value_columns",
            description="Return value columns for a test.",
        )
        agent = MCPEnabledChatAgent(
            api_key="test-key",
            model="test-model",
            mcp_server_root="/tmp/mcp",
            client=client,
            toolbox_factory=lambda _: toolbox,
        )

        response = agent.respond("plot the value columns for test T-300", "engineer", [])

        self.assertEqual(response.answer, final_answer)
        self.assertTrue(response.tool_calls[0]["result"]["plotShownToUser"])
        self.assertEqual(response.tool_calls[0]["result"]["valueColumns"][0]["sampledValues"][2], None)
        self.assertEqual(response.tool_calls[0]["result"]["valueColumns"][0]["sampledIndices"], [0, 1, 2, 3])
        self.assertEqual(response.tool_calls[0]["result"]["seriesSummaries"][0]["min"], 1.0)
        self.assertEqual(response.tool_calls[0]["result"]["seriesSummaries"][1]["max"], 5.0)
        self.assertEqual(response.tool_calls[0]["result"]["seriesSummaries"][0]["mean"], 2.6666666666666665)

        tool_message = next(
            message
            for message in client.chat.completions.requests[1]["messages"]
            if message["role"] == "tool"
        )
        self.assertIn('"seriesSummaries"', tool_message["content"])
        self.assertNotIn('"sampledValues"', tool_message["content"])

        second_request_messages = client.chat.completions.requests[1]["messages"]
        tool_message = next(message for message in second_request_messages if message["role"] == "tool")
        self.assertIn('"plotShownToUser": true', tool_message["content"])
        self.assertIn('"seriesSummaries"', tool_message["content"])
        self.assertNotIn('"sampledValues"', tool_message["content"])
        self.assertNotIn("NaN", tool_message["content"])

    def test_large_value_columns_tool_result_is_sampled_for_client(self):
        large_values = list(range(MAX_PLOT_POINTS + 200))
        final_answer = "I plotted the sampled value column."
        responses = [
            FakeResponse(
                FakeMessage(
                    "Let me retrieve the value column.",
                    tool_calls=[
                        FakeToolCall(
                            "call_1",
                            "db_get_test_value_columns",
                            {"test_id": "T-400", "value_column_index": 0},
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
                    "testId": "T-400",
                    "strict": True,
                    "includeValues": True,
                    "count": 1,
                    "valueColumns": [
                        {
                            "name": "Force",
                            "childId": "{TABLE}.{COL-1}_Value",
                            "sourceDocumentId": "doc-1",
                            "values": large_values,
                        }
                    ],
                }
            ),
            tool_name="db_get_test_value_columns",
            description="Return value columns for a test.",
        )
        agent = MCPEnabledChatAgent(
            api_key="test-key",
            model="test-model",
            mcp_server_root="/tmp/mcp",
            client=client,
            toolbox_factory=lambda _: toolbox,
        )

        response = agent.respond("plot the first value column for test T-400", "engineer", [])

        series = response.tool_calls[0]["result"]["valueColumns"][0]
        summary = response.tool_calls[0]["result"]["seriesSummaries"][0]

        self.assertEqual(response.answer, final_answer)
        self.assertLessEqual(len(series["sampledValues"]), MAX_PLOT_POINTS + 1)
        self.assertEqual(series["sampledIndices"][0], 0)
        self.assertEqual(series["sampledIndices"][-1], len(large_values) - 1)
        self.assertTrue(summary["sampledDown"])
        self.assertEqual(summary["points"], len(large_values))

    def test_compare_two_tests_tool_adds_test_ids_to_series_labels(self):
        final_answer = "I compared the two force curves."
        responses = [
            FakeResponse(
                FakeMessage(
                    "Let me compare the two tests.",
                    tool_calls=[
                        FakeToolCall(
                            "call_1",
                            "db_compare_two_tests",
                            {
                                "test_id_1": "{T-500-A}",
                                "test_id_2": "{T-500-B}",
                                "value_column_index": 0,
                            },
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
                    "testIds": ["{T-500-A}", "{T-500-B}"],
                    "strict": True,
                    "includeValues": True,
                    "count": 2,
                    "valueColumnIndex": 0,
                    "valueColumns": [
                        {
                            "testId": "{T-500-A}",
                            "name": "Force",
                            "childId": "{TABLE-A}.{COL-A}_Value",
                            "sourceDocumentId": "doc-a",
                            "values": [1, 2, 3],
                        },
                        {
                            "testId": "{T-500-B}",
                            "name": "Force",
                            "childId": "{TABLE-B}.{COL-B}_Value",
                            "sourceDocumentId": "doc-b",
                            "values": [2, 3, 4],
                        },
                    ],
                }
            ),
            tool_name="db_compare_two_tests",
            description="Return value columns for two tests in one comparison.",
        )
        agent = MCPEnabledChatAgent(
            api_key="test-key",
            model="test-model",
            mcp_server_root="/tmp/mcp",
            client=client,
            toolbox_factory=lambda _: toolbox,
        )

        response = agent.respond("compare the first force curves", "engineer", [])

        self.assertEqual(response.answer, final_answer)
        self.assertEqual(
            response.tool_calls[0]["result"]["seriesSummaries"][0]["label"],
            "Force ({T-500-A})",
        )
        self.assertEqual(
            response.tool_calls[0]["result"]["seriesSummaries"][1]["label"],
            "Force ({T-500-B})",
        )
        self.assertEqual(
            response.tool_calls[0]["result"]["testIds"],
            ["{T-500-A}", "{T-500-B}"],
        )

    def test_compare_two_tests_tool_without_index_still_summarizes_two_curves(self):
        final_answer = "I compared the first curves."
        responses = [
            FakeResponse(
                FakeMessage(
                    "Let me compare the two tests.",
                    tool_calls=[
                        FakeToolCall(
                            "call_1",
                            "db_compare_two_tests",
                            {
                                "test_id_1": "{T-501-A}",
                                "test_id_2": "{T-501-B}",
                            },
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
                    "testIds": ["{T-501-A}", "{T-501-B}"],
                    "strict": True,
                    "includeValues": True,
                    "count": 2,
                    "valueColumnIndex": 0,
                    "valueColumns": [
                        {
                            "testId": "{T-501-A}",
                            "name": "Force",
                            "sourceDocumentId": "doc-a",
                            "values": [1, 2],
                        },
                        {
                            "testId": "{T-501-B}",
                            "name": "Force",
                            "sourceDocumentId": "doc-b",
                            "values": [2, 3],
                        },
                    ],
                }
            ),
            tool_name="db_compare_two_tests",
            description="Return one value column for two tests in one comparison.",
        )
        agent = MCPEnabledChatAgent(
            api_key="test-key",
            model="test-model",
            mcp_server_root="/tmp/mcp",
            client=client,
            toolbox_factory=lambda _: toolbox,
        )

        response = agent.respond("compare the two tests", "engineer", [])

        self.assertEqual(response.answer, final_answer)
        self.assertEqual(len(response.tool_calls[0]["result"]["seriesSummaries"]), 2)
        self.assertEqual(response.tool_calls[0]["result"]["valueColumnIndex"], 0)


if __name__ == "__main__":
    unittest.main()
