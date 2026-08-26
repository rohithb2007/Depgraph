"""
Tiny demo service for DepGraph to operate on.
Deliberately uses the deprecated `np.float` alias, which NumPy removed in
1.24 (it was a plain alias for Python's built-in `float`, deprecated since
1.20). On numpy < 1.24 this works fine; on numpy >= 1.24 it raises:
    AttributeError: module 'numpy' has no attribute 'float'
That's the real, reproducible breaking change DepGraph needs to catch,
diagnose, and fix by replacing `np.float` with the built-in `float`.
"""
import numpy as np
import requests


def average_response_times(samples: list[float]) -> float:
    return float(sum(samples) / len(samples))  # <-- breaks on numpy >= 1.24


def check_remote_ok(url: str = "https://httpbin.org/status/200") -> bool:
    """Uses `requests` - upgrading this dep should NOT break anything,
    it's here so DepGraph has one dependency that upgrades cleanly
    alongside the one that doesn't."""
    resp = requests.get(url, timeout=5)
    return resp.status_code == 200


if __name__ == "__main__":
    avg = average_response_times([0.12, 0.34, 0.09])
    print(f"Average response time: {avg}")
