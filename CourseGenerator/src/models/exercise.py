"""Exercise and quiz models."""

from enum import Enum
from pydantic import BaseModel, Field
import uuid


class ExerciseType(str, Enum):
    """Types of exercises."""
    MULTIPLE_CHOICE = "multiple_choice"  # Pick correct answer
    CODE_TRACE = "code_trace"  # Trace execution flow
    FIND_THE_BUG = "find_the_bug"  # Identify issue in code
    FILL_BLANK = "fill_blank"  # Complete code snippet
    MATCH_PAIRS = "match_pairs"  # Match concepts to code
    ORDERING = "ordering"  # Order execution steps


class Exercise(BaseModel):
    """An exercise or quiz question."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: ExerciseType
    competency_level: int = Field(..., ge=0, le=6)

    # Question content
    question: str = Field(..., description="The question or prompt")
    code_snippet: str | None = Field(None, description="Code to analyze")
    code_language: str | None = Field(None, description="Language of code snippet")

    # Answer options (for multiple choice, match pairs, ordering)
    options: list[str] | None = None

    # Correct answer
    correct_answer: str | list[str] = Field(
        ...,
        description="Correct answer(s) - string for single, list for multiple/ordering",
    )

    # Learning support
    explanation: str = Field(..., description="Explanation of the correct answer")
    hints: list[str] = Field(default_factory=list)

    # Difficulty and context
    difficulty: str = Field(
        "medium",
        pattern="^(easy|medium|hard)$",
    )
    related_files: list[str] = Field(
        default_factory=list,
        description="Files related to this exercise",
    )


class QuizResult(BaseModel):
    """Result of a quiz attempt."""
    exercise_id: str
    user_answer: str | list[str]
    is_correct: bool
    time_taken_seconds: int
    hints_used: int = 0
