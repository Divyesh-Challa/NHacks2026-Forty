import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Caregiver from './pages/Caregiver'
import Pair from './pages/Pair'
import Patient from './pages/Patient'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/patient/:id" element={<Patient />} />
        <Route path="/caregiver" element={<Caregiver />} />
        <Route path="/pair" element={<Pair />} />
        <Route path="*" element={<Navigate to="/patient/p1" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
