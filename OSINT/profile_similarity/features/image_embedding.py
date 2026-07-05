from typing import Dict, Tuple

import numpy as np

from profile_similarity.models.clip_model import ClipEncoder


encoder = ClipEncoder()


def image_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    image1 = str(profile1.get("profile_image", "")).strip()
    image2 = str(profile2.get("profile_image", "")).strip()
    if not image1 or not image2:
        return 0.0, "No profile images were available for comparison."
    emb1 = encoder.encode_image(image1)
    emb2 = encoder.encode_image(image2)
    score = float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2) + 1e-9))
    score = max(0.0, min(1.0, score))
    return round(score, 4), f"The profile images were compared with CLIP-style embeddings at {score:.2f}."
