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

    # Database
    database_path: Path = Path(__file__).parent.parent / "data" / "courses.db"

    # Course generation settings
    max_modules: int = 10
    max_sections_per_module: int = 8
    target_active_ratio: float = 0.30  # 30% exercises/quizzes

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
