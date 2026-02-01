"""Course Planner - creates course outline from intent and repository."""

import json
from openai import OpenAI

from config import settings
from src.models.request import CourseRequest
from src.models.intent import ParsedIntent, Goal, Depth
from src.models.course import Course, CourseModule, CompetencyLevel
from src.client.cortex import CortexClient


PLANNER_PROMPT = """You are a course planner for developer onboarding.

You need to create a course outline for a developer learning about a codebase.

## Repository Information
{repo_info}

## User's Intent
Role: {role}
Goal: {goal}
Focus Areas: {focus_areas}
Depth: {depth}
Urgency: {urgency}

Key Questions to Answer:
{key_questions}

## Focus Area Context
{focus_context}

## Competency Levels Available
0. Architecture - System design, module organization, data flow (ALWAYS INCLUDE unless skip_architecture=true)
1. Explain - Understand what code does
2. Navigate - Find relevant code
3. Trace - Follow execution flow
4. Modify - Make targeted changes
5. Extend - Add new features
6. Debug - Diagnose and fix issues

## Instructions
Create a course outline with {max_modules} modules maximum.
- ALWAYS start with Architecture (level 0) unless told to skip
- Include competency levels appropriate for the user's goal
- Each module should have a clear learning objective
- Order modules from foundational to advanced

Based on the goal:
- onboarding: Levels 0, 1, 2 (Architecture, Explain, Navigate)
- fix_bug: Levels 0, 1, 3, 6 (Architecture, Explain, Trace, Debug)
- add_feature: Levels 0, 1, 2, 4, 5 (Architecture, Explain, Navigate, Modify, Extend)
- code_review: Levels 0, 1, 3 (Architecture, Explain, Trace)
- debugging: Levels 0, 1, 3, 6 (Architecture, Explain, Trace, Debug)
- refactoring: Levels 0, 1, 3, 4 (Architecture, Explain, Trace, Modify)

Respond with ONLY valid JSON:
{{
    "title": "Course title",
    "description": "Brief course description",
    "modules": [
        {{
            "title": "Module title",
            "description": "What this module covers",
            "competency_level": 0-6,
            "learning_objectives": ["objective 1", "objective 2"],
            "key_files": ["path/to/file.py"],
            "estimated_minutes": 15
        }}
    ]
}}"""


class CoursePlanner:
    """
    Plans course structure based on user intent and repository.

    Uses LLM to:
    - Analyze repository structure via KnowledgeCortex
    - Create course outline with appropriate competency levels
    - Always include Architecture module (unless explicitly skipped)
    """

    def __init__(
        self,
        cortex_client: CortexClient,
        model: str | None = None,
        reasoning_level: str | None = None,
    ):
        self.cortex = cortex_client
        self.model = model or settings.llm_model
        self.reasoning_level = reasoning_level or settings.reasoning_level
        self.openai = OpenAI(api_key=settings.openai_api_key)

    def plan(
        self,
        request: CourseRequest,
        parsed_intent: ParsedIntent,
    ) -> Course:
        """
        Create a course outline based on request and parsed intent.

        Steps:
        1. Get repository architecture overview
        2. Get context for focus areas
        3. Ask LLM to create course outline
        4. Build Course object with modules
        """
        # 1. Get architecture overview
        arch = self.cortex.get_architecture_overview(request.repo_name)

        # 2. Get focus area context
        focus_context = []
        for area in parsed_intent.focus_areas:
            context = self.cortex.get_focus_area_context(
                request.repo_name,
                area,
                n_results=3,
            )
            focus_context.extend(context)

        # 3. Build prompt
        repo_info = f"""
Repository: {request.repo_name}
Language: {arch['language']}
Files: {arch['file_count']}
Summary: {arch['repo_summary'] or 'No summary available'}

Modules:
{self._format_modules(arch['modules'])}

Key Files:
{self._format_files(arch['key_files'])}
"""

        focus_context_str = self._format_focus_context(focus_context)

        prompt = PLANNER_PROMPT.format(
            repo_info=repo_info,
            role=parsed_intent.role.value,
            goal=parsed_intent.goal.value,
            focus_areas=", ".join(parsed_intent.focus_areas) or "General",
            depth=parsed_intent.depth.value,
            urgency=parsed_intent.urgency.value,
            key_questions="\n".join(f"- {q}" for q in parsed_intent.key_questions),
            focus_context=focus_context_str,
            max_modules=self._get_max_modules(parsed_intent),
        )

        # 4. Call LLM
        response = self.openai.chat.completions.create(
            model=self.model,
            reasoning_effort=self.reasoning_level,
            messages=[
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        # 5. Build Course object
        modules = []
        for i, m in enumerate(result["modules"]):
            module = CourseModule(
                title=m["title"],
                description=m["description"],
                competency_level=CompetencyLevel(m["competency_level"]),
                order=i,
                sections=[],  # Sections will be added by ContentGenerator
            )
            modules.append(module)

        course = Course(
            repo_name=request.repo_name,
            title=result["title"],
            description=result["description"],
            original_intent=request.intent,
            parsed_intent=parsed_intent,
            modules=modules,
        )

        return course

    def _format_modules(self, modules: list[dict]) -> str:
        if not modules:
            return "No modules detected"
        lines = []
        for m in modules:
            summary = m.get("summary", "No summary")[:100]
            lines.append(f"- {m['name']}: {summary}")
        return "\n".join(lines)

    def _format_files(self, files: list[dict]) -> str:
        if not files:
            return "No key files"
        lines = []
        for f in files[:10]:
            lines.append(f"- {f['path']} ({f.get('functions', 0)} functions)")
        return "\n".join(lines)

    def _format_focus_context(self, context: list[dict]) -> str:
        if not context:
            return "No specific focus area context"
        lines = []
        for c in context:
            lines.append(f"- [{c['type']}] {c['path']}: {c['summary'][:150]}...")
        return "\n".join(lines)

    def _get_max_modules(self, intent: ParsedIntent) -> int:
        """Determine max modules based on depth and urgency."""
        base = settings.max_modules

        # Reduce for overview depth
        if intent.depth == Depth.OVERVIEW:
            base = min(base, 4)

        # Reduce for high urgency
        if intent.urgency.value == "high":
            base = min(base, 5)

        return base
