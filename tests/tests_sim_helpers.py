"""Small helpers shared by tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bot"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime  # noqa: E402

import engine  # noqa: E402
from clock import NY  # noqa: E402
from sim import FakeMarket  # noqa: E402


def halted_state():
    """A portfolio that is already down more than the daily limit, with a crypto setup forced ready."""
    start = datetime(2026, 11, 9, 0, 2, tzinfo=NY).timestamp()
    m = FakeMarket(start, 7)
    st = engine.new_state(start)
    st["cash"] = 90.0  # down 10% today
    import strategies as S
    orig = S.evaluate_crypto

    def always_ready(*a, **k):
        out = orig(*a, **k)
        for c in out:
            c["ready"] = True
        return out
    S.evaluate_crypto = always_ready

    def restore():
        S.evaluate_crypto = orig
    return st, m, restore
