# LLM orchestration layer: builds prompts, calls OpenAI, and runs MCP tools when needed.
import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, List

import openai
from openai import OpenAI

from mcp_client import MCPToolbox


logger = logging.getLogger("uvicorn.error")


SYSTEM_PROMPT = """You are MatAI, a concise and practical assistant.
Answer directly and keep responses clear.
Use tools only when they are genuinely needed.
If the user asks for general knowledge or casual conversation, answer without using tools.
If the user asks about stored test data, materials data, measurements, trends, or records, use the available MCP tools.
Do not invent tool results.
IMPORTANT: Only answer once the question is fully answered!!!
"""


def audience_instruction(role: str | None) -> str:
    if role == "executive":
        return (
            "Answer for an executive audience. Focus on the takeaway, risk, and next action. "
            "Keep technical detail to a minimum."
        )
    return (
        "Answer for an engineering audience. Be concrete about findings, relevant fields, and "
        "technical implications."
    )


def format_history(history: List[dict]) -> str:
    lines: list[str] = []
    for item in history:
        role = item.get("role", "user")
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        speaker = "Assistant" if role == "assistant" else "User"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines) if lines else "No prior conversation."


def extract_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""

    message = getattr(choices[0], "message", None)
    if message is None:
        return ""

    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
                    elif isinstance(text, dict) and isinstance(text.get("value"), str):
                        text_parts.append(text["value"])
                elif isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
            elif hasattr(item, "text") and isinstance(item.text, str):
                text_parts.append(item.text)
        return "\n".join(part.strip() for part in text_parts if part and part.strip())
    return ""


def function_call_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments

    if isinstance(arguments, str):
        try:
            loaded = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    return {}


def format_model_error(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, openai.RateLimitError):
        return (
            "The OpenAI API quota is currently exhausted for this project, so I cannot generate a reply right now. "
            "Please wait and try again later, or switch to a different model/key with available quota."
        )
    if isinstance(exc, openai.AuthenticationError):
        return "The OpenAI API key was rejected. Check the key in your `.env` file and try again."
    return f"Model error: {message}"


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize_json_value(item) for key, item in value.items()}
    return value


def tool_result_payload(result: str) -> dict[str, Any]:
    try:
        parsed = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        parsed = None

    if parsed is not None:
        return {"result": sanitize_json_value(parsed)}
    return {"result_text": result}


@dataclass
class ChatAgentResponse:
    answer: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    analysis: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolExecutionResult:
    model_payload: dict[str, Any]
    client_result: Any = None
    analysis: list[dict[str, Any]] = field(default_factory=list)


def looks_incomplete_after_tools(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if not normalized:
        return True

    incomplete_markers = (
        "please hold on",
        "one moment",
        "please wait",
        "i will now retrieve",
        "i'll now retrieve",
        "i will retrieve",
        "i'll retrieve",
        "let me retrieve",
        "fetching the data",
        "retrieving the data",
    )
    return any(marker in normalized for marker in incomplete_markers)


def _safe_numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return numeric


def _format_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6g}"


def summarize_value_arrays_tool(arguments: dict[str, Any], result: str) -> ToolExecutionResult:
    payload = tool_result_payload(result)
    parsed_result = payload.get("result")
    if not isinstance(parsed_result, dict):
        return ToolExecutionResult(model_payload=payload, client_result=parsed_result)

    value_arrays = parsed_result.get("valueArrays")
    if not isinstance(value_arrays, list):
        return ToolExecutionResult(model_payload=payload, client_result=parsed_result)

    series_summaries: list[dict[str, Any]] = []
    plotted_arrays: list[list[float | None]] = []
    longest_series = 0

    for index, raw_array in enumerate(value_arrays):
        values = raw_array if isinstance(raw_array, list) else []
        plotted_values = [_safe_numeric(value) for value in values]
        finite_values = [value for value in plotted_values if value is not None]
        label = f"Result {index + 1}"

        series_summaries.append(
            {
                "label": label,
                "points": len(values),
                "finitePoints": len(finite_values),
                "missingPoints": len(values) - len(finite_values),
                "min": min(finite_values) if finite_values else None,
                "max": max(finite_values) if finite_values else None,
            }
        )
        plotted_arrays.append(plotted_values)
        longest_series = max(longest_series, len(values))

    test_id = parsed_result.get("testId") or arguments.get("test_id")
    strict = bool(parsed_result.get("strict", arguments.get("strict", True)))
    values_limit = parsed_result.get("valuesLimit", arguments.get("values_limit"))

    summarized_result = {
        "testId": test_id,
        "strict": strict,
        "count": parsed_result.get("count", len(series_summaries)),
        "valuesLimit": values_limit,
        "plotShownToUser": True,
        "note": (
            "A line plot of the returned value arrays is already shown to the user. "
            "Raw arrays are intentionally omitted from model context to keep the prompt small."
        ),
        "seriesSummaries": [
            {
                **summary,
                "minText": _format_value(summary["min"]),
                "maxText": _format_value(summary["max"]),
            }
            for summary in series_summaries
        ],
    }
    client_result = {
        **summarized_result,
        "valueArrays": plotted_arrays,
    }
    return ToolExecutionResult(
        model_payload={"result": summarized_result},
        client_result=client_result,
        analysis=[],
    )


