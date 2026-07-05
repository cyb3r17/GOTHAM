from typing import Dict, Tuple

import numpy as np

from profile_similarity.models.sentence_model import SentenceEncoder


encoder = SentenceEncoder()


def caption_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    captions1 = profile1.get("captions") or []
    captions2 = profile2.get("captions") or []
    if not captions1 or not captions2:
        return 0.0, "No caption data was available for comparison."
    text1 = " ".join(str(c) for c in captions1[-20:])
    text2 = " ".join(str(c) for c in captions2[-20:])
    emb1 = encoder.encode(text1)
    emb2 = encoder.encode(text2)
    semantic = float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2) + 1e-9))
    len1 = sum(len(str(c)) for c in captions1[-20:]) / max(1, len(captions1[-20:]))
    len2 = sum(len(str(c)) for c in captions2[-20:]) / max(1, len(captions2[-20:]))
    length_score = 1.0 - min(abs(len1 - len2) / 200.0, 1.0)
    score = round(max(0.0, min(1.0, 0.7 * semantic + 0.3 * length_score)), 4)
    return score, f"Caption semantics and average caption length contributed to a score of {score:.2f}."
