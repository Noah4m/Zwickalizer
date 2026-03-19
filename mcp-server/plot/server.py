"""
Plot MCP server.

Generates SVG chart images and returns them as frontend-ready data URLs.
"""
import ast
import base64
import html
import math
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="MatAI MCP Server (Plotting)", version="0.1.0")


class LineChartRequest(BaseModel):
    values: list[float] = Field(min_length=1)
    x_values: list[float | str] | None = None
    dates: list[str] | None = None
    title: str = "Series plot"
    x_label: str = "X"
    y_label: str = "Value"
    series_name: str = "Series"


class FunctionPlotRequest(BaseModel):
    expression: str = Field(min_length=1, description="Expression in x, e.g. 2*x or sin(x)")
    x_start: float = -10.0
    x_end: float = 10.0
    num_points: int = Field(default=200, ge=2, le=1000)
    title: str | None = None
    x_label: str = "x"
    y_label: str = "f(x)"
    series_name: str = "Function"


ALLOWED_FUNCTIONS = {
    "abs": abs,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
}
ALLOWED_CONSTANTS = {"pi": math.pi, "e": math.e}
ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.Constant,
)


def _svg_data_url(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _resolve_x_values(req: LineChartRequest) -> list[float | str]:
    if req.x_values is not None:
        return req.x_values
    if req.dates is not None:
        return req.dates
    return list(range(len(req.values)))


def _validate_expression(expression: str) -> ast.Expression:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid expression syntax: {exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_AST_NODES):
            raise HTTPException(status_code=400, detail="Expression contains unsupported syntax")
        if isinstance(node, ast.Name) and node.id not in {"x", *ALLOWED_FUNCTIONS.keys(), *ALLOWED_CONSTANTS.keys()}:
            raise HTTPException(status_code=400, detail=f"Unknown symbol '{node.id}' in expression")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
                raise HTTPException(status_code=400, detail="Only simple math function calls are allowed")
    return tree


def _evaluate_expression(tree: ast.Expression, x_value: float) -> float:
    scope = {"x": x_value, **ALLOWED_FUNCTIONS, **ALLOWED_CONSTANTS}
    try:
        result = eval(compile(tree, "<plot-expression>", "eval"), {"__builtins__": {}}, scope)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not evaluate expression: {exc}") from exc

    if not isinstance(result, (int, float)) or not math.isfinite(result):
        raise HTTPException(status_code=400, detail="Expression must evaluate to a finite number")

    return float(result)


def _build_line_chart_svg(
    x_axis_values: list[float | str],
    y_values: list[float],
    title: str,
    x_label: str,
    y_label: str,
    series_name: str,
) -> str:
    width, height = 960, 560
    left, right, top, bottom = 88, 42, 44, 84
    chart_width = width - left - right
    chart_height = height - top - bottom

    min_value = min(y_values)
    max_value = max(y_values)
    if min_value == max_value:
        min_value -= 1
        max_value += 1

    def x_pos(index: int) -> float:
        if len(y_values) == 1:
            return left + chart_width / 2
        return left + (index / (len(y_values) - 1)) * chart_width

    def y_pos(value: float) -> float:
        ratio = (value - min_value) / (max_value - min_value)
        return top + chart_height - (ratio * chart_height)

    points = [(x_pos(index), y_pos(value)) for index, value in enumerate(y_values)]
    path = " ".join(
        f"{'M' if index == 0 else 'L'} {x_value:.2f} {y_value:.2f}"
        for index, (x_value, y_value) in enumerate(points)
    )

    markers = "".join(
        (
            f'<circle cx="{x_value:.2f}" cy="{y_value:.2f}" r="4.5" '
            'fill="#4ade80" stroke="#0f1217" stroke-width="2" />'
        )
        for x_value, y_value in points
    )

    y_mid = (min_value + max_value) / 2
    grid_values = [max_value, y_mid, min_value]
    grid_markup = "".join(
        (
            f'<line x1="{left}" y1="{y_pos(value):.2f}" x2="{width - right}" y2="{y_pos(value):.2f}" '
            'stroke="#2a2f39" stroke-width="1" stroke-dasharray="5 7" />'
            f'<text x="{left - 14}" y="{y_pos(value) + 5:.2f}" text-anchor="end" '
            'font-family="IBM Plex Mono, monospace" font-size="12" fill="#9aa3b2">'
            f"{value:.2f}</text>"
        )
        for value in grid_values
    )

    x_indices = sorted({0, len(x_axis_values) // 2, len(x_axis_values) - 1})
    x_markup = "".join(
        (
            f'<text x="{x_pos(index):.2f}" y="{height - bottom + 28}" text-anchor="middle" '
            'font-family="IBM Plex Mono, monospace" font-size="12" fill="#7a8290">'
            f"{html.escape(str(x_axis_values[index]))}</text>"
        )
        for index in x_indices
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">
  <rect width="{width}" height="{height}" rx="28" fill="#111318" />
  <rect x="18" y="18" width="{width - 36}" height="{height - 36}" rx="22" fill="#171a20" stroke="#2b3038" />
  <text x="{left}" y="38" font-family="IBM Plex Sans, sans-serif" font-size="24" font-weight="600" fill="#eef2f7">{html.escape(title)}</text>
  <text x="{left}" y="64" font-family="IBM Plex Mono, monospace" font-size="12" fill="#7a8290">{html.escape(series_name)}</text>
  {grid_markup}
  <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#4b5362" stroke-width="1.2" />
  <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#4b5362" stroke-width="1.2" />
  <path d="{path}" stroke="#4ade80" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" />
  {markers}
  {x_markup}
  <text x="{left + chart_width / 2:.2f}" y="{height - 22}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="13" fill="#9aa3b2">{html.escape(x_label)}</text>
  <text x="26" y="{top + chart_height / 2:.2f}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="13" fill="#9aa3b2" transform="rotate(-90 26 {top + chart_height / 2:.2f})">{html.escape(y_label)}</text>
</svg>"""


def _plot_response(
    *,
    title: str,
    x_label: str,
    y_label: str,
    series_name: str,
    x_axis_values: list[float | str],
    y_values: list[float],
) -> dict:
    svg = _build_line_chart_svg(
        x_axis_values=x_axis_values,
        y_values=y_values,
        title=title,
        x_label=x_label,
        y_label=y_label,
        series_name=series_name,
    )

    return {
        "status": "success",
        "plot": {
            "plot_type": "line",
            "title": title,
            "x_label": x_label,
            "y_label": y_label,
            "series_name": series_name,
            "mime_type": "image/svg+xml",
            "image_data_url": _svg_data_url(svg),
            "summary": {
                "point_count": len(y_values),
                "min_value": min(y_values),
                "max_value": max(y_values),
            },
        },
    }


@app.post("/tools/plot_line_chart")
async def plot_line_chart(req: LineChartRequest):
    x_axis_values = _resolve_x_values(req)
    if len(x_axis_values) != len(req.values):
        raise HTTPException(status_code=400, detail="x_values and values must have the same length")

    return _plot_response(
        title=req.title,
        x_label=req.x_label,
        y_label=req.y_label,
        series_name=req.series_name,
        x_axis_values=x_axis_values,
        y_values=req.values,
    )


@app.post("/tools/plot_function")
async def plot_function(req: FunctionPlotRequest):
    if req.x_end <= req.x_start:
        raise HTTPException(status_code=400, detail="x_end must be greater than x_start")

    tree = _validate_expression(req.expression)
    step = (req.x_end - req.x_start) / (req.num_points - 1)
    x_values = [req.x_start + (index * step) for index in range(req.num_points)]
    y_values = [_evaluate_expression(tree, x_value) for x_value in x_values]
    title = req.title or f"f(x) = {req.expression}"

    return _plot_response(
        title=title,
        x_label=req.x_label,
        y_label=req.y_label,
        series_name=req.series_name,
        x_axis_values=[round(x_value, 4) for x_value in x_values],
        y_values=y_values,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PLOT_PORT", 8004)))
