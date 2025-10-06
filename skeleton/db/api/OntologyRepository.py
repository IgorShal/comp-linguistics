import os
from typing import Optional, Dict, Any, List

from repositories.neo4j_repository import Neo4jRepository


class OntologyRepository(Neo4jRepository):
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        uri = uri or os.getenv("NEO4J_URI")
        user = user or os.getenv("NEO4J_USER")
        password = password or os.getenv("NEO4J_PASSWORD")
        super().__init__(uri, user, password)

    # В этом классе можно расширять специфическими методами, если потребуется