def summarize_value_columns_tool(arguments: dict[str, Any], result: str) -> ToolExecutionResult:
    payload = tool_result_payload(result)
    parsed_result = payload.get("result")
    if not isinstance(parsed_result, dict):
        return ToolExecutionResult(model_payload=payload, client_result=parsed_result)

    raw_value_columns = parsed_result.get("valueColumns")
    if not isinstance(raw_value_columns, list):
        return ToolExecutionResult(model_payload=payload, client_result=parsed_result)

    series_summaries: list[dict[str, Any]] = []
    client_value_columns: list[dict[str, Any]] = []

    for index, raw_column in enumerate(raw_value_columns):
        column = raw_column if isinstance(raw_column, dict) else {}
        values = column.get("values")
        if not isinstance(values, list):
            client_value_columns.append(sanitize_json_value(column))
            continue

        plotted_values = [_safe_numeric(value) for value in values]
        finite_values = [value for value in plotted_values if value is not None]
        name = column.get("name")
        source_document_id = column.get("sourceDocumentId")

        if isinstance(name, str) and name.strip():
            label = name.strip()
        else:
            label = f"Value column {index + 1}"

        if column.get("duplicate") and isinstance(source_document_id, str) and source_document_id:
            label = f"{label} ({source_document_id})"

        series_summaries.append(
            {
                "label": label,
                "name": name,
                "childId": column.get("childId"),
                "sourceDocumentId": source_document_id,
                "points": len(values),
                "finitePoints": len(finite_values),
                "missingPoints": len(values) - len(finite_values),
                "min": min(finite_values) if finite_values else None,
                "max": max(finite_values) if finite_values else None,
            }
        )
        client_value_columns.append(
            sanitize_json_value(
                {
                    **column,
                    "values": plotted_values,
                }
            )
        )

    if not any(isinstance(column.get("values"), list) for column in client_value_columns):
        return ToolExecutionResult(model_payload=payload, client_result=parsed_result)

    strict = bool(parsed_result.get("strict", arguments.get("strict", True)))
    include_values = bool(parsed_result.get("includeValues", arguments.get("include_values", False)))
    values_limit = parsed_result.get("valuesLimit", arguments.get("values_limit"))
    test_id = parsed_result.get("testId") or arguments.get("test_id")

    summarized_result = {
        "testId": test_id,
        "strict": strict,
        "includeValues": include_values,
        "count": parsed_result.get("count", len(client_value_columns)),
        "valuesLimit": values_limit,
        "plotShownToUser": include_values,
        "note": (
            "If values were requested, a line plot of the returned value columns is already shown to the user. "
            "Raw values are intentionally omitted from model context to keep the prompt small."
        ),
        "seriesSummaries": [
            {
                **summary,
                "minText": _format_value(summary["min"]),
                "maxText": _format_value(summary["max"]),
            }
            for summary in series_summaries
        ],
        "valueColumns": [
            {
                key: value
                for key, value in sanitize_json_value(column).items()
                if key != "values"
            }
            for column in client_value_columns
        ],
    }
    client_result = {
        **summarized_result,
        "valueColumns": client_value_columns,
    }
    return ToolExecutionResult(
        model_payload={"result": summarized_result},
        client_result=client_result,
        analysis=[],
    )


def execute_tool_for_chat(name: str, arguments: dict[str, Any], result: str) -> ToolExecutionResult:
    if name == "db_get_test_value_arrays":
        return summarize_value_arrays_tool(arguments, result)
    if name == "db_get_test_value_columns":
        return summarize_value_columns_tool(arguments, result)
    payload = tool_result_payload(result)
    return ToolExecutionResult(
        model_payload=payload,
        client_result=payload.get("result") or payload.get("result_text"),
    )


