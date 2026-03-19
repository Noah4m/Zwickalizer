# LLM orchestration layer: builds prompts, calls OpenAI, and runs MCP tools when needed.
import json
import logging
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


def tool_result_payload(result: str) -> dict[str, Any]:
    try:
        parsed = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        parsed = None

    if parsed is not None:
        return {"result": parsed}
    return {"result_text": result}


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

    def answer(self, message: str, role: str | None, history: List[dict]) -> str:
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

                for _ in range(6):
                    response = self._completion(messages, tools)
                    choice = response.choices[0] if response.choices else None
                    assistant_message = getattr(choice, "message", None)

                    if assistant_message is None:
                        return "I could not generate a response."

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
                        return final_text or "I could not generate a response."

                    for tool_call in tool_calls:
                        function = getattr(tool_call, "function", None)
                        name = getattr(function, "name", "")
                        arguments = function_call_arguments(getattr(function, "arguments", None))
                        logger.info("Model requested MCP tool '%s' with arguments: %s", name, json.dumps(arguments, default=str))
                        try:
                            result = toolbox.call(name, arguments)
                            response_payload = json.dumps(tool_result_payload(result))
                        except Exception as exc:
                            logger.exception("MCP tool '%s' failed during chat answer", name)
                            response_payload = json.dumps({"error": str(exc)})

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": response_payload,
                            }
                        )
                        used_tool = True

                return "I could not complete the tool workflow."
        except openai.APIError as exc:
            return format_model_error(exc)
        except Exception:
            logger.exception("Falling back after MCP or agent failure")
            try:
                response = self._completion(
                    [{"role": "user", "content": prompt + fallback_instruction}],
                )
                return extract_text(response) or "I could not generate a response."
            except openai.APIError as exc:
                return format_model_error(exc)
