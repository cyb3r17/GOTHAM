from typing import List

import numpy as np


class SentenceEncoder:
    def __init__(self) -> None:
        self._available = False
        self._model = None
        self._tokenizer = None
        self._use_sentence_transformers = False
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._use_sentence_transformers = True
            self._available = True
        except Exception:
            self._use_sentence_transformers = False
            try:
                from transformers import AutoModel, AutoTokenizer
                import torch

                self._tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
                self._model = AutoModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
                self._available = True
            except Exception:
                self._available = False

    def _mean_pooling(self, model_output, attention_mask):
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
            input_mask_expanded.sum(1), min=1e-9
        )

    def encode(self, text: str) -> np.ndarray:
        if self._available and self._model is not None:
            if self._use_sentence_transformers:
                return np.asarray(self._model.encode([text])[0], dtype=np.float32)
            if self._tokenizer is not None:
                import torch

                encoded_input = self._tokenizer(text, padding=True, truncation=True, return_tensors="pt")
                with torch.no_grad():
                    model_output = self._model(**encoded_input)
                embedding = self._mean_pooling(model_output, encoded_input["attention_mask"])
                embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
                return np.asarray(embedding[0].cpu(), dtype=np.float32)
        tokens = [t.lower() for t in text.split() if t.isalnum()]
        if not tokens:
            return np.zeros(32, dtype=np.float32)
        vec = np.zeros(32, dtype=np.float32)
        for idx, _ in enumerate(tokens[:32]):
            vec[idx % 32] += 1.0
        return vec / max(1.0, np.linalg.norm(vec))

    def encode_many(self, texts: List[str]) -> List[np.ndarray]:
        return [self.encode(text) for text in texts]
