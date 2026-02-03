import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Plus, Loader2, Sparkles, XCircle, BookOpen, Clock } from 'lucide-react'
import { api, getActiveJobs, markCourseRead, isCourseNew } from '../../api/client'

function formatRelativeTime(dateString) {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const [courses, setCourses] = useState([])
  const [activeJobs, setActiveJobs] = useState([])
  const [loading, setLoading] = useState(true)

  // Fetch courses and active jobs
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [coursesData, jobs] = await Promise.all([
          api.getCourses().catch(() => ({ courses: [] })),
          Promise.resolve(getActiveJobs()),
        ])
        setCourses(coursesData.courses || [])
        setActiveJobs(jobs)
      } catch (err) {
        console.error('Failed to fetch sidebar data:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchData()

    // Poll for active jobs status
    const interval = setInterval(async () => {
      const jobs = getActiveJobs()
      setActiveJobs(jobs)

      // Check if any jobs completed
      for (const job of jobs) {
        try {
          const status = await api.getJob(job.jobId)
          if (status.status === 'completed') {
            // Refresh courses list
            const coursesData = await api.getCourses()
            setCourses(coursesData.courses || [])
          }
        } catch {
          // Ignore errors during polling
        }
      }
    }, 10000) // Poll every 10 seconds

    return () => clearInterval(interval)
  }, [])

  // Refresh courses when navigating to a course
  useEffect(() => {
    if (location.pathname.startsWith('/course/')) {
      api.getCourses()
        .then(data => setCourses(data.courses || []))
        .catch(() => {})
    }
  }, [location.pathname])

  const handleNewCourse = () => {
    navigate('/new')
  }

  const handleCourseClick = (courseId) => {
    markCourseRead(courseId)
    navigate(`/course/${courseId}`)
  }

  const handleJobClick = (jobId) => {
    navigate(`/generate/${jobId}`)
  }

  // Merge jobs and courses into a single list
  const items = [
    // Active jobs first
    ...activeJobs.map(job => ({
      type: 'job',
      id: job.jobId,
      name: job.repoName || 'Generating...',
      status: 'generating',
      timestamp: job.startedAt,
    })),
    // Then completed courses
    ...courses.map(course => ({
      type: 'course',
      id: course.id,
      name: course.repo_name,
      title: course.title,
      status: isCourseNew(course.id) ? 'new' : 'normal',
      timestamp: course.created_at,
    })),
  ]

  // Check if current route matches
  const isActive = (item) => {
    if (item.type === 'job') {
      return location.pathname === `/generate/${item.id}`
    }
    return location.pathname === `/course/${item.id}`
  }

  return (
    <aside className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col h-full">
      {/* New Course Button */}
      <div className="p-4">
        <button
          onClick={handleNewCourse}
          className="w-full flex items-center justify-center gap-2 bg-[#FF6B35] hover:bg-[#E55A2B] text-white font-medium py-2.5 px-4 rounded-lg transition-colors"
        >
          <Plus className="w-5 h-5" />
          New Course
        </button>
      </div>

      {/* Courses List */}
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-8 px-4">
            <BookOpen className="w-8 h-8 text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500">No courses yet</p>
            <p className="text-xs text-gray-400 mt-1">Create your first course above</p>
          </div>
        ) : (
          <div className="space-y-1">
            {items.map(item => (
              <button
                key={`${item.type}-${item.id}`}
                onClick={() => item.type === 'job' ? handleJobClick(item.id) : handleCourseClick(item.id)}
                className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors ${
                  isActive(item)
                    ? 'bg-[#FFF0EB] border border-[#FF6B35]/20'
                    : item.status === 'generating'
                    ? 'bg-amber-50 hover:bg-amber-100'
                    : item.status === 'new'
                    ? 'bg-blue-50 hover:bg-blue-100'
                    : 'hover:bg-gray-100'
                }`}
              >
                <div className="flex items-start gap-2">
                  {/* Status Icon */}
                  <div className="flex-shrink-0 mt-0.5">
                    {item.status === 'generating' ? (
                      <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />
                    ) : item.status === 'new' ? (
                      <Sparkles className="w-4 h-4 text-blue-500" />
                    ) : item.status === 'failed' ? (
                      <XCircle className="w-4 h-4 text-red-500" />
                    ) : (
                      <BookOpen className="w-4 h-4 text-gray-400" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm truncate ${
                      item.status === 'new' ? 'font-semibold text-gray-900' : 'font-medium text-gray-700'
                    }`}>
                      {item.name}
                    </p>
                    {item.status === 'generating' ? (
                      <p className="text-xs text-amber-600 mt-0.5">Generating...</p>
                    ) : (
                      <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatRelativeTime(item.timestamp)}
                      </p>
                    )}
                  </div>

                  {/* New Badge */}
                  {item.status === 'new' && (
                    <span className="flex-shrink-0 w-2 h-2 bg-blue-500 rounded-full mt-1.5" />
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}
