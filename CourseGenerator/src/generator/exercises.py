"""Exercise Generator - creates exercises and quizzes for modules."""

import json
from openai import OpenAI

from config import settings
from src.models.course import Course, CourseModule, Section, SectionType, CompetencyLevel
from src.models.exercise import Exercise, ExerciseType
from src.client.cortex import CortexClient


EXERCISE_PROMPT = """You are creating learning exercises for developer onboarding.

## Context
Repository: {repo_name}
Module: {module_title}
Competency Level: {competency_level}
Module Content Summary: {content_summary}

## User Context
Role: {role}
Goal: {goal}

## Relevant Code
{code_context}

## Instructions
Create {num_exercises} exercises that test understanding of this module.

Exercise types to use based on competency level:
- 0 (Architecture): multiple_choice, match_pairs (match components to responsibilities)
- 1 (Explain): multiple_choice, fill_blank (complete explanation)
- 2 (Navigate): multiple_choice (where would you find X?)
- 3 (Trace): code_trace, ordering (order execution steps)
- 4 (Modify): fill_blank, find_the_bug
- 5 (Extend): multiple_choice (best approach to add X)
- 6 (Debug): find_the_bug, code_trace

Each exercise should:
- Use actual code from the repository when possible
- Have a clear correct answer
- Include an explanation of why the answer is correct
- Include 1-2 hints

Respond with ONLY valid JSON:
{{
    "exercises": [
        {{
            "type": "multiple_choice|code_trace|find_the_bug|fill_blank|match_pairs|ordering",
            "question": "The question or prompt",
            "code_snippet": "Optional code to analyze (null if not needed)",
            "code_language": "python|javascript|typescript (if code_snippet provided)",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "The correct option or answer",
            "explanation": "Why this is correct",
            "hints": ["Hint 1", "Hint 2"],
            "difficulty": "easy|medium|hard",
            "related_files": ["path/to/file.py"]
        }}
    ]
}}"""


class ExerciseGenerator:
    """
    Generates exercises and quizzes for course modules.

    Creates exercises that:
    - Match the competency level
    - Use actual code from the repository
    - Reinforce module content
    - Maintain 30% of total content
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
        self._exercises: dict[str, Exercise] = {}  # Store exercises by ID

    def generate_exercises(self, course: Course) -> Course:
        """
        Generate exercises for all modules in a course.

        Adds exercise sections to each module.
        """
        for module in course.modules:
            self._generate_module_exercises(course, module)

        course.calculate_stats()
        return course

    def get_exercise(self, exercise_id: str) -> Exercise | None:
        """Get an exercise by ID."""
        return self._exercises.get(exercise_id)

    def _generate_module_exercises(self, course: Course, module: CourseModule) -> None:
        """Generate exercises for a single module."""
        # Get code context for exercises
        code_context = self._get_code_context(course.repo_name, module)

        # Calculate number of exercises (target 30% active content)
        num_reading = len([s for s in module.sections if s.type == SectionType.READING])
        # For every ~2 reading sections, add 1 exercise
        num_exercises = max(1, (num_reading + 1) // 2)
        num_exercises = min(num_exercises, 3)  # Cap at 3 per module

        # Summarize content for context
        content_summary = self._summarize_module_content(module)

        # Build prompt
        prompt = EXERCISE_PROMPT.format(
            repo_name=course.repo_name,
            module_title=module.title,
            competency_level=module.competency_level.value,
            content_summary=content_summary,
            role=course.parsed_intent.role.value,
            goal=course.parsed_intent.goal.value,
            code_context=code_context,
            num_exercises=num_exercises,
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

        # Create exercises and sections
        for e in result["exercises"]:
            exercise = Exercise(
                type=ExerciseType(e["type"]),
                competency_level=module.competency_level.value,
                question=e["question"],
                code_snippet=e.get("code_snippet"),
                code_language=e.get("code_language"),
                options=e.get("options"),
                correct_answer=e["correct_answer"],
                explanation=e["explanation"],
                hints=e.get("hints", []),
                difficulty=e.get("difficulty", "medium"),
                related_files=e.get("related_files", []),
            )

            # Store exercise
            self._exercises[exercise.id] = exercise

            # Create section for the exercise
            section = Section(
                type=SectionType.EXERCISE,
                title=f"Exercise: {e['question'][:50]}...",
                content=self._format_exercise_content(exercise),
                exercise_id=exercise.id,
                estimated_minutes=5,
            )
            module.sections.append(section)

    def _get_code_context(self, repo_name: str, module: CourseModule) -> str:
        """Get relevant code for creating exercises."""
        # Use code references from reading sections
        code_refs = []
        for section in module.sections:
            if section.type == SectionType.READING:
                code_refs.extend(section.code_references)

        if not code_refs:
            return "No specific code context available"

        # Get actual code for up to 3 references
        code_parts = []
        for ref in code_refs[:3]:
            try:
                if ref.node_type == "function":
                    func = self.cortex.get_function(repo_name, ref.path.split("::")[-1])
                    if func.body:
                        code_parts.append(f"## {ref.path}\n```python\n{func.body[:500]}\n```")
                elif ref.node_type == "class":
                    cls = self.cortex.get_class(repo_name, ref.path.split("::")[-1])
                    if cls.body:
                        code_parts.append(f"## {ref.path}\n```python\n{cls.body[:500]}\n```")
                elif ref.node_type == "file":
                    file = self.cortex.get_file(repo_name, ref.path)
                    if file.content:
                        code_parts.append(f"## {ref.path}\n```python\n{file.content[:500]}\n```")
            except Exception:
                continue

        return "\n\n".join(code_parts) if code_parts else "No code available"

    def _summarize_module_content(self, module: CourseModule) -> str:
        """Create a brief summary of module content."""
        summaries = []
        for section in module.sections:
            if section.type == SectionType.READING:
                # Take first 200 chars of content
                summaries.append(f"- {section.title}: {section.content[:200]}...")
        return "\n".join(summaries[:5])

    def _format_exercise_content(self, exercise: Exercise) -> str:
        """Format exercise as Markdown content for display."""
        parts = [f"**{exercise.question}**\n"]

        if exercise.code_snippet:
            lang = exercise.code_language or "python"
            parts.append(f"```{lang}\n{exercise.code_snippet}\n```\n")

        if exercise.options:
            parts.append("Options:")
            for i, opt in enumerate(exercise.options):
                parts.append(f"  {chr(65+i)}. {opt}")
            parts.append("")

        return "\n".join(parts)
