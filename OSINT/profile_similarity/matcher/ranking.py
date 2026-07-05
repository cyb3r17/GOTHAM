from typing import Dict, List, Tuple

from profile_similarity.matcher.similarity import compute_feature_scores, compute_overall_similarity


def rank_profiles(profile1: Dict[str, object], profile2: Dict[str, object]) -> Dict[str, object]:
    scores, reasons = compute_feature_scores(profile1, profile2)
    overall = compute_overall_similarity(scores)
    explanations = []
    for feature_name in [
        "username",
        "display_name",
        "bio",
        "captions",
        "stylometry",
        "topics",
        "posting",
    ]:
        explanations.append({"feature": feature_name, "score": scores.get(feature_name, 0.0), "reason": reasons.get(feature_name, "")})
    return {
        "overall_similarity": overall,
        "scores": scores,
        "explanations": explanations,
    }
