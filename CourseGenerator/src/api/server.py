"""FastAPI server for CourseGenerator."""

import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import settings
from src.models.request import CourseRequest
from src.models.course import Course
from src.client.cortex import CortexClient
from src.generator.intent_parser import IntentParser
from src.generator.planner import CoursePlanner
from src.generator.content import ContentGenerator
from src.generator.exercises import ExerciseGenerator
from src.db.store import CourseStore
from src.db.jobs import JobStore


# Initialize app
app = FastAPI(
    title="CourseGenerator API",
    description="API for generating personalized learning courses from code repositories",
    version="0.1.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global components
cortex_client: CortexClient = None
intent_parser: IntentParser = None
planner: CoursePlanner = None
content_gen: ContentGenerator = None
exercise_gen: ExerciseGenerator = None
store: CourseStore = None
job_store: JobStore = None


@app.on_event("startup")
async def startup():
    global cortex_client, intent_parser, planner, content_gen, exercise_gen, store, job_store
    cortex_client = CortexClient()
    intent_parser = IntentParser()
    planner = CoursePlanner(cortex_client)
    content_gen = ContentGenerator(cortex_client)
    exercise_gen = ExerciseGenerator(cortex_client)
    store = CourseStore()
    job_store = JobStore()


@app.on_event("shutdown")
async def shutdown():
    if cortex_client:
        cortex_client.close()


# ============================================================================
# Request/Response Models
# ============================================================================

class FullPipelineRequest(BaseModel):
    """Request for full pipeline: clone + ingest + generate."""
    github_url: str
    intent: str
    experience_level: str | None = None
    time_budget_hours: float | None = None
    focus_areas: list[str] | None = None


class JobResponse(BaseModel):
    """Response with job ID for tracking."""
    job_id: str
    status: str
    message: str


class GenerateResponse(BaseModel):
    """Response from course generation."""
    course_id: str
    title: str
    description: str
    estimated_hours: float
    module_count: int
    status: str = "completed"


# ============================================================================
# Background job runner
# ============================================================================

def run_full_pipeline(job_id: str, github_url: str, intent: str, **kwargs):
    """
    Full pipeline: clone repo → ingest to KnowledgeCortex → generate course.
    Updates job status at each step.
    """
    try:
        # Extract repo name from URL
        repo_name = github_url.rstrip("/").split("/")[-1].replace(".git", "")
        job_store.update_status(job_id, "cloning", f"Cloning {repo_name}...", repo_name=repo_name)

        # Step 1: Ingest repo into KnowledgeCortex
        job_store.update_status(job_id, "ingesting", f"Ingesting {repo_name} into knowledge base...")

        # Call KnowledgeCortex ingest endpoint
        with httpx.Client(timeout=300.0) as client:
            response = client.post(
                f"{settings.cortex_api_url}/repos/ingest",
                json={"repo_url": github_url, "repo_name": repo_name},
            )
            if response.status_code != 200:
                raise Exception(f"Ingest failed: {response.text}")

        # Wait for enrichment (summaries + embeddings) to complete
        # The ingest endpoint runs this in background, so we poll
        import time
        for _ in range(60):  # Wait up to 60 seconds
            time.sleep(2)
            try:
                repo_response = client.get(f"{settings.cortex_api_url}/repos/{repo_name}")
                if repo_response.status_code == 200:
                    repo_data = repo_response.json()
                    if repo_data.get("repository", {}).get("summary"):
                        break
            except Exception:
                pass

        # Step 2: Parse intent
        job_store.update_status(job_id, "parsing_intent", "Understanding your learning goals...")

        request = CourseRequest(
            repo_name=repo_name,
            intent=intent,
            experience_level=kwargs.get("experience_level"),
            time_budget_hours=kwargs.get("time_budget_hours"),
            focus_areas=kwargs.get("focus_areas"),
        )
        parsed_intent = intent_parser.parse(request)

        # Step 3: Plan course
        job_store.update_status(job_id, "planning", "Designing course structure...")
        course = planner.plan(request, parsed_intent)

        # Step 4: Generate content
        job_store.update_status(
            job_id, "generating_content",
            f"Writing content for {len(course.modules)} modules..."
        )
        course = content_gen.generate_content(course)

        # Step 5: Generate exercises
        job_store.update_status(job_id, "generating_exercises", "Creating exercises and quizzes...")
        course = exercise_gen.generate_exercises(course)

        # Step 6: Save
        job_store.update_status(job_id, "saving", "Saving course...")
        store.save(course)

        # Done!
        job_store.update_status(
            job_id, "completed",
            f"Course ready: {course.title}",
            course_id=course.id,
        )

    except Exception as e:
        job_store.update_status(job_id, "failed", f"Error: {str(e)}", error=str(e))


def run_generate_only(job_id: str, repo_name: str, intent: str, **kwargs):
    """
    Generate course for already-ingested repo.
    """
    try:
        job_store.update_status(job_id, "parsing_intent", "Understanding your learning goals...", repo_name=repo_name)

        request = CourseRequest(
            repo_name=repo_name,
            intent=intent,
            experience_level=kwargs.get("experience_level"),
            time_budget_hours=kwargs.get("time_budget_hours"),
            focus_areas=kwargs.get("focus_areas"),
        )
        parsed_intent = intent_parser.parse(request)

        job_store.update_status(job_id, "planning", "Designing course structure...")
        course = planner.plan(request, parsed_intent)

        job_store.update_status(
            job_id, "generating_content",
            f"Writing content for {len(course.modules)} modules..."
        )
        course = content_gen.generate_content(course)

        job_store.update_status(job_id, "generating_exercises", "Creating exercises and quizzes...")
        course = exercise_gen.generate_exercises(course)

        job_store.update_status(job_id, "saving", "Saving course...")
        store.save(course)

        job_store.update_status(
            job_id, "completed",
            f"Course ready: {course.title}",
            course_id=course.id,
        )

    except Exception as e:
        job_store.update_status(job_id, "failed", f"Error: {str(e)}", error=str(e))


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "CourseGenerator"}


