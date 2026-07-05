from typing import Dict, Tuple

import re
import numpy as np

try:
    from keybert import KeyBERT
except Exception:  # pragma: no cover - optional dependency
    KeyBERT = None


def topic_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    text1 = " ".join(str(c) for c in (profile1.get("captions") or [])) + " " + str(profile1.get("bio", ""))
    text2 = " ".join(str(c) for c in (profile2.get("captions") or [])) + " " + str(profile2.get("bio", ""))
    if not text1 or not text2:
        return 0.0, "No text was available for topic extraction."
    if KeyBERT is None:
        # Build term-frequency vectors for more granular similarity when KeyBERT is unavailable
        def top_terms(text: str, top_n: int = 20):
            toks = [t.lower() for t in re.findall(r"\b\w{4,}\b", text)]
            counts = {}
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            # keep top_n terms by frequency
            items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:top_n]
            terms, freqs = zip(*items) if items else ([], [])
            return list(terms), list(freqs)

        topic1, freqs1 = top_terms(text1, top_n=20)
        topic2, freqs2 = top_terms(text2, top_n=20)
        # If no terms found, fall back to simple set-based topics
        if not topic1:
            topic1 = []
        if not topic2:
            topic2 = []
    else:
        kw_model = KeyBERT()
        topic1 = [t for t, _ in kw_model.extract_keywords(text1, top_n=10)]
        topic2 = [t for t, _ in kw_model.extract_keywords(text2, top_n=10)]
    if not topic1 or not topic2:
        return 0.0, "No topics could be extracted from the provided text."
    # Build combined vocabulary
    combined = sorted(set(topic1) | set(topic2))
    if not combined:
        return 0.0, "Keyword sets were empty."
    # Build term-frequency vectors if frequencies available
    def tf_vector(terms, freqs):
        vec = np.zeros(len(combined), dtype=np.float32)
        if not terms:
            return vec
        term_to_freq = dict(zip(terms, freqs)) if freqs else {t: 1 for t in terms}
        for i, term in enumerate(combined):
            vec[i] = float(term_to_freq.get(term, 0))
        # normalize
        norm = np.linalg.norm(vec)
        return vec / (norm + 1e-9)

    # Detect if freqs were computed (fallback path) or not (KeyBERT path)
    if 'freqs1' in locals() and freqs1:
        vec1 = tf_vector(topic1, freqs1)
    else:
        vec1 = tf_vector(topic1, [1] * len(topic1))
    if 'freqs2' in locals() and freqs2:
        vec2 = tf_vector(topic2, freqs2)
    else:
        vec2 = tf_vector(topic2, [1] * len(topic2))

    score = float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-9))
    return round(max(0.0, min(1.0, score)), 4), f"The extracted topic keywords overlapped with a similarity score of {score:.2f}."
