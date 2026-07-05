import datetime as dt
from collections import Counter
from typing import Dict, Tuple

import numpy as np


def posting_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    times1 = profile1.get("posting_times") or []
    times2 = profile2.get("posting_times") or []
    if not times1 or not times2:
        return 0.0, "No posting timestamps were available."

    def hist(times: list) -> np.ndarray:
        hour_counts = Counter()
        weekday_counts = Counter()
        for timestamp in times:
            try:
                dt_value = dt.datetime.fromisoformat(str(timestamp))
            except ValueError:
                continue
            hour_counts[dt_value.hour] += 1
            weekday_counts[dt_value.weekday()] += 1
        vec = np.array([hour_counts[i] for i in range(24)], dtype=np.float32)
        vec = np.concatenate([vec, np.array([weekday_counts[i] for i in range(7)], dtype=np.float32)])
        return vec / max(1.0, np.linalg.norm(vec))

    vec1 = hist(times1)
    vec2 = hist(times2)
    score = float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-9))
    score = max(0.0, min(1.0, score))
    return round(score, 4), f"The posting hour and weekday histograms matched at {score:.2f}."
