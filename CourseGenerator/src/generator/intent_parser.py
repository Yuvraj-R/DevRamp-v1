"""Intent Parser - extracts structured intent from natural language."""

import json
from openai import OpenAI

from config import settings
from src.models.request import CourseRequest
from src.models.intent import ParsedIntent, Role, Goal, Depth, Urgency


INTENT_PARSER_PROMPT = """You are an intent parser for a developer onboarding system.

Given a natural language description of what a developer needs to learn about a codebase,
extract structured information.

User's intent:
{intent}

{optional_context}

Extract the following (use the exact enum values provided):

1. role: The developer's role
   - backend, frontend, fullstack, devops, qa, data, unknown

2. goal: Their primary learning goal
   - onboarding (general understanding)
   - fix_bug (need to fix something)
   - add_feature (need to extend functionality)
   - code_review (need to review changes)
   - debugging (need to diagnose issues)
   - refactoring (need to improve existing code)

3. focus_areas: List of specific areas/modules/features to focus on (empty list if general)

4. depth: Required depth of understanding
   - overview (high-level only)
   - moderate (working knowledge)
   - deep (in-depth for modifications)

5. urgency: Time sensitivity
   - low (no deadline)
   - medium (within a week)
   - high (immediate/within days)

6. key_questions: List of 3-5 specific questions the course should answer

7. context: Any additional context about why they need this (optional)

8. specific_files: Any specific files mentioned (optional, empty list if none)

Respond with ONLY valid JSON matching this schema:
{{
    "role": "string",
    "goal": "string",
    "focus_areas": ["string"],
    "depth": "string",
    "urgency": "string",
    "key_questions": ["string"],
    "context": "string or null",
    "specific_files": ["string"] or null
}}"""


class IntentParser:
    """
    Parses natural language intent into structured ParsedIntent.

    Uses LLM to understand what the user needs and extract:
    - Role (backend, frontend, etc.)
    - Goal (onboarding, fix bug, add feature, etc.)
    - Focus areas
    - Depth of understanding needed
    - Urgency
    - Key questions to answer
    """

    def __init__(
        self,
        model: str | None = None,
        reasoning_level: str | None = None,
    ):
        self.model = model or settings.llm_model
        self.reasoning_level = reasoning_level or settings.reasoning_level
        self.openai = OpenAI(api_key=settings.openai_api_key)

    def parse(self, request: CourseRequest) -> ParsedIntent:
        """
        Parse a course request into structured intent.

        Uses the user's natural language intent plus any optional
        structured hints they provided.
        """
        # Build optional context from structured hints
        optional_parts = []
        if request.experience_level:
            optional_parts.append(f"Experience level: {request.experience_level}")
        if request.time_budget_hours:
            optional_parts.append(f"Time budget: {request.time_budget_hours} hours")
        if request.focus_areas:
            optional_parts.append(f"Requested focus areas: {', '.join(request.focus_areas)}")

        optional_context = ""
        if optional_parts:
            optional_context = "Additional context from user:\n" + "\n".join(optional_parts)

        prompt = INTENT_PARSER_PROMPT.format(
            intent=request.intent,
            optional_context=optional_context,
        )

        response = self.openai.chat.completions.create(
            model=self.model,
            reasoning_effort=self.reasoning_level,
            messages=[
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        # Parse the JSON response
        result = json.loads(response.choices[0].message.content)

        # Convert to ParsedIntent with proper enums
        return ParsedIntent(
            role=Role(result["role"]),
            goal=Goal(result["goal"]),
            focus_areas=result.get("focus_areas", []),
            depth=Depth(result["depth"]),
            urgency=Urgency(result["urgency"]),
            key_questions=result.get("key_questions", []),
            context=result.get("context"),
            specific_files=result.get("specific_files"),
        )
