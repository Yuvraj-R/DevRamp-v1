import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check, Loader2, X } from 'lucide-react'
import Header from '../components/layout/Header'
import { api } from '../api/client'

export default function Generate() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!jobId) return

    const poll = async () => {
      try {
        const data = await api.getJob(jobId)
        setJob(data)

        if (data.status === 'completed' && data.course_id) {
          // Small delay for UX, then redirect
          setTimeout(() => navigate(`/course/${data.course_id}`), 1000)
        } else if (data.status === 'failed') {
          setError(data.error || 'Generation failed')
        }
      } catch (err) {
        setError(err.message)
      }
    }

    poll()
    const interval = setInterval(poll, 1500)
    return () => clearInterval(interval)
  }, [jobId, navigate])

  const progressPercent = job
    ? Math.round((job.step_index / (job.total_steps - 1)) * 100)
    : 0

  return (
    <div className="min-h-screen bg-gray-50">
      <Header showBack />

      <main className="max-w-xl mx-auto px-6 py-16">
        <div className="text-center mb-10">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            {job?.status === 'completed' ? 'Course Ready!' : 'Generating your course...'}
          </h1>
          {job?.repo_name && (
            <p className="text-gray-500">{job.repo_name}</p>
          )}
        </div>

        {/* Progress Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
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

          {/* Error */}
          {error && (
            <div className="mt-6 p-4 bg-red-50 border border-red-100 rounded-lg flex items-start gap-3">
              <X className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-red-800">Generation failed</p>
                <p className="text-sm text-red-600 mt-1">{error}</p>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
