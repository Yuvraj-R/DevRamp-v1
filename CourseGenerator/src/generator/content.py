"""Content Generator - writes practical learning content."""

import json
from openai import OpenAI

from config import settings
from src.models.course import Course, CourseModule, Section, SectionType, CodeReference, CompetencyLevel
from src.models.intent import ParsedIntent
from src.client.cortex import CortexClient


CONTENT_PROMPT = """Write {num_sections} learning sections for this module.

## Context
Repo: {repo_name}
Module: "{module_title}" (Level {competency_level}: {level_desc})
Learning goal: {description}

## What the learner cares about
Role: {role} | Goal: {goal}
Their questions: {key_questions}

## Relevant codebase info
{codebase_context}

## Section Guidelines

**Content depth per section:**
- Simple concepts: 150-250 words
- Core concepts: 250-400 words
- Complex topics: 400-600 words

**You decide the appropriate depth for each section.**

## Writing Rules

**Content rules:**
1. Be specific. Name actual files, functions, classes from THIS codebase.
2. Be practical. What do they need to know to do their job?
3. Be conversational. Write like you're explaining to a smart colleague.
4. Don't explain basics. They're developers - skip what they already know.
5. Connect the dots. Show how pieces relate to each other.

**Formatting rules (IMPORTANT - this renders as markdown):**
- Use **bold** for key terms, file names, and important concepts
- Use bullet points (`-`) for lists and steps
- Use `backticks` for code references: file paths, function names, class names
- Use code blocks with language tags for multi-line code:
  ```python
  def example():
      pass
  ```
- Use → arrows to show flow: `input()` → `process()` → `output()`
- Use headers (###) to break up longer sections
- Keep paragraphs SHORT (2-4 sentences max)

**Good example:**
```markdown
### How Requests Flow

When a request hits the API, it goes through several layers:

- **`server.py`** - Entry point, handles routing
- **`middleware/auth.py`** - Validates JWT tokens
- **`handlers/`** - Business logic lives here

The key insight: all handlers inherit from `BaseHandler`, which provides:

1. Automatic request validation
2. Error handling wrapper
3. Response serialization

```python
class UserHandler(BaseHandler):
    def get(self, user_id: str):
        return self.db.get_user(user_id)
```

This pattern means you rarely write boilerplate.
```

Return JSON:
{{
    "sections": [
        {{
            "title": "Section title (specific and actionable)",
            "content": "Well-formatted markdown content",
            "estimated_minutes": 3-8,
            "code_references": [
                {{"path": "src/actual/file.py", "node_type": "file", "context": "Why this matters"}}
            ]
        }}
    ]
}}"""


LEVEL_DESCRIPTIONS = {
    CompetencyLevel.ARCHITECTURE: "big picture - how the system is designed and pieces connect",
    CompetencyLevel.EXPLAIN: "understanding what the code does and why",
    CompetencyLevel.NAVIGATE: "finding your way around, knowing where things live",
    CompetencyLevel.TRACE: "following execution paths, understanding data flow",
    CompetencyLevel.MODIFY: "making changes safely, understanding dependencies",
    CompetencyLevel.EXTEND: "adding new features, following existing patterns",
    CompetencyLevel.DEBUG: "finding and fixing issues, understanding failure modes",
}


class ContentGenerator:
    """Generates practical learning content scaled to module needs."""

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
        """Generate content for all modules."""
        for module in course.modules:
            self._generate_module_content(course, module)
        course.calculate_stats()
        return course

    def _generate_module_content(self, course: Course, module: CourseModule) -> None:
        """Generate sections for a module based on its estimated complexity."""
        # Get context for this module
        codebase_context = self._get_module_context(
            course.repo_name, module, course.parsed_intent
        )

        # Use the planner's estimate, or default to 4
        num_sections = module.estimated_sections or 4

        prompt = CONTENT_PROMPT.format(
            num_sections=num_sections,
            repo_name=course.repo_name,
            module_title=module.title,
            competency_level=module.competency_level.value,
            level_desc=LEVEL_DESCRIPTIONS[module.competency_level],
            description=module.description,
            role=course.parsed_intent.role.value,
            goal=course.parsed_intent.goal.value,
            key_questions=", ".join(course.parsed_intent.key_questions[:5]),
            codebase_context=codebase_context,
        )

        response = self.openai.chat.completions.create(
            model=self.model,
            reasoning_effort=self.reasoning_level,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        # Add sections from LLM response
        for s in result["sections"]:
            code_refs = [
                CodeReference(
                    path=r["path"],
                    node_type=r["node_type"],
                    context=r.get("context", ""),
                )
                for r in s.get("code_references", [])[:5]  # Allow more references
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
        self, repo_name: str, module: CourseModule, intent: ParsedIntent
    ) -> str:
        """Get relevant context for the module."""
        query = f"{module.title} - {module.description}"

        try:
            # Try RAG query for rich context
            result = self.cortex.query(
                question=f"Explain in detail: {query}",
                repo_name=repo_name,
                n_context=5,  # More context
            )
            # Allow longer context for better content
            answer = result.answer[:800] if len(result.answer) > 800 else result.answer
            sources = [s['path'] for s in result.sources[:5]]
            return f"{answer}\n\nKey files: {sources}"
        except Exception:
            try:
                # Fallback to semantic search
                search_results = self.cortex.search(query, repo_name, n_results=5)
                return "\n".join(
                    f"- {r.path}: {r.summary[:150]}" for r in search_results
                )
            except Exception:
                return "No specific context available - use your knowledge of the codebase structure."
