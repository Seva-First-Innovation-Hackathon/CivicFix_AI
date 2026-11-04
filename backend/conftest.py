import sys
from pathlib import Path
import pytest

# Add backend directory to sys.path so 'app' is importable
backend_path = Path(__file__).resolve().parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.core.limiter import limiter

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
