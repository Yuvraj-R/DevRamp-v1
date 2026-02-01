#!/usr/bin/env python3
"""Generate a course from natural language intent."""

import sys
sys.path.insert(0, '.')

from src.client.cortex import CortexClient
from src.generator.intent_parser import IntentParser
from src.generator.planner import CoursePlanner
from src.generator.content import ContentGenerator
from src.generator.exercises import ExerciseGenerator
from src.db.store import CourseStore
from src.models.request import CourseRequest


def main():
    # Initialize components
    cortex = CortexClient()
    intent_parser = IntentParser()
    planner = CoursePlanner(cortex)
    content_gen = ContentGenerator(cortex)
    exercise_gen = ExerciseGenerator(cortex)
    store = CourseStore()

    print("\n" + "=" * 70)
    print("  COURSE GENERATOR - Generate Personalized Learning Courses")
    print("=" * 70)

    # Get user input
    print("\nEnter the repository name (must be indexed in KnowledgeCortex):")
    repo_name = input("Repository: ").strip()

    print("\nDescribe what you need to learn (be specific about your role, goal, and focus):")
    print("Example: 'I'm a backend dev joining the team. I need to understand the")
    print("         payment processing flow because I'll be adding Stripe integration.'")
    intent = input("\nYour intent: ").strip()

    if not repo_name or not intent:
        print("Error: Both repository name and intent are required.")
        return

    # Create request
    request = CourseRequest(
        repo_name=repo_name,
        intent=intent,
    )

    print("\n" + "-" * 70)
    print("Generating course...")
    print("-" * 70)

    try:
        # Step 1: Parse intent
        print("\n1. Parsing your intent...")
        parsed_intent = intent_parser.parse(request)
        print(f"   Role: {parsed_intent.role.value}")
        print(f"   Goal: {parsed_intent.goal.value}")
        print(f"   Focus: {', '.join(parsed_intent.focus_areas) or 'General'}")
        print(f"   Depth: {parsed_intent.depth.value}")

        # Step 2: Plan course
        print("\n2. Planning course structure...")
        course = planner.plan(request, parsed_intent)
        print(f"   Title: {course.title}")
        print(f"   Modules: {len(course.modules)}")
        for m in course.modules:
            print(f"     - [{m.competency_level.name}] {m.title}")

        # Step 3: Generate content
        print("\n3. Generating reading content...")
        course = content_gen.generate_content(course)

        # Step 4: Generate exercises
        print("\n4. Generating exercises...")
        course = exercise_gen.generate_exercises(course)

        # Step 5: Save
        print("\n5. Saving course...")
        course_id = store.save(course)

        # Display result
        print("\n" + "=" * 70)
        print("COURSE GENERATED SUCCESSFULLY!")
        print("=" * 70)
        print(f"\nCourse ID: {course_id}")
        print(f"Title: {course.title}")
        print(f"Description: {course.description}")
        print(f"Estimated Time: {course.estimated_hours:.1f} hours")
        print(f"\nModules ({len(course.modules)}):")

        for m in course.modules:
            print(f"\n  [{m.competency_level.name}] {m.title}")
            print(f"  {m.description}")
            reading_count = len([s for s in m.sections if s.type.value == "reading"])
            exercise_count = len([s for s in m.sections if s.type.value in ("exercise", "quiz")])
            print(f"  Sections: {reading_count} reading, {exercise_count} exercises")

        print("\n" + "=" * 70)
        print(f"Stats: {course.total_readings} readings, {course.total_exercises} exercises")
        print("=" * 70)

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

    finally:
        cortex.close()


if __name__ == "__main__":
    main()
