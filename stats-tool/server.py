"""
Stats Tool — the LLM agent NEVER computes statistics itself.
It calls these endpoints with data arrays, gets back structured results with
p-values, effect sizes, and a plain-English interpretation hint.
"""
import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import numpy as np
from scipy import stats
from statsmodels.tsa.stattools import adfuller
import warnings

warnings.filterwarnings("ignore")

app = FastAPI(title="MatAI Stats Tool", version="0.1.0")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _interpretation(p: float, threshold: float = 0.05) -> str:
    return "statistically significant" if p < threshold else "not statistically significant"


# ── Tool: t-test (two independent groups) ────────────────────────────────────

class TTestRequest(BaseModel):
    group_a: List[float]
    group_b: List[float]
    label_a: str = "Group A"
    label_b: str = "Group B"
    equal_var: bool = False   # False = Welch's t-test (safer default)


@app.post("/stats/ttest")
async def ttest(req: TTestRequest):
    a, b = np.array(req.group_a), np.array(req.group_b)
    t_stat, p_value = stats.ttest_ind(a, b, equal_var=req.equal_var)
    # Cohen's d effect size
    pooled_std = np.sqrt((a.std()**2 + b.std()**2) / 2)
    cohens_d = (a.mean() - b.mean()) / pooled_std if pooled_std > 0 else 0.0

    return {
        "test": "Welch t-test" if not req.equal_var else "Student t-test",
        "label_a": req.label_a, "mean_a": round(float(a.mean()), 4), "std_a": round(float(a.std()), 4), "n_a": len(a),
        "label_b": req.label_b, "mean_b": round(float(b.mean()), 4), "std_b": round(float(b.std()), 4), "n_b": len(b),
        "t_statistic": round(float(t_stat), 4),
        "p_value": round(float(p_value), 6),
        "cohens_d": round(float(cohens_d), 4),
        "significant": bool(p_value < 0.05),
        "interpretation": _interpretation(p_value),
    }


# ── Tool: one-way ANOVA (3+ groups) ─────────────────────────────────────────

class AnovaRequest(BaseModel):
    groups: List[List[float]]
    labels: List[str]


@app.post("/stats/anova")
async def anova(req: AnovaRequest):
    arrays = [np.array(g) for g in req.groups]
    f_stat, p_value = stats.f_oneway(*arrays)
    return {
        "test": "one-way ANOVA",
        "groups": [
            {"label": l, "mean": round(float(a.mean()), 4), "std": round(float(a.std()), 4), "n": len(a)}
            for l, a in zip(req.labels, arrays)
        ],
        "f_statistic": round(float(f_stat), 4),
        "p_value": round(float(p_value), 6),
        "significant": bool(p_value < 0.05),
        "interpretation": _interpretation(p_value),
    }


# ── Tool: Mann-Kendall trend test ─────────────────────────────────────────────

class TrendRequest(BaseModel):
    values: List[float]
    dates: Optional[List[str]] = None


@app.post("/stats/trend")
async def trend_test(req: TrendRequest):
    """
    Mann-Kendall non-parametric trend test.
    Returns direction (increasing/decreasing/no trend) and significance.
    """
    y = np.array(req.values)
    n = len(y)

    # Compute S statistic manually (scipy has no MK, keeping dependency-free)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = y[j] - y[i]
            if diff > 0: s += 1
            elif diff < 0: s -= 1

    var_s = n * (n - 1) * (2 * n + 5) / 18
    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0

    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    # Sen's slope (robust linear trend per time step)
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            slopes.append((y[j] - y[i]) / (j - i))
    sens_slope = float(np.median(slopes)) if slopes else 0.0

    direction = "no trend"
    if p_value < 0.05:
        direction = "increasing" if s > 0 else "decreasing"

    return {
        "test": "Mann-Kendall",
        "n": n,
        "s_statistic": int(s),
        "z_score": round(float(z), 4),
        "p_value": round(float(p_value), 6),
        "sens_slope_per_step": round(sens_slope, 6),
        "direction": direction,
        "significant": bool(p_value < 0.05),
        "interpretation": f"Trend is {direction} ({_interpretation(p_value)})",
    }


# ── Tool: normality check (Shapiro-Wilk) ─────────────────────────────────────

class NormalityRequest(BaseModel):
    values: List[float]


@app.post("/stats/normality")
async def normality_check(req: NormalityRequest):
    y = np.array(req.values)
    stat, p_value = stats.shapiro(y[:5000])  # Shapiro is capped at 5000
    return {
        "test": "Shapiro-Wilk",
        "n": len(y),
        "statistic": round(float(stat), 4),
        "p_value": round(float(p_value), 6),
        "is_normal": bool(p_value >= 0.05),
        "interpretation": "data appears normally distributed" if p_value >= 0.05 else "data is not normally distributed — use non-parametric tests",
    }


# ── Tool: correlation between two properties ─────────────────────────────────

class CorrelationRequest(BaseModel):
    x: List[float]
    y: List[float]
    label_x: str = "X"
    label_y: str = "Y"


@app.post("/stats/correlation")
async def correlation(req: CorrelationRequest):
    x, y = np.array(req.x), np.array(req.y)
    pearson_r, pearson_p = stats.pearsonr(x, y)
    spearman_r, spearman_p = stats.spearmanr(x, y)
    return {
        "label_x": req.label_x, "label_y": req.label_y,
        "n": len(x),
        "pearson_r": round(float(pearson_r), 4),
        "pearson_p": round(float(pearson_p), 6),
        "spearman_r": round(float(spearman_r), 4),
        "spearman_p": round(float(spearman_p), 6),
        "interpretation": f"{'Strong' if abs(pearson_r) > 0.7 else 'Moderate' if abs(pearson_r) > 0.4 else 'Weak'} {'positive' if pearson_r > 0 else 'negative'} correlation",
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("STATS_PORT", 8002)))
