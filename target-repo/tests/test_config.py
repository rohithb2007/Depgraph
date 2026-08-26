import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import average_response_times


def test_average_response_times_basic():
    result = average_response_times([0.1, 0.2, 0.3])
    assert abs(result - 0.2) < 1e-9


def test_average_response_times_single_value():
    result = average_response_times([1.5])
    assert result == 1.5


def test_average_response_times_returns_float():
    result = average_response_times([0.12, 0.34, 0.09])
    assert isinstance(result, float)
