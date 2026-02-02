import { useState, useEffect } from 'react'
import { Check, X, Lightbulb, Loader2 } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { api } from '../../api/client'

export default function ExerciseCard({ exerciseId, onComplete }) {
  const [exercise, setExercise] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [submitted, setSubmitted] = useState(false)
  const [showHint, setShowHint] = useState(false)

  useEffect(() => {
    if (!exerciseId) return
    api.getExercise(exerciseId)
      .then(setExercise)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [exerciseId])

  const handleSubmit = () => {
    if (selected === null) return
    setSubmitted(true)
  }

  const isCorrect = submitted && exercise && selected === exercise.correct_answer

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 text-[#FF6B35] animate-spin" />
      </div>
    )
  }

  if (!exercise) {
    return (
      <div className="text-gray-400 text-center py-12">
        Exercise not found
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Question */}
      <p className="text-lg font-medium text-gray-900">{exercise.question}</p>

      {/* Code Snippet */}
      {exercise.code_snippet && (
        <div className="rounded-lg overflow-hidden border border-gray-200">
          <SyntaxHighlighter
            language={exercise.code_language || 'python'}
            style={oneLight}
            customStyle={{ margin: 0, padding: '1rem' }}
          >
            {exercise.code_snippet}
          </SyntaxHighlighter>
        </div>
      )}

      {/* Options */}
      {exercise.options && (
        <div className="space-y-3">
          {exercise.options.map((option, i) => {
            const letter = String.fromCharCode(65 + i)
            const isSelected = selected === option
            const isAnswer = exercise.correct_answer === option

            let optionStyle = 'border-gray-200 hover:border-gray-300'
            if (submitted) {
              if (isAnswer) {
                optionStyle = 'border-green-500 bg-green-50'
              } else if (isSelected && !isAnswer) {
                optionStyle = 'border-red-500 bg-red-50'
              }
            } else if (isSelected) {
              optionStyle = 'border-[#FF6B35] bg-[#FFF0EB]'
            }

            return (
              <button
                key={option}
                onClick={() => !submitted && setSelected(option)}
                disabled={submitted}
                className={`w-full flex items-center gap-3 p-4 rounded-lg border-2 text-left transition-colors ${optionStyle}`}
              >
                <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  submitted && isAnswer
                    ? 'bg-green-500 text-white'
                    : submitted && isSelected && !isAnswer
                    ? 'bg-red-500 text-white'
                    : isSelected
                    ? 'bg-[#FF6B35] text-white'
                    : 'bg-gray-100 text-gray-600'
                }`}>
                  {submitted && isAnswer ? <Check className="w-4 h-4" /> :
                   submitted && isSelected && !isAnswer ? <X className="w-4 h-4" /> :
                   letter}
                </span>
                <span className="text-gray-900">{option}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* Hint */}
      {!submitted && exercise.hints?.length > 0 && (
        <div>
          <button
            onClick={() => setShowHint(!showHint)}
            className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            <Lightbulb className="w-4 h-4" />
            {showHint ? 'Hide hint' : 'Show hint'}
          </button>
          {showHint && (
            <p className="mt-2 text-sm text-gray-600 bg-amber-50 border border-amber-100 rounded-lg p-3">
              {exercise.hints[0]}
            </p>
          )}
        </div>
      )}

      {/* Explanation */}
      {submitted && (
        <div className={`p-4 rounded-lg ${isCorrect ? 'bg-green-50 border border-green-100' : 'bg-gray-50 border border-gray-100'}`}>
          <p className={`font-medium mb-1 ${isCorrect ? 'text-green-800' : 'text-gray-800'}`}>
            {isCorrect ? 'Correct!' : 'Not quite.'}
          </p>
          <p className="text-sm text-gray-600">{exercise.explanation}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        {!submitted ? (
          <button
            onClick={handleSubmit}
            disabled={selected === null}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Check Answer
          </button>
        ) : (
          <button onClick={onComplete} className="btn-primary">
            Continue →
          </button>
        )}
      </div>
    </div>
  )
}
