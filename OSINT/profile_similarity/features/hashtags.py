from typing import Dict, Tuple


def hashtag_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    tags1 = {str(tag).strip().lower() for tag in (profile1.get("hashtags") or []) if str(tag).strip()}
    tags2 = {str(tag).strip().lower() for tag in (profile2.get("hashtags") or []) if str(tag).strip()}
    if not tags1 and not tags2:
        return 0.0, "No hashtags were available for comparison."
    union = tags1 | tags2
    if not union:
        return 0.0, "Hashtags were empty after normalization."
    score = len(tags1 & tags2) / len(union)
    return round(score, 4), f"The overlap between hashtag sets produced a Jaccard score of {score:.2f}."
