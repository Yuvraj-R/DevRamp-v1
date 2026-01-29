from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # Paths
    repos_dir: Path = Path(__file__).parent.parent / "repos"

    # LLM (for later)
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
