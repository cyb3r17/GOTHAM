import re
from typing import Dict, Tuple

import numpy as np

from profile_similarity.models.sentence_model import SentenceEncoder


encoder = SentenceEncoder()


def _heuristic_stylometry(text1: str, text2: str) -> Tuple[float, str]:
    # fallback heuristic from previous implementation
    sentences1 = re.split(r"[.!?]+", text1)
    words1 = re.findall(r"\b\w+\b", text1.lower())
    sentences2 = re.split(r"[.!?]+", text2)
    words2 = re.findall(r"\b\w+\b", text2.lower())
    if not words1 or not words2:
        return 0.0, "No caption text was available for stylometry analysis."
    def feat(words, sentences, text):
        punctuation = re.findall(r"[.!?,'\";:-]", text)
        vowels = re.findall(r"[aeiou]", text.lower())
        uppercase = sum(1 for ch in text if ch.isupper())
        lowercase = sum(1 for ch in text if ch.islower())
        stopwords = {"the", "and", "a", "an", "to", "of", "in", "is", "it", "for", "on", "with", "this", "that"}
        stop_count = sum(1 for w in words if w in stopwords)
        unique_ratio = len(set(words)) / max(1, len(words))
        return np.array([
            len(sentences) / max(1, len(words)),
            len(words) / max(1, len(sentences)),
            len(punctuation) / max(1, len(words)),
            text.count("?"),
            text.count("!"),
            uppercase / max(1, len(text)),
            lowercase / max(1, len(text)),
            stop_count / max(1, len(words)),
            len(vowels) / max(1, len(text)),
            unique_ratio,
        ], dtype=np.float32)
    vec1 = feat(words1, sentences1, text1)
    vec2 = feat(words2, sentences2, text2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0, "Stylometry vectors were empty."
    score = float(np.dot(vec1, vec2) / (norm1 * norm2))
    score = max(0.0, min(1.0, score))
    return round(score, 4), f"The stylometry feature vector was compared with cosine similarity at {score:.2f}."


def stylometry_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    # Build text bodies from captions + bio
    text1 = " ".join(str(c) for c in (profile1.get("captions") or []))
    text2 = " ".join(str(c) for c in (profile2.get("captions") or []))
    bio1 = str(profile1.get("bio") or "").strip()
    bio2 = str(profile2.get("bio") or "").strip()
    full1 = (bio1 + " " + text1).strip()
    full2 = (bio2 + " " + text2).strip()

    if not full1 or not full2:
        return 0.0, "No text was available for stylometry analysis."

    # Prefer embedding-based similarity when model is available
    if encoder._available:
        try:
            emb1 = encoder.encode(full1)
            emb2 = encoder.encode(full2)
            score = float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2) + 1e-9))
            score = max(0.0, min(1.0, score))
            return round(score, 4), f"Embeddings compared with cosine similarity at {score:.2f}."
        except Exception:
            # fall through to heuristic
            pass

    # Fallback heuristic
    return _heuristic_stylometry(full1, full2)
