from typing import Dict, Tuple

import numpy as np

from profile_similarity.models.sentence_model import SentenceEncoder


encoder = SentenceEncoder()


def bio_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    bio1 = str(profile1.get("bio", "")).strip()
    bio2 = str(profile2.get("bio", "")).strip()
    if not bio1 or not bio2:
        return 0.0, "No bios were available for comparison."
    emb1 = encoder.encode(bio1)
    emb2 = encoder.encode(bio2)
    score = float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2) + 1e-9))
    score = max(0.0, min(1.0, score))
    return round(score, 4), f"The bios were compared semantically and scored {score:.2f} on cosine similarity."
