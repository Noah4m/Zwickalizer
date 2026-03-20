# LLM orchestration layer: builds prompts, calls OpenAI, and runs MCP tools when needed.
import json
import logging
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

import openai
from openai import OpenAI

from mcp_client import MCPToolbox


logger = logging.getLogger("uvicorn.error")


SYSTEM_PROMPT = """You are MatAI, a concise and practical assistant.
Answer directly and keep responses clear.
Use tools only when they are genuinely needed.
If the user asks for general knowledge or casual conversation, answer without using tools.
If the user asks about stored test data, materials data, measurements, trends, or records, use the available MCP tools.
If the user asks to inspect, compare, or plot a specific test's value columns and no `test_id` is provided, ask exactly one brief clarifying question for the full `test_id`.
When you ask for or use a `test_id`, preserve the exact surrounding curly braces. The correct format is `{D1CB87C7-D89F-4583-9DA8-5372DC59F25A}` and the braces are part of the id. Never remove the braces.
If the user asks about stored tests or measurements and the request does not include a `test_id` or at least one retrieval filter such as `customer`, `material`, `testType`, `date`, `date_from`, or `date_to`, ask exactly one brief clarifying question before calling tools.
If the request is ambiguous, ask at most one concise clarifying question instead of guessing.
Do not invent tool results.
"""

FINAL_ANSWER_PROMPT = """You already have the tool results.
Answer the user's latest request now.
Do not call any more tools.
Do not say that you are retrieving data or ask the user to wait.
If no matching records were found, say that explicitly.
If plot data was returned, describe the visible trend, range, or comparison using the summarized tool output.
"""

MAX_PLOT_POINTS = 1500


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


def history_messages(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in history:
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role not in {"system", "user", "assistant"} or not content:
            continue
        messages.append({"role": role, "content": content})
    return messages


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


def _sample_indexes(length: int, max_points: int = MAX_PLOT_POINTS) -> list[int]:
    if length <= 0:
        return []
    if length <= max_points:
        return list(range(length))

    step = math.ceil(length / max_points)
    indexes = list(range(0, length, step))
    if indexes[-1] != length - 1:
        indexes.append(length - 1)
    return indexes


def _sample_series(values: list[float | None]) -> dict[str, Any]:
    sampled_indexes = _sample_indexes(len(values))
    sampled_values = [values[index] for index in sampled_indexes]
    return {
        "sampledIndices": sampled_indexes,
        "sampledValues": sampled_values,
        "sourcePoints": len(values),
        "sampledPoints": len(sampled_indexes),
        "sampledDown": len(sampled_indexes) < len(values),
    }


def _series_statistics(values: list[float | None]) -> dict[str, float | None]:
    finite_values = [value for value in values if value is not None]
    if not finite_values:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "range": None,
            "firstFinite": None,
            "lastFinite": None,
        }

    minimum = min(finite_values)
    maximum = max(finite_values)
    return {
        "min": minimum,
        "max": maximum,
        "mean": statistics.fmean(finite_values),
        "range": maximum - minimum,
        "firstFinite": finite_values[0],
        "lastFinite": finite_values[-1],
    }


