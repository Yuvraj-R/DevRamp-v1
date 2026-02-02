import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Clock, Layers, Loader2 } from 'lucide-react'
import Header from '../components/layout/Header'
import { api } from '../api/client'

export default function Home() {
  const [githubUrl, setGithubUrl] = useState('')
  const [intent, setIntent] = useState('')
  const [loading, setLoading] = useState(false)
  const [courses, setCourses] = useState([])
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.getCourses()
      .then(data => setCourses(data.courses || []))
      .catch(() => {})
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!githubUrl.trim() || !intent.trim()) return

    setLoading(true)
    setError('')

    try {
      // Extract repo name and check if already ingested
      const repoName = githubUrl.trim().split('/').pop().replace('.git', '')
      const exists = await api.checkRepo(repoName)

      let result
      if (exists) {
        result = await api.startGenerate(repoName, intent.trim())
      } else {
        result = await api.startPipeline(githubUrl.trim(), intent.trim())
      }

      navigate(`/generate/${result.job_id}`)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />

      {/* Hero */}
      <main className="max-w-2xl mx-auto px-6 py-16">
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold text-gray-900 mb-3">
            Learn any codebase, fast.
          </h1>
          <p className="text-lg text-gray-500">
            Enter a GitHub repo and tell us what you need to learn.
          </p>
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          <div className="mb-5">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              GitHub Repository
            </label>
            <input
              type="text"
              value={githubUrl}
              onChange={(e) => setGithubUrl(e.target.value)}
              placeholder="https://github.com/username/repo"
              className="input"
              disabled={loading}
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              What do you need to learn?
            </label>
            <textarea
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              placeholder="I'm a backend dev joining the team. I need to understand the authentication flow because I'll be adding OAuth support."
              rows={4}
              className="input resize-none"
              disabled={loading}
            />
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-100 rounded-lg text-red-600 text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !githubUrl.trim() || !intent.trim()}
            className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Starting...
              </>
            ) : (
              <>
                Generate Course
                <ArrowRight className="w-5 h-5" />
              </>
            )}
          </button>
        </form>

        {/* Recent Courses */}
        {courses.length > 0 && (
          <div className="mt-12">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Courses</h2>
            <div className="grid gap-4">
              {courses.slice(0, 5).map(course => (
                <button
                  key={course.id}
                  onClick={() => navigate(`/course/${course.id}`)}
                  className="card text-left hover:border-[#FF6B35] group"
                >
                  <h3 className="font-medium text-gray-900 group-hover:text-[#FF6B35] transition-colors">
                    {course.title || course.repo_name}
                  </h3>
                  <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
                    <span className="flex items-center gap-1">
                      <Layers className="w-4 h-4" />
                      {course.repo_name}
                    </span>
                    {course.created_at && (
                      <span className="flex items-center gap-1">
                        <Clock className="w-4 h-4" />
                        {new Date(course.created_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
