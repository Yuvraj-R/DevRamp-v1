"""Course Planner - creates course outline from intent and repository."""

import json
from openai import OpenAI

from config import settings
from src.models.request import CourseRequest
from src.models.intent import ParsedIntent, Goal, Depth
from src.models.course import Course, CourseModule, CompetencyLevel
from src.client.cortex import CortexClient


PLANNER_PROMPT = """You're designing an onboarding course for a developer. Your job is to create a course outline that **matches the complexity and size of the codebase**.

## The Codebase
{repo_info}

## Who's Learning
Role: {role} | Goal: {goal} | Depth: {depth}
Focus: {focus_areas}

Key questions they need answered:
{key_questions}

## Relevant Code Areas
{focus_context}

## Module Count Guidelines

**Base your module count on codebase complexity, not arbitrary limits:**

| Codebase Size | Suggested Modules | Reasoning |
|---------------|-------------------|-----------|
| Tiny (<20 files) | 2-3 modules | Quick overview is enough |
| Small (20-50 files) | 3-5 modules | Cover main concepts |
| Medium (50-200 files) | 5-8 modules | Multiple subsystems to learn |
| Large (200-500 files) | 8-12 modules | Many components and patterns |
| Very Large (500+ files) | 10-15 modules | Complex system requires thorough coverage |

**However, complexity matters more than file count:**
- A 30-file codebase with complex algorithms may need 6+ modules
- A 500-file codebase with repetitive CRUD may need only 8 modules
- Framework codebases (React, Django, etc.) need MORE modules due to conceptual depth

## Competency Levels

Pick levels that match their goal:
- 0: Architecture (system design, how pieces connect) - **Always include this first**
- 1: Explain (what does this code do?)
- 2: Navigate (where do I find X?)
- 3: Trace (follow the execution path)
- 4: Modify (how to change things safely)
- 5: Extend (adding new features)
- 6: Debug (finding and fixing issues)

Goal → Level mapping:
- onboarding: 0, 1, 2, 3 (understand the lay of the land, trace key flows)
- fix_bug/debugging: 0, 3, 6 (find it, trace it, fix it)
- add_feature: 0, 2, 4, 5 (find where, modify, extend)
- code_review: 0, 1, 3 (understand structure and flow)
- refactoring: 0, 3, 4 (trace dependencies, modify safely)

## Your Task

Design a course outline with the **appropriate number of modules** for this codebase.

**Rules:**
1. **Architecture module is always first** (level 0) - gives the big picture
2. **Cover all major subsystems** - don't leave gaps
3. **Be specific** - "Authentication Flow" not "Security Stuff"
4. **Include practical modules** - they need to actually DO things, not just read

Return JSON:
{{
    "title": "Descriptive course title",
    "description": "One sentence describing what they'll learn",
    "modules": [
        {{
            "title": "Module title (be specific to this codebase)",
            "description": "What they'll learn and why it matters",
            "competency_level": 0-6,
            "key_files": ["2-4 most important files for this module"],
            "estimated_sections": 3-7
        }}
    ]
}}"""


class CoursePlanner:
    """Plans course structure based on codebase complexity."""

    def __init__(
        self,
        cortex_client: CortexClient,
        model: str | None = None,
        reasoning_level: str | None = None,
    ):
        self.cortex = cortex_client
        self.model = model or settings.llm_model
        # Use higher reasoning for planning decisions
        self.reasoning_level = reasoning_level or settings.planning_reasoning_level
        self.openai = OpenAI(api_key=settings.openai_api_key)

    def plan(
        self,
        request: CourseRequest,
        parsed_intent: ParsedIntent,
    ) -> Course:
        """Create a course outline scaled to codebase complexity."""
        # Get repo info
        arch = self.cortex.get_architecture_overview(request.repo_name)

        # Get focus area context
        focus_context = []
        for area in parsed_intent.focus_areas[:5]:  # Allow more focus areas
            context = self.cortex.get_focus_area_context(
                request.repo_name, area, n_results=3
            )
            focus_context.extend(context)

        file_count = arch.get('file_count', 50)
        size_category = self._categorize_size(file_count)

        # Build rich repo info for the LLM
        repo_info = f"""
Name: {request.repo_name}
Language: {arch.get('language', 'unknown')}
Size: {file_count} files ({size_category})
Summary: {(arch.get('repo_summary') or 'No summary available')[:500]}

Modules/directories: {', '.join(m.get('name', '') for m in arch.get('modules', [])[:10])}
"""

        prompt = PLANNER_PROMPT.format(
            repo_info=repo_info,
            role=parsed_intent.role.value,
            goal=parsed_intent.goal.value,
            depth=parsed_intent.depth.value,
            focus_areas=", ".join(parsed_intent.focus_areas) or "General overview",
            key_questions="\n".join(f"- {q}" for q in parsed_intent.key_questions[:5]),
            focus_context=self._format_focus_context(focus_context),
        )

        # Get plan from LLM with medium reasoning
        response = self.openai.chat.completions.create(
            model=self.model,
            reasoning_effort=self.reasoning_level,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        # Build Course object - no hard cap, use what LLM suggests
        modules = []
        for i, m in enumerate(result["modules"]):
            module = CourseModule(
                title=m["title"],
                description=m["description"],
                competency_level=CompetencyLevel(m["competency_level"]),
                order=i,
                sections=[],
                # Store estimated sections for content generator
                estimated_sections=m.get("estimated_sections", 4),
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

    def _categorize_size(self, file_count: int) -> str:
        """Categorize codebase size for the prompt."""
        if file_count < 20:
            return "tiny"
        elif file_count < 50:
            return "small"
        elif file_count < 200:
            return "medium"
        elif file_count < 500:
            return "large"
        else:
            return "very large"

    def _format_focus_context(self, context: list[dict]) -> str:
        if not context:
            return "No specific context available"
        lines = []
        for c in context[:8]:  # More context
            lines.append(f"- {c['path']}: {c.get('summary', '')[:150]}")
        return "\n".join(lines)
