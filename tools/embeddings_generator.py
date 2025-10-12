from typing import List
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


class EmbeddingsGenerator:
    def __init__(self):
        self._model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-mpnet-base-v2')

    @staticmethod
    def get_chunks(text: str) -> List[str]:
        if text[-1] == '.':
            text = text[:-1]
        return text.split('.')

    def get_embeddings(self, sentences: List[str]) -> np.ndarray:
        embeddings = self._model.encode(sentences)
        return embeddings

    @staticmethod
    def cos_compare(embedding_first: np.ndarray, embedding_second: np.ndarray) -> np.ndarray:
        return cosine_similarity([embedding_first], [embedding_second])[0][0]


if __name__ == '__main__':
    text = """The car is yellow. Yellow is the color of this car"""

    generator = EmbeddingsGenerator()
    chunks = generator.get_chunks(text)
    count_of_strings = len(chunks)
    print(f"Sentences count: {count_of_strings}")
    embeddings = generator.get_embeddings(chunks)
    print(generator.cos_compare(embeddings[0], embeddings[1]))
