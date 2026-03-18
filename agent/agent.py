"""
Agent — LLM orchestrator using Google Gemini.

Receives a user message + chat history from the backend.
Calls Gemini 2.0 Flash with a tool belt (MCP tools + stats tools).
Runs the agentic loop: model decides which tools to call, we execute them,
feed results back, until the model produces a final text answer.
"""
import os, json
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import httpx
from google import genai
from google.genai import types

app = FastAPI(title="MatAI Agent", version="0.1.0")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MCP_URL        = os.environ["MCP_SERVER_URL"]   # http://mcp-server:8001
STATS_URL      = os.environ["STATS_TOOL_URL"]   # http://stats-tool:8002

gemini = genai.Client(api_key=GEMINI_API_KEY)
MODEL  = "gemini-2.5-flash-lite"

# ── Tool declarations (Gemini function-calling format) ────────────────────────

TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="describe_db",
        description="Discover what collections and fields exist in the MongoDB database. Call this first if unsure about field names or collection structure.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="list_materials",
        description="List all material names available in the database.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="query_tests",
        description="Query test result rows from the database with optional filters.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "material_name": types.Schema(type=types.Type.STRING),
                "machine_id":    types.Schema(type=types.Type.STRING),
                "site":          types.Schema(type=types.Type.STRING),
                "property_name": types.Schema(type=types.Type.STRING,
                                              description="e.g. tensile_strength, elongation"),
                "date_from":     types.Schema(type=types.Type.STRING,
                                              description="ISO date e.g. 2024-01-01"),
                "date_to":       types.Schema(type=types.Type.STRING),
                "limit":         types.Schema(type=types.Type.INTEGER),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="summary_stats",
        description=(
            "Get descriptive statistics (mean, std, min, max, percentiles) "
            "for a material property, optionally grouped by machine or site."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            required=["material_name", "property_name"],
            properties={
                "material_name": types.Schema(type=types.Type.STRING),
                "property_name": types.Schema(type=types.Type.STRING),
                "group_by":      types.Schema(
                    type=types.Type.STRING,
                    enum=["machine_id", "site"],
                    description="Optional grouping column",
                ),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="get_series",
        description=(
            "Fetch an ordered time series (dates + values) for a material property. "
            "Use this before calling trend or correlation tests."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            required=["material_name", "property_name"],
            properties={
                "material_name": types.Schema(type=types.Type.STRING),
                "property_name": types.Schema(type=types.Type.STRING),
                "machine_id":    types.Schema(type=types.Type.STRING),
                "date_from":     types.Schema(type=types.Type.STRING),
                "date_to":       types.Schema(type=types.Type.STRING),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="stats_ttest",
        description=(
            "Run a Welch t-test to compare two groups. "
            "Returns t-statistic, p-value, Cohen's d effect size."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            required=["group_a", "group_b"],
            properties={
                "group_a": types.Schema(type=types.Type.ARRAY,
                                        items=types.Schema(type=types.Type.NUMBER)),
                "group_b": types.Schema(type=types.Type.ARRAY,
                                        items=types.Schema(type=types.Type.NUMBER)),
                "label_a": types.Schema(type=types.Type.STRING),
                "label_b": types.Schema(type=types.Type.STRING),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="stats_trend",
        description=(
            "Run Mann-Kendall trend test on a time series. "
            "Returns direction (increasing/decreasing/no trend), p-value, Sen's slope."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            required=["values"],
            properties={
                "values": types.Schema(type=types.Type.ARRAY,
                                       items=types.Schema(type=types.Type.NUMBER)),
                "dates":  types.Schema(type=types.Type.ARRAY,
                                       items=types.Schema(type=types.Type.STRING)),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="stats_normality",
        description=(
            "Check if a sample is normally distributed (Shapiro-Wilk). "
            "Use before choosing parametric vs non-parametric tests."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            required=["values"],
            properties={
                "values": types.Schema(type=types.Type.ARRAY,
                                       items=types.Schema(type=types.Type.NUMBER)),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="stats_correlation",
        description="Compute Pearson and Spearman correlation between two numeric series.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            required=["x", "y"],
            properties={
                "x":       types.Schema(type=types.Type.ARRAY,
                                        items=types.Schema(type=types.Type.NUMBER)),
                "y":       types.Schema(type=types.Type.ARRAY,
                                        items=types.Schema(type=types.Type.NUMBER)),
                "label_x": types.Schema(type=types.Type.STRING),
                "label_y": types.Schema(type=types.Type.STRING),
            },
        ),
    ),
])

SYSTEM_PROMPT = """You are MatAI, an expert data analyst for material testing.
You have access to a database of test results (tensile strength, elongation, etc.) and statistical tools.

Guidelines:
- Always check normality before choosing parametric vs non-parametric tests.
- For trend questions, use stats_trend (Mann-Kendall).
- For machine/site comparisons, fetch both series with get_series then run stats_ttest.
- For "does param A influence property B", fetch both series and run stats_correlation.
- Always report p-values and effect sizes in your answer.
- Suggest a logical next step at the end of every answer.
- Be concise but precise. Engineers trust numbers, not vague statements.
"""


# ── Tool executor ─────────────────────────────────────────────────────────────

async def execute_tool(name: str, inputs: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as http:
        if name == "describe_db":
            r = await http.get(f"{MCP_URL}/tools/describe_db")
        elif name == "list_materials":
            r = await http.get(f"{MCP_URL}/tools/list_materials")
        elif name == "query_tests":
            r = await http.post(f"{MCP_URL}/tools/query_tests", json=inputs)
        elif name == "summary_stats":
            r = await http.post(f"{MCP_URL}/tools/summary_stats", json=inputs)
        elif name == "get_series":
            r = await http.post(f"{MCP_URL}/tools/get_series", json=inputs)
        elif name == "stats_ttest":
            r = await http.post(f"{STATS_URL}/stats/ttest", json=inputs)
        elif name == "stats_trend":
            r = await http.post(f"{STATS_URL}/stats/trend", json=inputs)
        elif name == "stats_normality":
            r = await http.post(f"{STATS_URL}/stats/normality", json=inputs)
        elif name == "stats_correlation":
            r = await http.post(f"{STATS_URL}/stats/correlation", json=inputs)
        else:
            return {"error": f"Unknown tool: {name}"}

        r.raise_for_status()
        return r.json()


# ── Agentic loop ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []   # [{"role": "user"|"model", "content": "..."}]


@app.post("/chat")
async def chat(req: ChatRequest):
    # Build Gemini-format history (roles are "user" / "model")
    contents: list[types.Content] = []

    for m in req.history:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append(types.Content(
            role=role,
            parts=[types.Part(text=m["content"])],
        ))

    # Add current user message
    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=req.message)],
    ))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[TOOLS],
        temperature=0.2,
    )

    tool_calls_log = []   # audit trail returned to frontend

    # Agentic loop — max 10 steps
    for _ in range(10):
        response = gemini.models.generate_content(
            model=MODEL,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        parts      = candidate.content.parts

        # Collect function calls from this turn
        fn_calls = [p for p in parts if p.function_call is not None]
        text_parts = [p for p in parts if p.text]

        # No function calls → final answer
        if not fn_calls:
            answer = " ".join(p.text for p in text_parts if p.text)
            return {"answer": answer, "tool_calls": tool_calls_log}

        # Append model turn to history
        contents.append(candidate.content)

        # Execute all function calls and build a single function-response turn
        response_parts = []
        for fc in fn_calls:
            fn_name = fc.function_call.name
            fn_args = dict(fc.function_call.args)
            result  = await execute_tool(fn_name, fn_args)

            tool_calls_log.append({
                "tool":   fn_name,
                "input":  fn_args,
                "result": result,
            })

            response_parts.append(types.Part(
                function_response=types.FunctionResponse(
                    name=fn_name,
                    response=result,
                )
            ))

        # Feed all tool results back as a single "tool" turn
        contents.append(types.Content(role="tool", parts=response_parts))

    return {"answer": "Max reasoning steps reached.", "tool_calls": tool_calls_log}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AGENT_PORT", 8003)))

