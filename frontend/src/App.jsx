import { Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import IncidentDetail from './pages/IncidentDetail'
import { HealthBar } from './components/HealthBar'

function NavLink({ to, children }) {
  const { pathname } = useLocation()
  const active = pathname === to
  return (
    <Link
      to={to}
      className={`text-sm font-semibold px-3 py-1 rounded transition-colors
        ${active ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white'}`}
    >
      {children}
    </Link>
  )
}

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Nav */}
      <nav className="border-b border-gray-800 bg-gray-950 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
          <span className="text-white font-bold tracking-tight">
            🚨 <span className="text-blue-400">IMS</span>
          </span>
          <div className="flex gap-1">
            <NavLink to="/">Dashboard</NavLink>
          </div>
          <div className="ml-auto">
            <HealthBar />
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/incidents/:id" element={<IncidentDetail />} />
        </Routes>
      </main>

      <footer className="border-t border-gray-800 py-3 text-center text-xs text-gray-600">
        Incident Management System · Built for Zeotap SRE Internship Challenge
      </footer>
    </div>
  )
}
