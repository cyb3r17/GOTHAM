from typing import Dict, Tuple

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - optional dependency
    class _FallbackFuzz:
        @staticmethod
        def ratio(a: str, b: str) -> int:
            from difflib import SequenceMatcher
            return int(SequenceMatcher(None, a, b).ratio() * 100)

        @staticmethod
        def partial_ratio(a: str, b: str) -> int:
            from difflib import SequenceMatcher
            return int(SequenceMatcher(None, a, b).ratio() * 100)

        @staticmethod
        def token_sort_ratio(a: str, b: str) -> int:
            from difflib import SequenceMatcher
            return int(SequenceMatcher(None, a.replace("_", " "), b.replace("_", " ")).ratio() * 100)

    fuzz = _FallbackFuzz()


def username_similarity(profile1: Dict[str, object], profile2: Dict[str, object]) -> Tuple[float, str]:
    user1 = str(profile1.get("username", "")).strip().lower()
    user2 = str(profile2.get("username", "")).strip().lower()
    if not user1 or not user2:
        return 0.0, "No usernames were available for comparison."
    ratio = fuzz.ratio(user1, user2) / 100.0
    partial = fuzz.partial_ratio(user1, user2) / 100.0
    token = fuzz.token_sort_ratio(user1, user2) / 100.0
    score = round((ratio * 0.5 + partial * 0.3 + token * 0.2), 4)
    reason = (
        f"The usernames share a strong overlap with a score of {score:.2f}, "
        f"based on exact, partial, and token-based matching."
    )
    return score, reason
