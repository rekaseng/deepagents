"""chart_generate — port of src/tools/chart.ts (QuickChart.io, Chart.js config → PNG).
Same v1 trade-off: external API avoids native build deps; swap to local
rendering when governance lands."""

import re
import uuid

import httpx
from langchain_core.tools import tool

from ..config import SCRATCH_DIR


@tool
def chart_generate(chart_config: dict, title: str = "chart") -> dict:
    """Generate a chart PNG from data. Input: a Chart.js configuration object (type: bar/line/pie/scatter, data.labels, data.datasets). Returns the PNG file path, ready to attach to an email draft."""
    try:
        res = httpx.post(
            "https://quickchart.io/chart",
            json={
                "chart": chart_config,
                "format": "png",
                "width": 800,
                "height": 450,
                "backgroundColor": "white",
            },
            timeout=20,
        )
        res.raise_for_status()
        out_dir = SCRATCH_DIR / "outbound"
        out_dir.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^\w\-]", "_", title)[:40]
        out_path = out_dir / f"{name}-{uuid.uuid4().hex[:8]}.png"
        out_path.write_bytes(res.content)
        return {"success": True, "output": {"filePath": str(out_path)}}
    except Exception as e:
        return {"success": False, "error": str(e)}
