"""Human-like interaction helpers — randomized taps and natural typing."""

import random
import time
from collections.abc import Callable

import uiautomator2 as u2


def random_point(el: u2.UiObject) -> tuple[int, int]:
    """Pick a Gaussian-random point within element bounds, biased toward center."""
    info = el.info
    assert isinstance(info, dict)
    bounds = info["bounds"]
    assert isinstance(bounds, dict)
    cx = (bounds["left"] + bounds["right"]) / 2
    cy = (bounds["top"] + bounds["bottom"]) / 2
    w = (bounds["right"] - bounds["left"]) / 2
    h = (bounds["bottom"] - bounds["top"]) / 2
    # ~68% of taps land within inner 1/3
    x = int(max(bounds["left"], min(bounds["right"], random.gauss(cx, w / 3))))
    y = int(max(bounds["top"], min(bounds["bottom"], random.gauss(cy, h / 3))))
    return x, y


def natural_type(send_keys: Callable[[str], None], el: u2.UiObject, text: str) -> None:
    """Click element, then send characters one at a time with human-like delays."""
    el.click()
    time.sleep(random.uniform(0.1, 0.3))
    for ch in text:
        send_keys(ch)
        time.sleep(random.uniform(0.05, 0.2))
