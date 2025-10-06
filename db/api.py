from typing import Optional

from repositories.neo4j_repository import Neo4jRepository
from utils.repository_error import RepositoryError
import os


def get_ontology_repository() -> Neo4jRepository:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    encrypted = os.getenv("NEO4J_ENCRYPTED", "0") == "1"
    return Neo4jRepository(uri, user, password, encrypted=encrypted)


class DriverRepository:
    def __init__(self, repo: Optional[Neo4jRepository] = None):
        self.repo = repo or get_ontology_repository()

    def health(self) -> bool:
        try:
            self.repo.get_all_nodes()
            return True
        except RepositoryError:
            return False