class MCPEnabledChatAgent:
    def __init__(
        self,
        api_key: str,
        model: str,
        mcp_server_root: str,
        client: Any | None = None,
        toolbox_factory: Callable[[str], MCPToolbox] = MCPToolbox,
    ):
        self.client = client or OpenAI(api_key=api_key)
        self.model = model
        self.mcp_server_root = mcp_server_root
        self.toolbox_factory = toolbox_factory

    def _completion(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
        }
        if tools:
            request["tools"] = tools
        return self.client.chat.completions.create(**request)

    def respond(self, message: str, role: str | None, history: List[dict]) -> ChatAgentResponse:
        prompt = f"""
System instructions:
{SYSTEM_PROMPT.strip()}

Audience instructions:
{audience_instruction(role)}

Conversation history:
{format_history(history)}

Latest user question:
{message}
""".strip()

        base_messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        fallback_instruction = (
            "\n\nTool status:\n"
            "If external tools are unavailable, answer general questions normally. "
            "If the user asks for data that requires tools, explain that the tools are currently unavailable."
        )

        try:
            with self.toolbox_factory(self.mcp_server_root) as toolbox:
                tools = toolbox.openai_tools()
                messages: list[dict[str, Any]] = list(base_messages)
                used_tool = False
                tool_calls_for_client: list[dict[str, Any]] = []
                analysis_for_client: list[dict[str, Any]] = []

                for _ in range(6):
                    response = self._completion(messages, tools)
                    choice = response.choices[0] if response.choices else None
                    assistant_message = getattr(choice, "message", None)

                    if assistant_message is None:
                        return ChatAgentResponse(answer="I could not generate a response.")

                    tool_calls = list(getattr(assistant_message, "tool_calls", None) or [])
                    assistant_payload = assistant_message.model_dump(exclude_none=True)
                    assistant_payload.setdefault("role", "assistant")
                    messages.append(assistant_payload)

                    if not tool_calls:
                        final_text = extract_text(response)
                        if used_tool and looks_incomplete_after_tools(final_text):
                            logger.warning(
                                "Model returned an incomplete post-tool answer; forcing one more completion turn"
                            )
                            messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "You already have the tool results. Answer the user's request now. "
                                        "Do not say that you will retrieve data or ask the user to wait. "
                                        "If no matching records were found, say that explicitly."
                                    ),
                                }
                            )
                            continue
                        return ChatAgentResponse(
                            answer=final_text or "I could not generate a response.",
                            tool_calls=tool_calls_for_client,
                            analysis=analysis_for_client,
                        )

                    for tool_call in tool_calls:
                        function = getattr(tool_call, "function", None)
                        name = getattr(function, "name", "")
                        arguments = function_call_arguments(getattr(function, "arguments", None))
                        logger.info("Model requested MCP tool '%s' with arguments: %s", name, json.dumps(arguments, default=str))
                        try:
                            result = toolbox.call(name, arguments)
                            execution = execute_tool_for_chat(name, arguments, result)
                            response_payload = json.dumps(sanitize_json_value(execution.model_payload), allow_nan=False)
                            tool_calls_for_client.append(
                                {
                                    "name": name,
                                    "args": arguments,
                                    "result": execution.client_result,
                                }
                            )
                            analysis_for_client.extend(execution.analysis)
                        except Exception as exc:
                            logger.exception("MCP tool '%s' failed during chat answer", name)
                            response_payload = json.dumps({"error": str(exc)})
                            tool_calls_for_client.append(
                                {
                                    "name": name,
                                    "args": arguments,
                                    "result": {"error": str(exc)},
                                }
                            )

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": response_payload,
                            }
                        )
                        used_tool = True

                return ChatAgentResponse(answer="I could not complete the tool workflow.")
        except openai.APIError as exc:
            return ChatAgentResponse(answer=format_model_error(exc))
        except Exception:
            logger.exception("Falling back after MCP or agent failure")
            try:
                response = self._completion(
                    [{"role": "user", "content": prompt + fallback_instruction}],
                )
                return ChatAgentResponse(answer=extract_text(response) or "I could not generate a response.")
            except openai.APIError as exc:
                return ChatAgentResponse(answer=format_model_error(exc))

    def answer(self, message: str, role: str | None, history: List[dict]) -> str:
        return self.respond(message, role, history).answer
