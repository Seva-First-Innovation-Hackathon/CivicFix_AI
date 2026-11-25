import sys
from pathlib import Path

# Keep backend root on sys.path; isolated DB and fixture setup live in tests/conftest.py
backend_path = Path(__file__).resolve().parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
