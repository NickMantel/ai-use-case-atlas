import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Isolated settings for the test run (must be set before the app is imported).
_DB = ROOT / "data" / "test_atlas.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["LLM_PROVIDER"] = "stub"
os.environ["CATALOG_ADAPTER"] = "demo"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ.setdefault("FRAMEWORK", "default")


@pytest.fixture(scope="session")
def client():
    if _DB.exists():
        _DB.unlink()
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        c.cookies.set("atlas_name", "Test Facilitator")
        yield c
    if _DB.exists():
        _DB.unlink()


@pytest.fixture()
def fw():
    from app.config import get_framework

    return get_framework()
