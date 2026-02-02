"""Content Generator - writes concise, practical learning content."""

import json
from openai import OpenAI

from config import settings
from src.models.course import Course, CourseModule, Section, SectionType, CodeReference, CompetencyLevel
from src.models.intent import ParsedIntent
from src.client.cortex import CortexClient


CONTENT_PROMPT = """Write {num_sections} short learning sections for this module.

## Context
Repo: {repo_name}
Module: "{module_title}" (Level {competency_level}: {level_desc})
Learning goal: {description}

## What the learner cares about
Role: {role} | Goal: {goal}
Their questions: {key_questions}

## Relevant codebase info
{codebase_context}

## Writing rules - READ THESE
1. **Be concise.** Every sentence must teach something. No filler.
2. **Be specific.** Name actual files, functions, classes. No vague hand-waving.
3. **Be practical.** What do they need to know to do their job?
4. **Be conversational.** Write like you're explaining to a smart colleague, not writing a textbook.
5. **Skip the obvious.** Don't explain what a function is. They're developers.

Bad: "The authentication module handles user authentication and provides various authentication-related functionality."
Good: "Auth lives in `src/auth/`. Login flow: `authenticate()` validates creds → `create_session()` → returns JWT."

Each section should be 100-200 words MAX. If you can say it in fewer words, do it.

Return JSON:
{{
    "sections": [
        {{
            "title": "Punchy title",
            "content": "The actual content in markdown. Be concise!",
            "code_references": [
                {{"path": "src/example.py", "node_type": "file", "context": "Why this matters"}}
            ]
        }}
    ]
}}"""


LEVEL_DESCRIPTIONS = {
    CompetencyLevel.ARCHITECTURE: "big picture - how pieces connect",
    CompetencyLevel.EXPLAIN: "what the code does",
    CompetencyLevel.NAVIGATE: "finding your way around",
    CompetencyLevel.TRACE: "following execution paths",
    CompetencyLevel.MODIFY: "making changes safely",
    CompetencyLevel.EXTEND: "adding new stuff",
    CompetencyLevel.DEBUG: "finding and fixing issues",
}


class ContentGenerator:
    """Generates concise, practical learning content."""

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

    def generate_content(self, course: Course) -> Course:
        """Generate content for all modules. Keeps it tight."""
        for module in course.modules:
            self._generate_module_content(course, module)
        course.calculate_stats()
        return course

    def _generate_module_content(self, course: Course, module: CourseModule) -> None:
        """Generate 2-3 sections for a module. No more."""
        # Get context
        codebase_context = self._get_module_context(
            course.repo_name, module, course.parsed_intent
        )

        # 2-3 sections max
        num_sections = min(settings.max_sections_per_module, 3)

        prompt = CONTENT_PROMPT.format(
            num_sections=num_sections,
            repo_name=course.repo_name,
            module_title=module.title,
            competency_level=module.competency_level.value,
            level_desc=LEVEL_DESCRIPTIONS[module.competency_level],
            description=module.description,
            role=course.parsed_intent.role.value,
            goal=course.parsed_intent.goal.value,
            key_questions=", ".join(course.parsed_intent.key_questions[:3]),
            codebase_context=codebase_context,
        )

        response = self.openai.chat.completions.create(
            model=self.model,
            reasoning_effort=self.reasoning_level,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        for s in result["sections"][:num_sections]:
            code_refs = [
                CodeReference(
                    path=r["path"],
                    node_type=r["node_type"],
                    context=r.get("context", ""),
                )
                for r in s.get("code_references", [])[:3]
            ]

            section = Section(
                type=SectionType.READING,
                title=s["title"],
                content=s["content"],
                code_references=code_refs,
                estimated_minutes=3,  # Short sections = less time
            )
            module.sections.append(section)

    def _get_module_context(
        self, repo_name: str, module: CourseModule, intent: ParsedIntent
    ) -> str:
        """Get relevant context. Keep it brief."""
        query = f"{module.title} - {module.description}"

        try:
            result = self.cortex.query(
                question=f"Briefly explain: {query}",
                repo_name=repo_name,
                n_context=3,
            )
            # Truncate to avoid prompt bloat
            answer = result.answer[:500] if len(result.answer) > 500 else result.answer
            return f"{answer}\n\nKey files: {[s['path'] for s in result.sources[:3]]}"
        except Exception:
            try:
                search_results = self.cortex.search(query, repo_name, n_results=3)
                return "\n".join(
                    f"- {r.path}: {r.summary[:100]}" for r in search_results
                )
            except Exception:
                return "No specific context available"
