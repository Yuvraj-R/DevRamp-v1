"""Course structure models."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid

from .intent import ParsedIntent


class CompetencyLevel(int, Enum):
    """Competency levels for learning progression."""
    ARCHITECTURE = 0  # System design understanding
    EXPLAIN = 1  # Understand what code does
    NAVIGATE = 2  # Find relevant code
    TRACE = 3  # Follow execution flow
    MODIFY = 4  # Make targeted changes
    EXTEND = 5  # Add new features
    DEBUG = 6  # Diagnose and fix issues


class SectionType(str, Enum):
    """Types of course sections."""
    READING = "reading"  # Passive content
    EXERCISE = "exercise"  # Active practice
    QUIZ = "quiz"  # Knowledge check


class CodeReference(BaseModel):
    """Reference to code in KnowledgeCortex."""
    path: str = Field(..., description="File path or function/class path")
    node_type: str = Field(..., description="file, function, or class")
    context: str = Field(..., description="Why this code is referenced")
    line_start: int | None = None
    line_end: int | None = None


class Section(BaseModel):
    """A section within a course module."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: SectionType
    title: str
    content: str = Field(..., description="Markdown content")
    code_references: list[CodeReference] = Field(default_factory=list)
    estimated_minutes: int = Field(default=5)

    # For exercises/quizzes
    exercise_id: str | None = Field(None, description="ID of associated exercise")


class CourseModule(BaseModel):
    """A module within a course."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    description: str
    competency_level: CompetencyLevel
    order: int
    sections: list[Section] = Field(default_factory=list)

    @property
    def reading_sections(self) -> list[Section]:
        return [s for s in self.sections if s.type == SectionType.READING]

    @property
    def active_sections(self) -> list[Section]:
        return [s for s in self.sections if s.type in (SectionType.EXERCISE, SectionType.QUIZ)]

    @property
    def estimated_minutes(self) -> int:
        return sum(s.estimated_minutes for s in self.sections)


class Course(BaseModel):
    """A complete learning course."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    repo_name: str
    title: str
    description: str

    # User context
    original_intent: str = Field(..., description="User's original natural language intent")
    parsed_intent: ParsedIntent

    # Course content
    modules: list[CourseModule] = Field(default_factory=list)

    # Metadata
    estimated_hours: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Stats
    total_readings: int = 0
    total_exercises: int = 0
    total_quizzes: int = 0

    def calculate_stats(self) -> None:
        """Calculate course statistics from modules."""
        self.total_readings = sum(
            len(m.reading_sections) for m in self.modules
        )
        self.total_exercises = sum(
            len([s for s in m.sections if s.type == SectionType.EXERCISE])
            for m in self.modules
        )
        self.total_quizzes = sum(
            len([s for s in m.sections if s.type == SectionType.QUIZ])
            for m in self.modules
        )
        self.estimated_hours = sum(
            m.estimated_minutes for m in self.modules
        ) / 60.0
