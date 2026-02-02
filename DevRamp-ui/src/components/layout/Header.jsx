import { Link } from 'react-router-dom'
import { BookOpen } from 'lucide-react'

export default function Header({ showBack = false }) {
  return (
    <header className="border-b border-gray-100">
      <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 text-gray-900 hover:text-[#FF6B35] transition-colors">
          <BookOpen className="w-6 h-6 text-[#FF6B35]" />
          <span className="font-semibold text-lg">DevRamp</span>
        </Link>

        {showBack ? (
          <Link to="/" className="text-gray-500 hover:text-gray-900 text-sm font-medium transition-colors">
            ← Back to Home
          </Link>
        ) : (
          <Link to="/" className="text-gray-500 hover:text-gray-900 text-sm font-medium transition-colors">
            View Courses
          </Link>
        )}
      </div>
    </header>
  )
}
