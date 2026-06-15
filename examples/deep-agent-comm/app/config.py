"""Central paths + env. All paths are local to this example directory
(examples/deep-agent-comm). The .env beside this folder holds DEEPSEEK_*,
GMAIL_*, and the Microsoft app creds used by the Teams bot endpoint."""

import os
from pathlib import Path

from dotenv import load_dotenv

# examples/deep-agent-comm/app/config.py -> parents[1] == examples/deep-agent-comm
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

SCRATCH_DIR = PROJECT_ROOT / "scratch"
SKILLS_DIR = PROJECT_ROOT / "skills"                  # single source of truth for skill .md files
PUBLIC_DIR = PROJECT_ROOT / "public"
SECRETS_DIR = PROJECT_ROOT / "secrets"
CLIENT_SECRET_PATH = SECRETS_DIR / "google_oauth_client.json"
TOKEN_PATH = SECRETS_DIR / "gmail.token.json"

# Local runtime state (sqlite databases)
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TASK_DB_PATH = DATA_DIR / "tasks.sqlite"
CHECKPOINT_DB_PATH = DATA_DIR / "checkpoints.sqlite"
DEMO_DB_PATH = DATA_DIR / "demo-data.sqlite"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

DEFAULT_GMAIL_USER = "yeexianteoh1223@gmail.com"
GMAIL_USER = os.getenv("GMAIL_USER", DEFAULT_GMAIL_USER)
ALLOWED_SENDERS = [
    s.strip().lower() for s in os.getenv("ALLOWED_SENDERS", "").split(",") if s.strip()
]
POLL_INTERVAL_MS = int(os.getenv("POLL_INTERVAL_MS", "60000"))
ATTACHMENT_MAX_BYTES = int(os.getenv("ATTACHMENT_MAX_BYTES", str(10 * 1024 * 1024)))

# Microsoft Bot Framework (Teams) — optional; only needed for the /api/messages endpoint
MICROSOFT_APP_ID = os.getenv("MICROSOFT_APP_ID", "")
MICROSOFT_APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")
MICROSOFT_APP_TENANT_ID = os.getenv("MICROSOFT_APP_TENANT_ID", "")

PORT = int(os.getenv("PORT", "3001"))
