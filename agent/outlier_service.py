import json
from typing import Any

from mcp_client import MCPToolbox


def fetch_review_outliers(mcp_server_root: str, limit: int = 6) -> dict[str, Any]:
    with MCPToolbox(mcp_server_root) as toolbox:
        tool_name = "outliers_list_review_outliers"
        if tool_name not in toolbox.tools:
            return {
                "outliers": [],
                "source": "unavailable",
                "reason": "Outlier MCP tool is not registered.",
            }

        raw_result = toolbox.call(
            tool_name,
            {
                "limit": limit,
                "sample_size": 80,
                "test_type": "tensile",
            },
        )
        payload = json.loads(raw_result) if raw_result else {}
        if not isinstance(payload, dict):
            payload = {}
        payload["source"] = "live"
        return payload
