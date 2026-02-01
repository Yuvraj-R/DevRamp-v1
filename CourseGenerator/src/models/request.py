"""Course request models - user input for course generation."""

from pydantic import BaseModel, Field


class CourseRequest(BaseModel):
    """
    User request for course generation.

    The primary input is natural language `intent` - users describe what they need
    and the LLM extracts structure from it.

    Example:
        CourseRequest(
            repo_name="LiveEngine",
            intent="I'm a backend dev joining the team. I need to understand the
                    payment processing flow because I'll be adding Stripe integration."
        )
    """
    repo_name: str = Field(..., description="Name of the repository in KnowledgeCortex")
    intent: str = Field(
        ...,
        description="Natural language description of what the user needs to learn",
        min_length=10,
    )

    # Optional structured hints - LLM uses these if provided, infers otherwise
    experience_level: str | None = Field(
        None,
        description="Optional: junior, mid, or senior",
        pattern="^(junior|mid|senior)$",
    )
    time_budget_hours: float | None = Field(
        None,
        description="Optional: how many hours the user has for learning",
        gt=0,
        le=40,
    )
    focus_areas: list[str] | None = Field(
        None,
        description="Optional: specific modules/features to focus on",
    )
    skip_architecture: bool = Field(
        False,
        description="Set to true for high-level overview only (skips Architecture module)",
    )
