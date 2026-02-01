"""Job tracking for course generation progress."""

import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path

from config import settings


class JobStatus(str, Enum):
    PENDING = "pending"
    CLONING = "cloning"
    INGESTING = "ingesting"
    PARSING_INTENT = "parsing_intent"
    PLANNING = "planning"
    GENERATING_CONTENT = "generating_content"
    GENERATING_EXERCISES = "generating_exercises"
    SAVING = "saving"
    COMPLETED = "completed"
    FAILED = "failed"


JOB_STEPS = [
    ("pending", "Waiting to start..."),
    ("cloning", "Cloning repository..."),
    ("ingesting", "Ingesting into KnowledgeCortex..."),
    ("parsing_intent", "Understanding your intent..."),
    ("planning", "Planning course structure..."),
    ("generating_content", "Writing content..."),
    ("generating_exercises", "Creating exercises..."),
    ("saving", "Saving course..."),
    ("completed", "Done!"),
]


class JobStore:
    """Track course generation job progress."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.database_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    repo_url TEXT NOT NULL,
                    repo_name TEXT,
                    intent TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    status_message TEXT,
                    course_id TEXT,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def create(self, job_id: str, repo_url: str, intent: str) -> str:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, repo_url, intent, status, status_message)
                VALUES (?, ?, ?, 'pending', 'Waiting to start...')
                """,
                (job_id, repo_url, intent),
            )
        return job_id

    def update_status(
        self,
        job_id: str,
        status: str,
        message: str | None = None,
        repo_name: str | None = None,
        course_id: str | None = None,
        error: str | None = None,
    ):
        with sqlite3.connect(self.db_path) as conn:
            if repo_name:
                conn.execute(
                    "UPDATE jobs SET repo_name = ?, updated_at = ? WHERE id = ?",
                    (repo_name, datetime.utcnow().isoformat(), job_id),
                )
            if course_id:
                conn.execute(
                    "UPDATE jobs SET course_id = ?, updated_at = ? WHERE id = ?",
                    (course_id, datetime.utcnow().isoformat(), job_id),
                )
            if error:
                conn.execute(
                    "UPDATE jobs SET error = ?, updated_at = ? WHERE id = ?",
                    (error, datetime.utcnow().isoformat(), job_id),
                )
            conn.execute(
                """
                UPDATE jobs SET status = ?, status_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, message or status, datetime.utcnow().isoformat(), job_id),
            )

    def get(self, job_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if not row:
            return None

        job = dict(row)
        # Add step index for progress bar
        status = job["status"]
        step_index = next(
            (i for i, (s, _) in enumerate(JOB_STEPS) if s == status),
            0
        )
        job["step_index"] = step_index
        job["total_steps"] = len(JOB_STEPS)
        job["steps"] = [
            {"status": s, "label": label, "completed": i < step_index, "current": i == step_index}
            for i, (s, label) in enumerate(JOB_STEPS)
        ]
        return job

    def list_recent(self, limit: int = 10) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, repo_url, repo_name, intent, status, status_message,
                       course_id, error, created_at
                FROM jobs ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
