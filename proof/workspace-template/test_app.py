"""Dependency-free test for the §9 proof edit: run with `python3 test_app.py`.

Exits 0 iff the edit is correct (get_value() returns 42). No pytest, no
third-party imports — the proof container stays minimal (spec-settled).
"""

import sys

from app import get_value

EXPECTED = 42

actual = get_value()
if actual == EXPECTED:
    print(f"PASS: get_value() == {EXPECTED}")
    sys.exit(0)
print(f"FAIL: get_value() == {actual!r}, expected {EXPECTED}")
sys.exit(1)
