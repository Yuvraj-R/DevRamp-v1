import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, Clock, Layers, BookOpen, CheckCircle, Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Header from '../components/layout/Header'
import ExerciseCard from '../components/exercise/ExerciseCard'
import { api } from '../api/client'

export default function Course() {
  const { courseId } = useParams()
  const [course, setCourse] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedModules, setExpandedModules] = useState({})
  const [activeSection, setActiveSection] = useState(null)
  const [completedSections, setCompletedSections] = useState(new Set())

  useEffect(() => {
    api.getCourse(courseId)
      .then(data => {
        setCourse(data)
        // Expand first module and select first section
        if (data.modules?.length > 0) {
          setExpandedModules({ 0: true })
          if (data.modules[0].sections?.length > 0) {
            setActiveSection({ moduleIndex: 0, sectionIndex: 0 })
          }
        }
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [courseId])

  const toggleModule = (index) => {
    setExpandedModules(prev => ({ ...prev, [index]: !prev[index] }))
  }

  const selectSection = (moduleIndex, sectionIndex) => {
    setActiveSection({ moduleIndex, sectionIndex })
  }

  const markComplete = () => {
    if (!activeSection) return
    const key = `${activeSection.moduleIndex}-${activeSection.sectionIndex}`
    setCompletedSections(prev => new Set([...prev, key]))
    goNext()
  }

  const goNext = () => {
    if (!course || !activeSection) return
    const { moduleIndex, sectionIndex } = activeSection
    const currentModule = course.modules[moduleIndex]

    if (sectionIndex < currentModule.sections.length - 1) {
      setActiveSection({ moduleIndex, sectionIndex: sectionIndex + 1 })
    } else if (moduleIndex < course.modules.length - 1) {
      setExpandedModules(prev => ({ ...prev, [moduleIndex + 1]: true }))
      setActiveSection({ moduleIndex: moduleIndex + 1, sectionIndex: 0 })
    }
  }

  const goPrev = () => {
    if (!course || !activeSection) return
    const { moduleIndex, sectionIndex } = activeSection

    if (sectionIndex > 0) {
      setActiveSection({ moduleIndex, sectionIndex: sectionIndex - 1 })
    } else if (moduleIndex > 0) {
      const prevModule = course.modules[moduleIndex - 1]
      setExpandedModules(prev => ({ ...prev, [moduleIndex - 1]: true }))
      setActiveSection({ moduleIndex: moduleIndex - 1, sectionIndex: prevModule.sections.length - 1 })
    }
  }

  const currentSection = activeSection && course
    ? course.modules[activeSection.moduleIndex]?.sections[activeSection.sectionIndex]
    : null

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#FF6B35] animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header showBack />
        <div className="max-w-xl mx-auto px-6 py-16 text-center">
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-white">
      <Header showBack />

      {/* Course Header */}
      <div className="border-b border-gray-100 bg-gray-50">
        <div className="max-w-6xl mx-auto px-6 py-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">{course.title}</h1>
          <div className="flex items-center gap-6 text-sm text-gray-500">
            <span className="flex items-center gap-1.5">
              <Layers className="w-4 h-4" />
              {course.modules?.length || 0} modules
            </span>
            <span className="flex items-center gap-1.5">
              <BookOpen className="w-4 h-4" />
              {course.total_readings || 0} readings
            </span>
            <span className="flex items-center gap-1.5">
              <Clock className="w-4 h-4" />
              {course.estimated_hours?.toFixed(1) || 0} hrs
            </span>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-6xl mx-auto flex">
        {/* Sidebar */}
        <aside className="w-72 flex-shrink-0 border-r border-gray-100 h-[calc(100vh-140px)] overflow-y-auto sticky top-0">
          <nav className="p-4">
            {course.modules?.map((mod, modIndex) => (
              <div key={mod.id} className="mb-2">
                <button
                  onClick={() => toggleModule(modIndex)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm font-medium text-gray-900 hover:bg-gray-50 rounded-lg transition-colors"
                >
                  {expandedModules[modIndex] ? (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  )}
                  <span className="truncate">{mod.title}</span>
                </button>

                {expandedModules[modIndex] && (
                  <div className="ml-6 mt-1 space-y-1">
                    {mod.sections?.map((section, secIndex) => {
                      const isActive = activeSection?.moduleIndex === modIndex && activeSection?.sectionIndex === secIndex
                      const isComplete = completedSections.has(`${modIndex}-${secIndex}`)
                      return (
                        <button
                          key={section.id}
                          onClick={() => selectSection(modIndex, secIndex)}
                          className={`w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm rounded-lg transition-colors ${
                            isActive
                              ? 'bg-[#FFF0EB] text-[#FF6B35]'
                              : 'text-gray-600 hover:bg-gray-50'
                          }`}
                        >
                          {isComplete ? (
                            <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                          ) : (
                            <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                              section.type === 'exercise' ? 'bg-amber-400' : 'bg-gray-300'
                            }`} />
                          )}
                          <span className="truncate">{section.title}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            ))}
          </nav>
        </aside>

        {/* Content Pane */}
        <main className="flex-1 min-w-0 h-[calc(100vh-140px)] overflow-y-auto">
          {currentSection ? (
            <div className="max-w-3xl mx-auto px-8 py-8">
              {/* Section Header */}
              <div className="mb-6">
                <span className={`inline-block text-xs font-medium uppercase tracking-wide px-2 py-1 rounded mb-2 ${
                  currentSection.type === 'exercise'
                    ? 'bg-amber-100 text-amber-700'
                    : 'bg-gray-100 text-gray-600'
                }`}>
                  {currentSection.type}
                </span>
                <h2 className="text-2xl font-bold text-gray-900">{currentSection.title}</h2>
              </div>

              {/* Content */}
              {currentSection.type === 'exercise' ? (
                <ExerciseCard
                  exerciseId={currentSection.exercise_id}
                  onComplete={markComplete}
                />
              ) : (
                <article className="prose prose-gray max-w-none">
                  <ReactMarkdown
                    components={{
                      code({ node, inline, className, children, ...props }) {
                        const match = /language-(\w+)/.exec(className || '')
                        return !inline && match ? (
                          <SyntaxHighlighter
                            style={oneLight}
                            language={match[1]}
                            PreTag="div"
                            {...props}
                          >
                            {String(children).replace(/\n$/, '')}
                          </SyntaxHighlighter>
                        ) : (
                          <code className={className} {...props}>
                            {children}
                          </code>
                        )
                      }
                    }}
                  >
                    {currentSection.content}
                  </ReactMarkdown>
                </article>
              )}

              {/* Navigation */}
              <div className="flex items-center justify-between mt-10 pt-6 border-t border-gray-100">
                <button
                  onClick={goPrev}
                  disabled={activeSection?.moduleIndex === 0 && activeSection?.sectionIndex === 0}
                  className="btn-secondary disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  ← Previous
                </button>

                {currentSection.type !== 'exercise' && (
                  <button onClick={markComplete} className="btn-primary">
                    Mark Complete & Continue →
                  </button>
                )}

                {currentSection.type === 'exercise' && (
                  <button onClick={goNext} className="btn-secondary">
                    Skip →
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              Select a section to begin
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
