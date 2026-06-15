"""Tool registries. NOTE: run_code is NOT in GENERAL_TOOLS — only sandbox-tier
subagents get it (least privilege). There is NO gmail send tool anywhere —
draft-only enforced by absence."""

from .basic import calculator, echo, web_fetch
from .chart import chart_generate
from .excel import excel_read, excel_write
from .gmail import GMAIL_TOOLS
from .run_code import run_code
from .sqltool import sql_query

# Main agent + non-sandbox subagents
GENERAL_TOOLS = [
    calculator,
    echo,
    web_fetch,
    excel_read,
    excel_write,
    chart_generate,
    sql_query,
    *GMAIL_TOOLS,
]

# Sandbox-tier subagents (skills flagged subagent: true): no email access,
# no further delegation, but code execution allowed.
SANDBOX_TOOLS = [
    excel_read,
    excel_write,
    chart_generate,
    run_code,
    calculator,
]
