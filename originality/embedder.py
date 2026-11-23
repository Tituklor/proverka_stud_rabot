import zlib
import numpy as np

from .fragments import words


class Embedder:

    def __init__(self, model_name):
        self.name = model_name
        self._model = None

    def encode(self, texts):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.name)
            self._model.max_seq_length = 256
        vectors = self._model.encode(texts, normalize_embeddings=True,
                                     batch_size=32, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)


class StubEmbedder:
    name = "stub-bag-of-words-v1"

    def __init__(self, dim=512):
        self.dim = dim

    def encode(self, texts):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for w in words(text):
                out[i, zlib.crc32(w[:5].encode("utf-8")) % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms
