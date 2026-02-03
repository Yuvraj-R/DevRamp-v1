"""Exercise Generator - creates quick knowledge checks."""

import json
from openai import OpenAI

from config import settings
from src.models.course import Course, CourseModule, Section, SectionType, CompetencyLevel
from src.models.exercise import Exercise, ExerciseType
from src.client.cortex import CortexClient


EXERCISE_PROMPT = """Create {num_exercises} quick exercise(s) for this module.

## Module Info
"{module_title}" (Level {competency_level})
Content covered: {content_summary}

## Learner Context
Role: {role} | Goal: {goal}

## Code to reference
{code_context}

## Exercise Rules
1. **Quick and practical** - should take 1-2 minutes to answer
2. **Test understanding, not memorization** - "Why does X work this way?" not "What line number is Y?"
3. **Use real code** when possible - snippets from the actual codebase
4. **One clear correct answer** - no trick questions

Exercise types by level:
- Architecture (0): multiple_choice about system design
- Explain (1): multiple_choice or fill_blank about what code does
- Navigate (2): "Where would you find X?" questions
- Trace (3): code_trace or ordering execution steps
- Modify (4): "How would you change X?" or find_the_bug
- Extend (5): multiple_choice about best approach
- Debug (6): find_the_bug or code_trace

Return JSON:
{{
    "exercises": [
        {{
            "type": "multiple_choice|code_trace|find_the_bug|fill_blank|ordering",
            "question": "Clear, direct question",
            "code_snippet": "actual code if needed (null if not)",
            "code_language": "python|javascript|etc",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "The right one",
            "explanation": "Why, in 1-2 sentences",
            "hints": ["One helpful hint"]
        }}
    ]
}}"""


class ExerciseGenerator:
    """Creates quick, practical exercises."""

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
        self._exercises: dict[str, Exercise] = {}

    def generate_exercises(self, course: Course) -> Course:
        """Add 1-2 exercises per module."""
        for module in course.modules:
            self._generate_module_exercises(course, module)
        course.calculate_stats()
        return course

    def get_exercise(self, exercise_id: str) -> Exercise | None:
        return self._exercises.get(exercise_id)

    def _generate_module_exercises(self, course: Course, module: CourseModule) -> None:
        """Generate exercises scaled to module size."""
        # Get code context from reading sections
        code_context = self._get_code_context(course.repo_name, module)
        content_summary = self._summarize_content(module)

        # Scale exercises to module size: ~1 exercise per 2-3 readings
        reading_count = len([s for s in module.sections if s.type == SectionType.READING])
        num_exercises = max(1, min(reading_count // 2, 4))  # 1-4 exercises

        prompt = EXERCISE_PROMPT.format(
            num_exercises=num_exercises,
            module_title=module.title,
            competency_level=module.competency_level.value,
            content_summary=content_summary,
            role=course.parsed_intent.role.value,
            goal=course.parsed_intent.goal.value,
            code_context=code_context,
        )

        response = self.openai.chat.completions.create(
            model=self.model,
            reasoning_effort=self.reasoning_level,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        for e in result["exercises"][:num_exercises]:
            exercise = Exercise(
                type=ExerciseType(e["type"]),
                competency_level=module.competency_level.value,
                question=e["question"],
                code_snippet=e.get("code_snippet"),
                code_language=e.get("code_language"),
                options=e.get("options"),
                correct_answer=e["correct_answer"],
                explanation=e["explanation"],
                hints=e.get("hints", [])[:2],  # Up to 2 hints
                difficulty="medium",
            )

            self._exercises[exercise.id] = exercise

            section = Section(
                type=SectionType.EXERCISE,
                title=f"Check: {e['question'][:40]}...",
                content=self._format_exercise(exercise),
                exercise_id=exercise.id,
                estimated_minutes=2,
            )
            module.sections.append(section)

    def _get_code_context(self, repo_name: str, module: CourseModule) -> str:
        """Get code snippets for exercises."""
        code_refs = []
        for section in module.sections:
            if section.type == SectionType.READING:
                code_refs.extend(section.code_references)

        if not code_refs:
            return "No specific code available"

        parts = []
        for ref in code_refs[:2]:
            try:
                if ref.node_type == "function":
                    func = self.cortex.get_function(repo_name, ref.path.split("::")[-1])
                    if func.body:
                        parts.append(f"```python\n{func.body[:300]}\n```")
                elif ref.node_type == "file":
                    file = self.cortex.get_file(repo_name, ref.path)
                    if file.content:
                        parts.append(f"```python\n{file.content[:300]}\n```")
            except Exception:
                continue

        return "\n\n".join(parts) if parts else "No code snippets available"

    def _summarize_content(self, module: CourseModule) -> str:
        """Brief summary of what was taught."""
        titles = [s.title for s in module.sections if s.type == SectionType.READING]
        return ", ".join(titles[:3]) if titles else module.description

    def _format_exercise(self, exercise: Exercise) -> str:
        """Format exercise for display."""
        parts = [f"**{exercise.question}**\n"]

        if exercise.code_snippet:
            lang = exercise.code_language or "python"
            parts.append(f"```{lang}\n{exercise.code_snippet}\n```\n")

        if exercise.options:
            for i, opt in enumerate(exercise.options):
                parts.append(f"{chr(65+i)}. {opt}")

        return "\n".join(parts)
