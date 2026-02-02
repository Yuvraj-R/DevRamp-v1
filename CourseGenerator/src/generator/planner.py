"""Course Planner - creates course outline from intent and repository."""

import json
from openai import OpenAI

from config import settings
from src.models.request import CourseRequest
from src.models.intent import ParsedIntent, Goal, Depth
from src.models.course import Course, CourseModule, CompetencyLevel
from src.client.cortex import CortexClient


PLANNER_PROMPT = """You're designing a quick onboarding course. Be ruthlessly concise.

## The Codebase
{repo_info}

## Who's Learning
Role: {role} | Goal: {goal} | Depth: {depth}
Focus: {focus_areas}

Key questions they need answered:
{key_questions}

## Relevant Code Areas
{focus_context}

## Your Job
Create a TIGHT course outline. Rules:

1. **{max_modules} modules MAXIMUM** - probably fewer. Small codebase = fewer modules.
2. **Start with Architecture** (level 0) unless they just want a quick overview
3. **No fluff** - every module must teach something essential
4. **Be practical** - what do they actually need to know to do their job?

Competency levels (pick what fits their goal):
- 0: Architecture (system design, how pieces connect)
- 1: Explain (what does this code do?)
- 2: Navigate (where do I find X?)
- 3: Trace (follow the execution path)
- 4: Modify (how to change things safely)
- 5: Extend (adding new features)
- 6: Debug (finding and fixing issues)

Goal → Level mapping:
- onboarding: 0, 1, 2 (understand the lay of the land)
- fix_bug/debugging: 0, 3, 6 (find it, trace it, fix it)
- add_feature: 0, 2, 4, 5 (find where, modify, extend)
- code_review: 0, 1, 3 (understand structure and flow)
- refactoring: 0, 3, 4 (trace dependencies, modify safely)

Return JSON only:
{{
    "title": "Short, punchy title",
    "description": "One sentence max",
    "modules": [
        {{
            "title": "Module title (be specific)",
            "description": "What they'll learn (one line)",
            "competency_level": 0-6,
            "key_files": ["the 2-3 most important files"]
        }}
    ]
}}"""


class CoursePlanner:
    """Plans course structure. Keeps it tight and practical."""

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
        """Create a lean course outline."""
        # Get repo info
        arch = self.cortex.get_architecture_overview(request.repo_name)

        # Get focus area context
        focus_context = []
        for area in parsed_intent.focus_areas[:3]:  # Limit to top 3
            context = self.cortex.get_focus_area_context(
                request.repo_name, area, n_results=2
            )
            focus_context.extend(context)

        # Determine max modules based on codebase size
        file_count = arch.get('file_count', 50)
        max_modules = self._get_max_modules(file_count, parsed_intent)

        # Build prompt
        repo_info = f"""
Name: {request.repo_name}
Language: {arch.get('language', 'unknown')}
Size: {file_count} files ({"small" if file_count < 30 else "medium" if file_count < 100 else "large"})
Summary: {(arch.get('repo_summary') or 'No summary')[:300]}

Key modules: {', '.join(m.get('name', '') for m in arch.get('modules', [])[:5])}
"""

        prompt = PLANNER_PROMPT.format(
            repo_info=repo_info,
            role=parsed_intent.role.value,
            goal=parsed_intent.goal.value,
            depth=parsed_intent.depth.value,
            focus_areas=", ".join(parsed_intent.focus_areas) or "General overview",
            key_questions="\n".join(f"- {q}" for q in parsed_intent.key_questions[:4]),
            focus_context=self._format_focus_context(focus_context),
            max_modules=max_modules,
        )

        # Get plan from LLM
        response = self.openai.chat.completions.create(
            model=self.model,
            reasoning_effort=self.reasoning_level,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        # Build Course object
        modules = []
        for i, m in enumerate(result["modules"][:max_modules]):
            module = CourseModule(
                title=m["title"],
                description=m["description"],
                competency_level=CompetencyLevel(m["competency_level"]),
                order=i,
                sections=[],
            )
            modules.append(module)

        return Course(
            repo_name=request.repo_name,
            title=result["title"],
            description=result["description"],
            original_intent=request.intent,
            parsed_intent=parsed_intent,
            modules=modules,
        )

    def _get_max_modules(self, file_count: int, intent: ParsedIntent) -> int:
        """Fewer files = fewer modules. Simple."""
        if file_count < 20:
            base = 2
        elif file_count < 50:
            base = 3
        elif file_count < 100:
            base = 4
        else:
            base = settings.max_modules

        # Quick overview = even fewer
        if intent.depth.value == "overview":
            base = min(base, 2)

        return base

    def _format_focus_context(self, context: list[dict]) -> str:
        if not context:
            return "No specific context"
        lines = []
        for c in context[:5]:
            lines.append(f"- {c['path']}: {c.get('summary', '')[:100]}")
        return "\n".join(lines)
