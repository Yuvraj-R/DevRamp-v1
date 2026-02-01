"""Course storage using SQLite."""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

from config import settings
from src.models.course import Course


class CourseStore:
    """
    SQLite-based storage for generated courses.

    Stores courses as JSON blobs for simplicity.
    Can be upgraded to proper relational schema if needed.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.database_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS courses (
                    id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    original_intent TEXT NOT NULL,
                    data JSON NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_courses_repo
                ON courses(repo_name)
            """)

    def save(self, course: Course) -> str:
        """Save a course and return its ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO courses (id, repo_name, title, original_intent, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    course.id,
                    course.repo_name,
                    course.title,
                    course.original_intent,
                    course.model_dump_json(),
                    course.created_at.isoformat(),
                ),
            )
        return course.id

    def get(self, course_id: str) -> Course | None:
        """Get a course by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT data FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()

        if not row:
            return None

        return Course.model_validate_json(row["data"])

    def list_by_repo(self, repo_name: str) -> list[dict]:
        """List all courses for a repository."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, title, original_intent, created_at
                FROM courses
                WHERE repo_name = ?
                ORDER BY created_at DESC
                """,
                (repo_name,),
            ).fetchall()

        return [dict(row) for row in rows]

    def list_all(self) -> list[dict]:
        """List all courses."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, repo_name, title, original_intent, created_at
                FROM courses
                ORDER BY created_at DESC
                """,
            ).fetchall()

        return [dict(row) for row in rows]

    def delete(self, course_id: str) -> bool:
        """Delete a course."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "DELETE FROM courses WHERE id = ?",
                (course_id,),
            )
        return result.rowcount > 0
