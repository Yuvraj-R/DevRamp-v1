import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Generate from './pages/Generate'
import Course from './pages/Course'

export default function App() {
  return (
    <div className="min-h-screen bg-white">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/generate/:jobId" element={<Generate />} />
        <Route path="/course/:courseId" element={<Course />} />
      </Routes>
    </div>
  )
}
