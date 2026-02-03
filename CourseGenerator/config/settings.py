"""CourseGenerator settings."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # KnowledgeCortex API
    cortex_api_url: str = "http://localhost:8000"

    # OpenAI
    openai_api_key: str = ""
    llm_model: str = "gpt-5.2-2025-12-11"
    reasoning_level: str = "low"
    planning_reasoning_level: str = "medium"  # Higher reasoning for course planning

    # Database
    database_path: Path = Path(__file__).parent.parent / "data" / "courses.db"

    # Course generation settings
    # These are soft guidelines - LLM decides actual counts based on complexity
    target_active_ratio: float = 0.30  # 30% exercises/quizzes

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
