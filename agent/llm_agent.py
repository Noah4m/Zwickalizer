import json
from typing import Any, List

from google import genai
from google.genai.errors import ClientError
from google.genai import types

from mcp_client import MCPToolbox


SYSTEM_PROMPT = """You are MatAI, a concise and practical assistant.
Answer directly and keep responses clear.
Use tools only when they are genuinely needed.
If the user asks for general knowledge or casual conversation, answer without using tools.
If the user asks about stored test data, materials data, measurements, trends, or records, use the available MCP tools.
Do not invent tool results.
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
    text = getattr(response, "text", None)
    if text:
        return text.strip()

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        chunks: list[str] = []
        for part in parts:
            value = getattr(part, "text", None)
            if value:
                chunks.append(value)
        if chunks:
            return " ".join(chunks).strip()

    return ""


def extract_function_calls(response: Any) -> list[Any]:
    direct_calls = getattr(response, "function_calls", None)
    if direct_calls:
        return list(direct_calls)

    calls: list[Any] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                calls.append(function_call)
    return calls


def response_content_for_history(response: Any) -> Any:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if content is not None:
            return content

    text = extract_text(response)
    return types.Content(role="model", parts=[types.Part.from_text(text=text or "")])


def function_call_arguments(function_call: Any) -> dict[str, Any]:
    arguments = getattr(function_call, "args", None)
    if isinstance(arguments, dict):
        return arguments

    if isinstance(arguments, str):
        try:
            loaded = json.loads(arguments)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            return {}

    arguments = getattr(function_call, "arguments", None)
    if isinstance(arguments, dict):
        return arguments

    return {}


def user_message_content(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part.from_text(text=text)])


def format_model_error(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, ClientError) and getattr(exc, "status_code", None) == 429:
        return (
            "The Gemini API quota is currently exhausted for this project, so I cannot generate a reply right now. "
            "Please wait and try again later, or switch to a different model/key with available quota."
        )
    return f"Model error: {message}"


class MCPEnabledChatAgent:
    def __init__(self, api_key: str, model: str, mcp_server_root: str):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.mcp_server_root = mcp_server_root

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

        base_contents: list[Any] = [user_message_content(prompt)]
        fallback_instruction = (
            "\n\nTool status:\n"
            "If external tools are unavailable, answer general questions normally. "
            "If the user asks for data that requires tools, explain that the tools are currently unavailable."
        )

        try:
            with MCPToolbox(self.mcp_server_root) as toolbox:
                config = types.GenerateContentConfig(
                    tools=toolbox.google_tools(),
                    temperature=0.2,
                )
                contents: list[Any] = list(base_contents)

                for _ in range(6):
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    )

                    function_calls = extract_function_calls(response)
                    if not function_calls:
                        return extract_text(response) or "I could not generate a response."

                    contents.append(response_content_for_history(response))

                    tool_parts: list[Any] = []
                    for function_call in function_calls:
                        name = getattr(function_call, "name", "")
                        arguments = function_call_arguments(function_call)
                        try:
                            result = toolbox.call(name, arguments)
                            response_payload = {"result": result}
                        except Exception as exc:
                            response_payload = {"error": str(exc)}

                        tool_parts.append(
                            types.Part.from_function_response(
                                name=name,
                                response=response_payload,
                            )
                        )

                    contents.append(types.Content(role="tool", parts=tool_parts))

                return "I could not complete the tool workflow."
        except ClientError as exc:
            return format_model_error(exc)
        except Exception:
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[
                        user_message_content(prompt + fallback_instruction),
                    ],
                    config=types.GenerateContentConfig(temperature=0.2),
                )
                return extract_text(response) or "I could not generate a response."
            except ClientError as exc:
                return format_model_error(exc)
