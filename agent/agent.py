"""
Agent — LLM orchestrator using Google Gemini.

Receives a user message + chat history from the backend.
Calls Gemini 2.0 Flash with a tool belt (MCP tools + stats tools).
Runs the agentic loop: model decides which tools to call, we execute them,
feed results back, until the model produces a final text answer.
"""
import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import httpx
from google import genai
from google.genai import types

app = FastAPI(title="MatAI Agent", version="0.1.0")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SERVICE_URLS = {
    "db": os.environ.get("DB_MCP_SERVER_URL") or os.environ.get("MCP_SERVER_URL", "http://mcp-db-server:8001"),
    "plot": os.environ.get("PLOT_MCP_SERVER_URL", "http://mcp-plot-server:8004"),
    "stats": os.environ["STATS_TOOL_URL"],
}

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
        name="plot_line_chart",
        description=(
            "Generate a line-chart visualisation from x/y values or from a series. "
            "Use this when the user provides explicit values to plot. "
            "The generated plot is displayed directly in the UI."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            required=["values"],
            properties={
                "x_values": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="Optional x-axis labels. Use strings for dates or numeric labels.",
                ),
                "values": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.NUMBER),
                ),
                "title": types.Schema(type=types.Type.STRING),
                "x_label": types.Schema(type=types.Type.STRING),
                "y_label": types.Schema(type=types.Type.STRING),
                "series_name": types.Schema(type=types.Type.STRING),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="plot_function",
        description=(
            "Plot a mathematical function of x, for example 2*x, x**2, sin(x), or exp(-x). "
            "Use this when the user asks to plot an explicit formula."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            required=["expression"],
            properties={
                "expression": types.Schema(type=types.Type.STRING),
                "x_start": types.Schema(type=types.Type.NUMBER),
                "x_end": types.Schema(type=types.Type.NUMBER),
                "num_points": types.Schema(type=types.Type.INTEGER),
                "title": types.Schema(type=types.Type.STRING),
                "x_label": types.Schema(type=types.Type.STRING),
                "y_label": types.Schema(type=types.Type.STRING),
                "series_name": types.Schema(type=types.Type.STRING),
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
- For requests to visualise a time series, fetch the series first and then call plot_line_chart.
- If the user directly gives numbers to plot, call plot_line_chart without using the DB.
- If the user asks to plot a mathematical expression like 2*x or sin(x), call plot_function.
- The plot itself is shown in the UI, not in your tool context. After calling a plot tool, just mention that the visualisation has been generated.
- Always report p-values and effect sizes in your answer.
- Suggest a logical next step at the end of every answer.
- Be concise but precise. Engineers trust numbers, not vague statements.
"""

TOOL_ROUTES = {
    "describe_db": {"service": "db", "method": "GET", "path": "/tools/describe_db"},
    "list_materials": {"service": "db", "method": "GET", "path": "/tools/list_materials"},
    "query_tests": {"service": "db", "method": "POST", "path": "/tools/query_tests"},
    "summary_stats": {"service": "db", "method": "POST", "path": "/tools/summary_stats"},
    "get_series": {"service": "db", "method": "POST", "path": "/tools/get_series"},
    "plot_line_chart": {"service": "plot", "method": "POST", "path": "/tools/plot_line_chart"},
    "plot_function": {"service": "plot", "method": "POST", "path": "/tools/plot_function"},
    "stats_ttest": {"service": "stats", "method": "POST", "path": "/stats/ttest"},
    "stats_trend": {"service": "stats", "method": "POST", "path": "/stats/trend"},
    "stats_normality": {"service": "stats", "method": "POST", "path": "/stats/normality"},
    "stats_correlation": {"service": "stats", "method": "POST", "path": "/stats/correlation"},
}


# ── Tool executor ─────────────────────────────────────────────────────────────

async def execute_tool(name: str, inputs: dict) -> dict:
    route = TOOL_ROUTES.get(name)
    if route is None:
        return {"error": f"Unknown tool: {name}"}

    url = f"{SERVICE_URLS[route['service']]}{route['path']}"

    async with httpx.AsyncClient(timeout=30) as http:
        if route["method"] == "GET":
            r = await http.get(url)
        else:
            r = await http.post(url, json=inputs)

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
    visualizations = []

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
            return {
                "answer": answer,
                "tool_calls": tool_calls_log,
                "visualizations": visualizations,
            }

        # Append model turn to history
        contents.append(candidate.content)

        # Execute all function calls and build a single function-response turn
        response_parts = []
        for fc in fn_calls:
            fn_name = fc.function_call.name
            fn_args = dict(fc.function_call.args)
            result  = await execute_tool(fn_name, fn_args)
            model_result = result

            if fn_name in {"plot_line_chart", "plot_function"} and result.get("status") == "success":
                plot_payload = result.get("plot")
                if plot_payload is not None:
                    visualizations.append(plot_payload)
                model_result = {
                    "status": "success",
                    "message": "Plot generated and delivered to the UI.",
                }

            tool_calls_log.append({
                "tool":   fn_name,
                "input":  fn_args,
                "result": model_result,
            })

            response_parts.append(types.Part(
                function_response=types.FunctionResponse(
                    name=fn_name,
                    response=model_result,
                )
            ))

        # Feed all tool results back as a single "tool" turn
        contents.append(types.Content(role="tool", parts=response_parts))

    return {
        "answer": "Max reasoning steps reached.",
        "tool_calls": tool_calls_log,
        "visualizations": visualizations,
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AGENT_PORT", 8003)))