@app.post("/pipeline/start", response_model=JobResponse)
async def start_pipeline(request: FullPipelineRequest, background_tasks: BackgroundTasks):
    """
    Start full pipeline: clone repo → ingest → generate course.
    Returns job ID for status tracking.
    """
    job_id = str(uuid.uuid4())[:8]

    # Create job
    job_store.create(job_id, request.github_url, request.intent)

    # Run in background
    background_tasks.add_task(
        run_full_pipeline,
        job_id,
        request.github_url,
        request.intent,
        experience_level=request.experience_level,
        time_budget_hours=request.time_budget_hours,
        focus_areas=request.focus_areas,
    )

    return JobResponse(
        job_id=job_id,
        status="pending",
        message="Pipeline started. Poll /jobs/{job_id} for status.",
    )


@app.post("/generate/start", response_model=JobResponse)
async def start_generate(request: CourseRequest, background_tasks: BackgroundTasks):
    """
    Start course generation for already-ingested repo.
    Returns job ID for status tracking.
    """
    job_id = str(uuid.uuid4())[:8]

    # Create job
    job_store.create(job_id, request.repo_name, request.intent)

    # Run in background
    background_tasks.add_task(
        run_generate_only,
        job_id,
        request.repo_name,
        request.intent,
        experience_level=request.experience_level,
        time_budget_hours=request.time_budget_hours,
        focus_areas=request.focus_areas,
    )

    return JobResponse(
        job_id=job_id,
        status="pending",
        message="Generation started. Poll /jobs/{job_id} for status.",
    )


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status with progress steps."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


@app.get("/jobs")
async def list_jobs(limit: int = 10):
    """List recent jobs."""
    return {"jobs": job_store.list_recent(limit)}


# Keep existing endpoints for direct access

@app.post("/courses/generate", response_model=GenerateResponse)
async def generate_course(request: CourseRequest):
    """
    Generate a personalized learning course (synchronous).
    For async with progress tracking, use /generate/start instead.
    """
    try:
        parsed_intent = intent_parser.parse(request)
        course = planner.plan(request, parsed_intent)
        course = content_gen.generate_content(course)
        course = exercise_gen.generate_exercises(course)
        store.save(course)

        return GenerateResponse(
            course_id=course.id,
            title=course.title,
            description=course.description,
            estimated_hours=course.estimated_hours,
            module_count=len(course.modules),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/courses")
async def list_courses(repo_name: str | None = None):
    """List all courses, optionally filtered by repository."""
    if repo_name:
        courses = store.list_by_repo(repo_name)
    else:
        courses = store.list_all()
    return {"courses": courses}


@app.get("/courses/{course_id}")
async def get_course(course_id: str):
    """Get a complete course by ID."""
    course = store.get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Course not found: {course_id}")
    return course.model_dump()


@app.delete("/courses/{course_id}")
async def delete_course(course_id: str):
    """Delete a course."""
    if not store.delete(course_id):
        raise HTTPException(status_code=404, detail=f"Course not found: {course_id}")
    return {"status": "deleted", "course_id": course_id}


@app.get("/courses/{course_id}/module/{module_index}")
async def get_module(course_id: str, module_index: int):
    """Get a specific module from a course."""
    course = store.get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Course not found: {course_id}")

    if module_index < 0 or module_index >= len(course.modules):
        raise HTTPException(status_code=404, detail=f"Module not found: {module_index}")

    return course.modules[module_index].model_dump()


@app.get("/exercises/{exercise_id}")
async def get_exercise(exercise_id: str):
    """Get an exercise by ID."""
    exercise = exercise_gen.get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail=f"Exercise not found: {exercise_id}")
    return exercise.model_dump()


# ============================================================================
# Static files for debug UI
# ============================================================================

# Serve debug UI
debug_dir = Path(__file__).parent.parent.parent / "debug"
if debug_dir.exists():
    app.mount("/static", StaticFiles(directory=debug_dir), name="static")

    @app.get("/")
    async def serve_ui():
        return FileResponse(debug_dir / "index.html")


# ============================================================================
# Run server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
