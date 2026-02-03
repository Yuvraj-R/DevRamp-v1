import { Link } from 'react-router-dom'
import { BookOpen } from 'lucide-react'

export default function Header() {
  return (
    <header className="border-b border-gray-200 bg-white flex-shrink-0">
      <div className="px-6 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 text-gray-900 hover:text-[#FF6B35] transition-colors">
          <BookOpen className="w-6 h-6 text-[#FF6B35]" />
          <span className="font-semibold text-lg">DevRamp</span>
        </Link>
      </div>
    </header>
  )
}
