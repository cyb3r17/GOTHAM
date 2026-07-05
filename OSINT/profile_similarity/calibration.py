import json
import math
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "calibration.json"


def _default_params():
    return {"alpha": 6.0, "beta": 0.5}  # temperature and midpoint


def load_params():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return _default_params()
    return _default_params()


def calibrate_probability(score: float) -> float:
    """Map a raw 0-1 score to a probability using a sigmoid (Platt-like) transform.

    Params can be changed by creating `calibration.json` next to this file, e.g.
    {"alpha": 6.0, "beta": 0.5}
    """
    params = load_params()
    alpha = float(params.get("alpha", 6.0))
    beta = float(params.get("beta", 0.5))
    x = alpha * (score - beta)
    try:
        p = 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        p = 0.0 if x < 0 else 1.0
    return max(0.0, min(1.0, p))
