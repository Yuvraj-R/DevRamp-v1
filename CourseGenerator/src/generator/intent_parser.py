"""Intent Parser - extracts structured intent from natural language."""

import json
from openai import OpenAI

from config import settings
from src.models.request import CourseRequest
from src.models.intent import ParsedIntent, Role, Goal, Depth, Urgency


INTENT_PARSER_PROMPT = """Parse this developer's learning intent. Be concise.

What they said:
"{intent}"
{optional_context}

Extract (use exact enum values):

role: backend | frontend | fullstack | devops | qa | data | unknown
goal: onboarding | fix_bug | add_feature | code_review | debugging | refactoring
focus_areas: specific things they mentioned (2-3 max, empty if general)
depth: overview | moderate | deep
urgency: low | medium | high
key_questions: 2-3 specific questions to answer (not generic fluff)

Return JSON only:
{{
    "role": "string",
    "goal": "string",
    "focus_areas": ["max 3 items"],
    "depth": "string",
    "urgency": "string",
    "key_questions": ["2-3 specific questions"]
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

        # Convert to ParsedIntent with proper enums, enforce limits
        return ParsedIntent(
            role=Role(result["role"]),
            goal=Goal(result["goal"]),
            focus_areas=result.get("focus_areas", [])[:3],  # Max 3
            depth=Depth(result["depth"]),
            urgency=Urgency(result["urgency"]),
            key_questions=result.get("key_questions", [])[:3],  # Max 3
            context=result.get("context"),
            specific_files=result.get("specific_files"),
        )
