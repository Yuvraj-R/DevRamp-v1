import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import NewCourse from './pages/NewCourse'
import Generate from './pages/Generate'
import Course from './pages/Course'

export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/new" replace />} />
        <Route path="/new" element={<NewCourse />} />
        <Route path="/generate/:jobId" element={<Generate />} />
        <Route path="/course/:courseId" element={<Course />} />
      </Routes>
    </AppLayout>
  )
}
