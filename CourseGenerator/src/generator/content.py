"""Content Generator - generates reading sections for modules."""

import json
from openai import OpenAI

from config import settings
from src.models.course import Course, CourseModule, Section, SectionType, CodeReference, CompetencyLevel
from src.models.intent import ParsedIntent
from src.client.cortex import CortexClient


CONTENT_PROMPT = """You are a technical writer creating onboarding content for developers.

## Context
Repository: {repo_name}
Module: {module_title}
Competency Level: {competency_level} - {level_description}
Learning Objectives: {objectives}

## User Context
Role: {role}
Goal: {goal}
Key Questions: {key_questions}

## Codebase Information
{codebase_context}

## Instructions
Create {num_reading_sections} reading sections for this module.
Each section should:
- Be clear and concise
- Reference actual code from the repository
- Match the competency level
- Help answer the user's key questions
- Use Markdown formatting

For competency level descriptions:
- 0 (Architecture): Explain system design, module structure, data flow
- 1 (Explain): Describe what specific code does and why
- 2 (Navigate): Show how to find relevant code for tasks
- 3 (Trace): Walk through execution paths step by step
- 4 (Modify): Explain how to make changes safely
- 5 (Extend): Guide adding new functionality
- 6 (Debug): Teach debugging techniques for this codebase

Respond with ONLY valid JSON:
{{
    "sections": [
        {{
            "title": "Section title",
            "content": "Markdown content with code references",
            "code_references": [
                {{
                    "path": "path/to/file.py",
                    "node_type": "file|function|class",
                    "context": "Why this code is referenced"
                }}
            ],
            "estimated_minutes": 5
        }}
    ]
}}"""


LEVEL_DESCRIPTIONS = {
    CompetencyLevel.ARCHITECTURE: "Understanding system design and structure",
    CompetencyLevel.EXPLAIN: "Understanding what code does",
    CompetencyLevel.NAVIGATE: "Finding relevant code",
    CompetencyLevel.TRACE: "Following execution flow",
    CompetencyLevel.MODIFY: "Making targeted changes",
    CompetencyLevel.EXTEND: "Adding new features",
    CompetencyLevel.DEBUG: "Diagnosing and fixing issues",
}


class ContentGenerator:
    """
    Generates reading content for course modules.

    Uses LLM to create educational content that:
    - Explains concepts at the appropriate competency level
    - References actual code from the repository
    - Answers the user's key questions
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

    def generate_content(self, course: Course) -> Course:
        """
        Generate reading content for all modules in a course.

        Modifies course in-place, adding sections to each module.
        Maintains 70/30 passive/active ratio.
        """
        for module in course.modules:
            self._generate_module_content(course, module)

        course.calculate_stats()
        return course

    def _generate_module_content(self, course: Course, module: CourseModule) -> None:
        """Generate content for a single module."""
        # Get relevant context from KnowledgeCortex
        codebase_context = self._get_module_context(
            course.repo_name,
            module,
            course.parsed_intent,
        )

        # Calculate section counts for 70/30 ratio
        # We'll have ContentGenerator do reading, ExerciseGenerator do exercises
        num_reading_sections = min(
            int(settings.max_sections_per_module * 0.7),
            5,  # Cap at 5 reading sections
        )

        # Build prompt
        prompt = CONTENT_PROMPT.format(
            repo_name=course.repo_name,
            module_title=module.title,
            competency_level=module.competency_level.value,
            level_description=LEVEL_DESCRIPTIONS[module.competency_level],
            objectives=module.description,
            role=course.parsed_intent.role.value,
            goal=course.parsed_intent.goal.value,
            key_questions="\n".join(f"- {q}" for q in course.parsed_intent.key_questions),
            codebase_context=codebase_context,
            num_reading_sections=num_reading_sections,
        )

        # Call LLM
        response = self.openai.chat.completions.create(
            model=self.model,
            reasoning_effort=self.reasoning_level,
            messages=[
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        # Create sections
        for s in result["sections"]:
            code_refs = [
                CodeReference(
                    path=r["path"],
                    node_type=r["node_type"],
                    context=r["context"],
                )
                for r in s.get("code_references", [])
            ]

            section = Section(
                type=SectionType.READING,
                title=s["title"],
                content=s["content"],
                code_references=code_refs,
                estimated_minutes=s.get("estimated_minutes", 5),
            )
            module.sections.append(section)

    def _get_module_context(
        self,
        repo_name: str,
        module: CourseModule,
        intent: ParsedIntent,
    ) -> str:
        """Get relevant codebase context for a module."""
        # Query KnowledgeCortex for relevant information
        query = f"""
        For the module "{module.title}" focusing on {LEVEL_DESCRIPTIONS[module.competency_level]},
        what are the key components, files, and concepts I should cover?
        Focus areas: {', '.join(intent.focus_areas) or 'general'}
        """

        try:
            result = self.cortex.query(
                question=query,
                repo_name=repo_name,
                n_context=5,
            )
            return f"Answer: {result.answer}\n\nSources: {result.sources}"
        except Exception as e:
            # Fallback to search
            try:
                search_results = self.cortex.search(
                    query=module.title,
                    repo_name=repo_name,
                    n_results=5,
                )
                lines = []
                for r in search_results:
                    lines.append(f"- [{r.node_type}] {r.path}: {r.summary[:200]}")
                return "\n".join(lines)
            except Exception:
                return "No specific context available"
