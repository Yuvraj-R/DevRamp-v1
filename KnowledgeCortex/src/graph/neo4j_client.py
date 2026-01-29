"""Neo4j database client."""

from contextlib import contextmanager
from neo4j import GraphDatabase
from config import settings


class Neo4jClient:
    """Client for interacting with Neo4j graph database."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self._driver = None

    @property
    def driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def verify_connection(self) -> bool:
        """Verify that we can connect to Neo4j."""
        try:
            self.driver.verify_connectivity()
            return True
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
            return False

    @contextmanager
    def session(self):
        """Get a session context manager."""
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()

    def run_query(self, query: str, parameters: dict | None = None) -> list[dict]:
        """Run a Cypher query and return results as a list of dicts."""
        with self.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def run_write(self, query: str, parameters: dict | None = None) -> None:
        """Run a write query."""
        with self.session() as session:
            session.run(query, parameters or {})

    def clear_database(self) -> None:
        """Delete all nodes and relationships. Use with caution!"""
        self.run_write("MATCH (n) DETACH DELETE n")


# Singleton instance
_client: Neo4jClient | None = None


def get_client() -> Neo4jClient:
    """Get the singleton Neo4j client."""
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
