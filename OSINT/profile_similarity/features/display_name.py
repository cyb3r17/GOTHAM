from typing import Dict, Tuple

import numpy as np

from profile_similarity.models.sentence_model import SentenceEncoder


encoder = SentenceEncoder()


def display_name_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    name1 = str(profile1.get("display_name", "")).strip()
    name2 = str(profile2.get("display_name", "")).strip()
    if not name1 or not name2:
        return 0.0, "No display names were available for comparison."
    emb1 = encoder.encode(name1)
    emb2 = encoder.encode(name2)
    score = float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2) + 1e-9))
    score = max(0.0, min(1.0, score))
    return round(score, 4), f"The display names were embedded and compared with cosine similarity at {score:.2f}."
