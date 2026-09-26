"""Central place for paths and settings. Loads .env once on import so every
module can just read os.environ without repeating load_dotenv() calls."""
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"

load_dotenv(REPO_ROOT / ".env")
