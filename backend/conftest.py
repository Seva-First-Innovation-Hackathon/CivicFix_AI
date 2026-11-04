import sys
from pathlib import Path
import pytest

# Add backend directory to sys.path so 'app' is importable
backend_path = Path(__file__).resolve().parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.core.limiter import limiter
from app.db.init_db import ensure_schema_upgrades
from seed import seed_demo_data

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure test database schema is created and seeded with test accounts."""
    ensure_schema_upgrades()
    seed_demo_data()

@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset rate limiter counters before every test function for test isolation."""
    try:
        limiter._storage.reset()
    except Exception:
        pass
    yield
    try:
        limiter._storage.reset()
    except Exception:
        pass
