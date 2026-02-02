const API_BASE = 'http://localhost:8001'

async function request(endpoint, options = {}) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || 'Request failed')
  }

  return res.json()
}

export const api = {
  // Start course generation pipeline
  startPipeline: (githubUrl, intent) =>
    request('/pipeline/start', {
      method: 'POST',
      body: JSON.stringify({ github_url: githubUrl, intent }),
    }),

  // Start generation for already-ingested repo
  startGenerate: (repoName, intent) =>
    request('/generate/start', {
      method: 'POST',
      body: JSON.stringify({ repo_name: repoName, intent }),
    }),

  // Get job status
  getJob: (jobId) => request(`/jobs/${jobId}`),

  // List courses
  getCourses: () => request('/courses'),

  // Get single course
  getCourse: (courseId) => request(`/courses/${courseId}`),

  // Get exercise
  getExercise: (exerciseId) => request(`/exercises/${exerciseId}`),

  // Check if repo exists in KnowledgeCortex
  checkRepo: async (repoName) => {
    try {
      const res = await fetch(`http://localhost:8000/repos/${repoName}`)
      return res.ok
    } catch {
      return false
    }
  },
}
