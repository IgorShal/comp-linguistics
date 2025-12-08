#!/usr/bin/env python3
import os
import dotenv
from db.api.EmbeddingsGenerator import EmbeddingsGenerator
from db.api.OntologyRepository import OntologyRepository

dotenv.load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD")

if __name__ == "__main__":
    repo = OntologyRepository(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASS)
    emb_gen = EmbeddingsGenerator()
    try:
        print("Collecting nodes and computing embeddings...")
        total = repo.compute_and_store_embeddings_for_all_nodes(emb_gen)
        print(f"Processed nodes: {total}")
    finally:
        repo.close()