def summarize_value_columns_tool(
    arguments: dict[str, Any], result: str
) -> ToolExecutionResult:
    payload = tool_result_payload(result)
    parsed_result = payload.get("result")
    if not isinstance(parsed_result, dict):
        return ToolExecutionResult(model_payload=payload, client_result=parsed_result)

    raw_value_columns = parsed_result.get("valueColumns")
    if not isinstance(raw_value_columns, list):
        return ToolExecutionResult(model_payload=payload, client_result=parsed_result)

    series_summaries: list[dict[str, Any]] = []
    client_value_columns: list[dict[str, Any]] = []
    has_sampled_values = False
    comparison_test_ids = parsed_result.get("testIds")
    distinct_test_ids = [
        test_id
        for test_id in (
            comparison_test_ids
            if isinstance(comparison_test_ids, list)
            else list(
                {
                    column.get("testId")
                    for column in raw_value_columns
                    if isinstance(column, dict) and isinstance(column.get("testId"), str)
                }
            )
        )
        if isinstance(test_id, str) and test_id
    ]
    comparison_mode = len(distinct_test_ids) > 1

    for index, raw_column in enumerate(raw_value_columns):
        column = raw_column if isinstance(raw_column, dict) else {}
        values = column.get("values")
        if not isinstance(values, list):
            client_value_columns.append(sanitize_json_value(column))
            continue

        plotted_values = [_safe_numeric(value) for value in values]
        name = column.get("name")
        source_document_id = column.get("sourceDocumentId")
        series_stats = _series_statistics(plotted_values)
        sampled_series = _sample_series(plotted_values)

        if isinstance(name, str) and name.strip():
            label = name.strip()
        else:
            label = f"Value column {index + 1}"

        if comparison_mode and isinstance(column.get("testId"), str) and column.get("testId"):
            label = f"{label} ({column['testId']})"

        if (
            column.get("duplicate")
            and isinstance(source_document_id, str)
            and source_document_id
        ):
            label = f"{label} ({source_document_id})"

        series_summaries.append(
            {
                "label": label,
                "name": name,
                "childId": column.get("childId"),
                "sourceDocumentId": source_document_id,
                "points": len(values),
                "finitePoints": len(
                    [value for value in plotted_values if value is not None]
                ),
                "missingPoints": len(
                    [value for value in plotted_values if value is None]
                ),
                **series_stats,
                "sampledPoints": sampled_series["sampledPoints"],
                "sampledDown": sampled_series["sampledDown"],
            }
        )
        client_value_columns.append(
            sanitize_json_value(
                {
                    **{key: value for key, value in column.items() if key != "values"},
                    **sampled_series,
                }
            )
        )
        has_sampled_values = True

    if not has_sampled_values:
        return ToolExecutionResult(model_payload=payload, client_result=parsed_result)

    strict = bool(parsed_result.get("strict", arguments.get("strict", True)))
    include_values = True
    values_limit = parsed_result.get("valuesLimit", arguments.get("values_limit"))
    value_column_index = parsed_result.get(
        "valueColumnIndex", arguments.get("value_column_index")
    )
    test_id = parsed_result.get("testId") or arguments.get("test_id")
    if not distinct_test_ids and isinstance(test_id, str) and test_id:
        distinct_test_ids = [test_id]

    summarized_result = {
        "testId": test_id,
        "testIds": distinct_test_ids,
        "comparisonMode": comparison_mode,
        "strict": strict,
        "includeValues": include_values,
        "count": parsed_result.get("count", len(client_value_columns)),
        "valuesLimit": values_limit,
        "valueColumnIndex": (
            value_column_index if isinstance(value_column_index, int) else None
        ),
        "plotShownToUser": True,
        "sampling": {
            "maxPoints": MAX_PLOT_POINTS,
            "strategy": "deterministic_stride",
        },
        "note": (
            "A line plot of sampled value columns is already shown to the user. "
            "Full values are intentionally omitted from the client payload and model context to keep the response small."
        ),
        "seriesSummaries": [
            {
                **summary,
                "minText": _format_value(summary["min"]),
                "maxText": _format_value(summary["max"]),
                "meanText": _format_value(summary["mean"]),
                "rangeText": _format_value(summary["range"]),
                "firstFiniteText": _format_value(summary["firstFinite"]),
                "lastFiniteText": _format_value(summary["lastFinite"]),
            }
            for summary in series_summaries
        ],
        "valueColumns": [
            {
                key: value
                for key, value in sanitize_json_value(column).items()
                if key not in {"values", "sampledValues", "sampledIndices"}
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


def execute_tool_for_chat(
    name: str, arguments: dict[str, Any], result: str
) -> ToolExecutionResult:
    if name in {"db_get_test_value_columns", "db_compare_two_tests"}:
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

    def _completion(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ):
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
        }
        if tools:
            request["tools"] = tools
        return self.client.chat.completions.create(**request)

    def respond(
        self, message: str, role: str | None, history: list[dict]
    ) -> ChatAgentResponse:
        conversation_history = history_messages(history)
        base_messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "system", "content": audience_instruction(role)},
            *conversation_history,
            {"role": "user", "content": message},
        ]
        fallback_messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "system", "content": audience_instruction(role)},
            {
                "role": "system",
                "content": (
                    "External MCP tools are currently unavailable. "
                    "Answer general questions normally. "
                    "If the user asks for stored data that requires tools, explain that the tools are unavailable."
                ),
            },
            *conversation_history,
            {"role": "user", "content": message},
        ]

        try:
            with self.toolbox_factory(self.mcp_server_root) as toolbox:
                tools = toolbox.openai_tools()
                messages: list[dict[str, Any]] = list(base_messages)
                tool_calls_for_client: list[dict[str, Any]] = []
                analysis_for_client: list[dict[str, Any]] = []

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
                    return ChatAgentResponse(
                        answer=extract_text(response)
                        or "I could not generate a response.",
                        tool_calls=tool_calls_for_client,
                        analysis=analysis_for_client,
                    )

                for tool_call in tool_calls:
                    function = getattr(tool_call, "function", None)
                    name = getattr(function, "name", "")
                    arguments = function_call_arguments(
                        getattr(function, "arguments", None)
                    )
                    logger.info(
                        "Model requested MCP tool '%s' with arguments: %s",
                        name,
                        json.dumps(arguments, default=str),
                    )
                    try:
                        result = toolbox.call(name, arguments)
                        execution = execute_tool_for_chat(name, arguments, result)
                        response_payload = json.dumps(
                            sanitize_json_value(execution.model_payload),
                            allow_nan=False,
                        )
                        tool_calls_for_client.append(
                            {
                                "name": name,
                                "args": arguments,
                                "result": execution.client_result,
                            }
                        )
                        analysis_for_client.extend(execution.analysis)
                    except Exception as exc:
                        logger.exception(
                            "MCP tool '%s' failed during chat answer", name
                        )
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

                final_response = self._completion(
                    messages
                    + [{"role": "system", "content": FINAL_ANSWER_PROMPT.strip()}]
                )
                return ChatAgentResponse(
                    answer=extract_text(final_response)
                    or "I could not generate a response.",
                    tool_calls=tool_calls_for_client,
                    analysis=analysis_for_client,
                )
        except openai.APIError as exc:
            return ChatAgentResponse(answer=format_model_error(exc))
        except Exception:
            logger.exception("Falling back after MCP or agent failure")
            try:
                response = self._completion(fallback_messages)
                return ChatAgentResponse(
                    answer=extract_text(response) or "I could not generate a response."
                )
            except openai.APIError as exc:
                return ChatAgentResponse(answer=format_model_error(exc))

    def answer(self, message: str, role: str | None, history: list[dict]) -> str:
        return self.respond(message, role, history).answer
