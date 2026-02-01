"""Parsed intent - LLM-extracted structure from natural language."""

from pydantic import BaseModel, Field
from enum import Enum


class Role(str, Enum):
    """Developer roles."""
    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "fullstack"
    DEVOPS = "devops"
    QA = "qa"
    DATA = "data"
    UNKNOWN = "unknown"


class Goal(str, Enum):
    """Learning goals."""
    ONBOARDING = "onboarding"  # General understanding
    FIX_BUG = "fix_bug"  # Need to fix something specific
    ADD_FEATURE = "add_feature"  # Need to extend functionality
    CODE_REVIEW = "code_review"  # Need to review/understand changes
    DEBUGGING = "debugging"  # Need to diagnose issues
    REFACTORING = "refactoring"  # Need to improve existing code


class Depth(str, Enum):
    """Course depth levels."""
    OVERVIEW = "overview"  # High-level understanding only
    MODERATE = "moderate"  # Working knowledge
    DEEP = "deep"  # In-depth understanding for modifications


class Urgency(str, Enum):
    """Time sensitivity."""
    LOW = "low"  # No deadline
    MEDIUM = "medium"  # Within a week
    HIGH = "high"  # Immediate/within days


class ParsedIntent(BaseModel):
    """
    Structure extracted from natural language intent by LLM.

    The Intent Parser analyzes the user's natural language description
    and extracts these structured fields.
    """
    role: Role = Field(..., description="Inferred developer role")
    goal: Goal = Field(..., description="Primary learning goal")
    focus_areas: list[str] = Field(
        default_factory=list,
        description="Specific areas/modules to focus on",
    )
    depth: Depth = Field(..., description="Required depth of understanding")
    urgency: Urgency = Field(..., description="Time sensitivity")
    key_questions: list[str] = Field(
        default_factory=list,
        description="Key questions the course should answer",
    )

    # Additional context extracted
    context: str | None = Field(
        None,
        description="Additional context about why the user needs this",
    )
    specific_files: list[str] | None = Field(
        None,
        description="Specific files mentioned by user",
    )
