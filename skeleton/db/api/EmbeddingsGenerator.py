from typing import List
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


class EmbeddingsGenerator:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-mpnet-base-v2')
        return cls._instance

    @staticmethod
    def get_chunks(text: str, splitter: str = '. ') -> List[str]:
        if text[-1] == splitter:
            text = text[:-1]
        return text.split(splitter)

    def get_embeddings(self, sentences: List[str]) -> np.ndarray:
        embeddings = self._model.encode(sentences)
        return embeddings

    def get_text_embedding(self, text: str) -> np.ndarray:
        return self._model.encode([text])[0]

    @staticmethod
    def cos_compare(embedding_first: np.ndarray, embedding_second: np.ndarray) -> float:
        return cosine_similarity([embedding_first], [embedding_second])[0][0]

