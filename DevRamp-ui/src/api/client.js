const API_BASE = 'http://localhost:8001'
const CORTEX_BASE = 'http://localhost:8000'

// Retry configuration
const MAX_RETRIES = 3
const RETRY_DELAY = 2000

// Timeouts - course generation can take a long time
const THIRTY_MINUTES = 30 * 60 * 1000

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function request(endpoint, options = {}, retries = MAX_RETRIES) {
  const controller = new AbortController()
  const timeout = options.timeout || THIRTY_MINUTES // 30 min default

  const timeoutId = setTimeout(() => controller.abort(), timeout)

  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      signal: controller.signal,
      ...options,
    })

    clearTimeout(timeoutId)

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Request failed' }))
      throw new Error(error.detail || 'Request failed')
    }

    return res.json()
  } catch (err) {
    clearTimeout(timeoutId)

    // Retry on network errors or timeouts (not on 4xx/5xx)
    if (retries > 0 && (err.name === 'AbortError' || err.name === 'TypeError')) {
      console.log(`Retrying ${endpoint}, ${retries} attempts left...`)
      await sleep(RETRY_DELAY)
      return request(endpoint, options, retries - 1)
    }

    throw err
  }
}

// ============================================================================
// Active Jobs Persistence (localStorage)
// ============================================================================

const ACTIVE_JOBS_KEY = 'devramp_active_jobs'
const READ_COURSES_KEY = 'devramp_read_courses'

export function saveActiveJob(jobId, repoName, intent) {
  const jobs = getActiveJobs()
  // Remove existing job with same ID if any
  const filtered = jobs.filter(j => j.jobId !== jobId)
  filtered.unshift({
    jobId,
    repoName,
    intent,
    startedAt: Date.now(),
  })
  localStorage.setItem(ACTIVE_JOBS_KEY, JSON.stringify(filtered))
}

export function getActiveJobs() {
  try {
    const stored = localStorage.getItem(ACTIVE_JOBS_KEY)
    if (!stored) return []

    const jobs = JSON.parse(stored)
    // Filter out expired jobs (older than 2 hours)
    const now = Date.now()
    const valid = jobs.filter(job => now - job.startedAt < 2 * 60 * 60 * 1000)

    // Update storage if we filtered any
    if (valid.length !== jobs.length) {
      localStorage.setItem(ACTIVE_JOBS_KEY, JSON.stringify(valid))
    }

    return valid
  } catch {
    return []
  }
}

export function removeActiveJob(jobId) {
  const jobs = getActiveJobs()
  const filtered = jobs.filter(j => j.jobId !== jobId)
  localStorage.setItem(ACTIVE_JOBS_KEY, JSON.stringify(filtered))
}

export function clearActiveJobs() {
  localStorage.removeItem(ACTIVE_JOBS_KEY)
}

// Legacy single-job functions for backwards compatibility
export function getActiveJob() {
  const jobs = getActiveJobs()
  return jobs.length > 0 ? jobs[0] : null
}

export function clearActiveJob() {
  const job = getActiveJob()
  if (job) {
    removeActiveJob(job.jobId)
  }
}

// ============================================================================
// Read/Unread Course Tracking
// ============================================================================

export function markCourseRead(courseId) {
  const read = getReadCourses()
  if (!read.includes(courseId)) {
    read.push(courseId)
    localStorage.setItem(READ_COURSES_KEY, JSON.stringify(read))
  }
}

export function getReadCourses() {
  try {
    const stored = localStorage.getItem(READ_COURSES_KEY)
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

export function isCourseNew(courseId) {
  return !getReadCourses().includes(courseId)
}

// ============================================================================
// API Methods
// ============================================================================

export const api = {
  // Start course generation pipeline
  startPipeline: async (githubUrl, intent) => {
    const result = await request('/pipeline/start', {
      method: 'POST',
      body: JSON.stringify({ github_url: githubUrl, intent }),
      // This returns immediately with job_id, shouldn't take long
      timeout: 60000,
    })

    // Save job to localStorage
    const repoName = githubUrl.split('/').pop().replace('.git', '')
    saveActiveJob(result.job_id, repoName, intent)

    return result
  },

  // Start generation for already-ingested repo
  startGenerate: async (repoName, intent) => {
    const result = await request('/generate/start', {
      method: 'POST',
      body: JSON.stringify({ repo_name: repoName, intent }),
      timeout: 60000,
    })

    saveActiveJob(result.job_id, repoName, intent)
    return result
  },

  // Get job status (polling - should be quick)
  getJob: (jobId) => request(`/jobs/${jobId}`, { timeout: 30000 }),

  // List courses
  getCourses: () => request('/courses', { timeout: 60000 }),

  // Get single course (can be large)
  getCourse: (courseId) => request(`/courses/${courseId}`, { timeout: THIRTY_MINUTES }),

  // Get exercise
  getExercise: (exerciseId) => request(`/exercises/${exerciseId}`, { timeout: 60000 }),

  // Check if repo exists in KnowledgeCortex
  checkRepo: async (repoName) => {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000)

      const res = await fetch(`${CORTEX_BASE}/repos/${repoName}`, {
        signal: controller.signal,
      })

      clearTimeout(timeoutId)
      return res.ok
    } catch {
      return false
    }
  },
}
