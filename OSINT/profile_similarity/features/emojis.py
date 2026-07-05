import re
from typing import Dict, Tuple

import numpy as np


def emoji_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    text1 = " ".join(str(c) for c in (profile1.get("captions") or [])) + " " + str(profile1.get("bio", ""))
    text2 = " ".join(str(c) for c in (profile2.get("captions") or [])) + " " + str(profile2.get("bio", ""))
    emoji_pattern = re.compile("[\U0001F300-\U0001FAFF\\u2600-\u27BF]")
    emojis1 = emoji_pattern.findall(text1)
    emojis2 = emoji_pattern.findall(text2)
    if not emojis1 and not emojis2:
        return 0.0, "No emojis were detected in either profile."
    counts1 = {e: emojis1.count(e) for e in set(emojis1)}
    counts2 = {e: emojis2.count(e) for e in set(emojis2)}
    all_emojis = set(counts1) | set(counts2)
    vec1 = np.array([counts1.get(e, 0) for e in sorted(all_emojis)], dtype=np.float32)
    vec2 = np.array([counts2.get(e, 0) for e in sorted(all_emojis)], dtype=np.float32)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0, "Emoji vectors were empty."
    score = float(np.dot(vec1, vec2) / (norm1 * norm2))
    return round(max(0.0, min(1.0, score)), 4), f"The emoji frequency vectors produced a similarity of {score:.2f}."
