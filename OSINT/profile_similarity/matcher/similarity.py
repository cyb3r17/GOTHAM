from typing import Dict, List, Tuple

from profile_similarity.features.bio import bio_similarity
from profile_similarity.features.captions import caption_similarity
from profile_similarity.features.display_name import display_name_similarity
from profile_similarity.features.posting import posting_similarity
from profile_similarity.features.stylometry import stylometry_similarity
from profile_similarity.features.topics import topic_similarity
from profile_similarity.features.username import username_similarity


FEATURE_WEIGHTS = {
    "username": 0.25,
    "display_name": 0.10,
    "bio": 0.25,
    "captions": 0.15,
    "stylometry": 0.10,
    "topics": 0.10,
    "posting": 0.05,
}


def compute_feature_scores(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[Dict[str, float], Dict[str, str]]:
    feature_functions = [
        ("username", username_similarity),
        ("display_name", display_name_similarity),
        ("bio", bio_similarity),
        ("captions", caption_similarity),
        ("stylometry", stylometry_similarity),
        ("topics", topic_similarity),
        ("posting", posting_similarity),
    ]
    scores = {}
    reasons = {}
    for name, fn in feature_functions:
        score, reason = fn(profile1, profile2)
        scores[name] = float(score)
        reasons[name] = reason
    return scores, reasons


def compute_overall_similarity(scores: Dict[str, float]) -> float:
    weighted_total = sum(scores.get(name, 0.0) * weight for name, weight in FEATURE_WEIGHTS.items())
    return round(weighted_total * 100.0, 2)
