import hashlib
import os
import sqlite3
from typing import Optional

import numpy as np


class EmbeddingCache:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "embeddings.sqlite3")
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                vector BLOB NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def _key(self, text: str, kind: str) -> str:
        return hashlib.sha256(f"{kind}:{text}".encode("utf-8")).hexdigest()

    def get(self, text: str, kind: str) -> Optional[np.ndarray]:
        key = self._key(text, kind)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT vector FROM embeddings WHERE key=?", (key,)).fetchone()
        conn.close()
        if row is None:
            return None
        return np.frombuffer(row[0], dtype=np.float32)

    def set(self, text: str, kind: str, vector: np.ndarray) -> None:
        key = self._key(text, kind)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO embeddings (key, kind, vector) VALUES (?, ?, ?)",
            (key, kind, vector.astype(np.float32).tobytes()),
        )
        conn.commit()
        conn.close()
