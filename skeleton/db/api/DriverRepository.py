import os
from typing import Optional

from neo4j import GraphDatabase, Driver


class DriverRepository:
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self._uri = uri or os.getenv("NEO4J_URI")
        self._user = user or os.getenv("NEO4J_USER")
        self._password = password or os.getenv("NEO4J_PASSWORD")
        self._driver: Driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))

    @property
    def driver(self) -> Driver:
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()


