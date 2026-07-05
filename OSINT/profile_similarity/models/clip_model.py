import os
from typing import Optional

import numpy as np


class ClipEncoder:
    def __init__(self) -> None:
        self._available = False
        self._model = None
        self._processor = None
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            self._model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            self._processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            self._available = True
        except Exception:
            self._available = False

    def encode_image(self, image_path: Optional[str]) -> np.ndarray:
        if not image_path or not os.path.exists(image_path):
            return np.zeros(32, dtype=np.float32)
        if self._available and self._model is not None and self._processor is not None:
            from PIL import Image

            image = Image.open(image_path).convert("RGB")
            inputs = self._processor(images=image, return_tensors="pt")
            with self._model.eval():
                features = self._model.get_image_features(**inputs)
            return np.asarray(features.detach().cpu()[0], dtype=np.float32)
        return np.zeros(32, dtype=np.float32)
