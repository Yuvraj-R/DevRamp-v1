import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check, Loader2, X, RefreshCw, Clock, Info } from 'lucide-react'
import { api, removeActiveJob } from '../api/client'

export default function Generate() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [lastUpdate, setLastUpdate] = useState(Date.now())
  const maxConsecutiveErrors = 5
  const consecutiveErrors = useRef(0)

  useEffect(() => {
    if (!jobId) return

    const poll = async () => {
      try {
        const data = await api.getJob(jobId)
        setJob(data)
        setLastUpdate(Date.now())
        consecutiveErrors.current = 0 // Reset on success
        setError('') // Clear any temporary errors

        if (data.status === 'completed' && data.course_id) {
          removeActiveJob(jobId)
          // Small delay for UX, then redirect
          setTimeout(() => navigate(`/course/${data.course_id}`), 1500)
        } else if (data.status === 'failed') {
          removeActiveJob(jobId)
          setError(data.error || 'Generation failed')
        }
      } catch (err) {
        consecutiveErrors.current++

        // Only show error after multiple consecutive failures
        if (consecutiveErrors.current >= maxConsecutiveErrors) {
          setError(`Connection issue: ${err.message}. Still trying...`)
        }

        // Don't stop polling - backend might still be working
        console.log(`Poll error (attempt ${consecutiveErrors.current}):`, err.message)
      }
    }

    poll()
    const interval = setInterval(poll, 3000) // Poll every 3s
    return () => clearInterval(interval)
  }, [jobId, navigate])

  // Calculate time elapsed
  const startTime = job?.created_at ? new Date(job.created_at).getTime() : lastUpdate
  const timeElapsed = Math.floor((Date.now() - startTime) / 1000)
  const minutes = Math.floor(timeElapsed / 60)
  const seconds = timeElapsed % 60

  const progressPercent = job
    ? Math.round((job.step_index / (job.total_steps - 1)) * 100)
    : 0

  const isStillWorking = job && job.status !== 'completed' && job.status !== 'failed'
  const isCompleted = job?.status === 'completed'

  return (
    <div className="h-full flex items-center justify-center p-8">
      <div className="w-full max-w-xl">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            {isCompleted ? 'Course Ready!' : 'Generating your course...'}
          </h1>
          {job?.repo_name && (
            <p className="text-gray-500">{job.repo_name}</p>
          )}
        </div>

        {/* Info Banner */}
        {isStillWorking && (
          <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 mb-6 flex gap-3">
            <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-800">
              <p className="font-medium">Course generation takes 5-20 minutes</p>
              <p className="text-blue-600 mt-1">
                This depends on codebase size and complexity. You can navigate away -
                your course will appear in the sidebar when it's ready.
              </p>
            </div>
          </div>
        )}

        {/* Progress Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          {/* Time Elapsed */}
          {isStillWorking && (
            <div className="text-center text-sm text-gray-500 mb-6 flex items-center justify-center gap-2">
              <Clock className="w-4 h-4" />
              Time elapsed: {minutes > 0 ? `${minutes}m ` : ''}{seconds}s
            </div>
          )}

          {/* Steps */}
          <div className="space-y-4 mb-8">
            {job?.steps?.map((step, i) => (
              <div key={step.status} className="flex items-center gap-4">
                <div className={`
                  w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0
                  ${step.completed ? 'bg-green-500 text-white' : ''}
                  ${step.current ? 'bg-[#FF6B35] text-white' : ''}
                  ${!step.completed && !step.current ? 'bg-gray-100 text-gray-400' : ''}
                `}>
                  {step.completed ? (
                    <Check className="w-4 h-4" />
                  ) : step.current ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <span className="text-sm">{i + 1}</span>
                  )}
                </div>
                <span className={`text-sm ${
                  step.completed ? 'text-green-600' :
                  step.current ? 'text-gray-900 font-medium' :
                  'text-gray-400'
                }`}>
                  {step.label}
                </span>
              </div>
            ))}
          </div>

          {/* Progress Bar */}
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-[#FF6B35] transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <p className="text-center text-sm text-gray-500 mt-2">
            {progressPercent}% complete
          </p>

          {/* Connection Warning (soft error) */}
          {error && isStillWorking && (
            <div className="mt-6 p-4 bg-amber-50 border border-amber-100 rounded-lg flex items-start gap-3">
              <RefreshCw className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5 animate-spin" />
              <div>
                <p className="font-medium text-amber-800">Connection unstable</p>
                <p className="text-sm text-amber-600 mt-1">
                  {error} - The backend is likely still working.
                </p>
              </div>
            </div>
          )}

          {/* Hard Error (job failed) */}
          {error && !isStillWorking && job?.status === 'failed' && (
            <div className="mt-6 p-4 bg-red-50 border border-red-100 rounded-lg flex items-start gap-3">
              <X className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-red-800">Generation failed</p>
                <p className="text-sm text-red-600 mt-1">{error}</p>
              </div>
            </div>
          )}

          {/* Completion Message */}
          {isCompleted && (
            <div className="mt-6 p-4 bg-green-50 border border-green-100 rounded-lg text-center">
              <p className="text-green-800 font-medium">Redirecting to your course...</p>
            </div>
          )}
        </div>

        {/* Job ID for reference */}
        <p className="text-center text-xs text-gray-400 mt-4">
          Job ID: {jobId}
        </p>
      </div>
    </div>
  )
}
