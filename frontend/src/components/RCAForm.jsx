import { useState } from 'react'
import { submitRCA } from '../services/api'

const CATEGORIES = [
  'INFRASTRUCTURE', 'CODE_BUG', 'CONFIGURATION',
  'CAPACITY', 'DEPENDENCY', 'HUMAN_ERROR', 'SECURITY', 'UNKNOWN',
]

function toLocalDatetimeValue(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function RCAForm({ workItemId, createdAt, onSuccess }) {
  const [form, setForm] = useState({
    incident_start: toLocalDatetimeValue(createdAt),
    incident_end: toLocalDatetimeValue(new Date().toISOString()),
    root_cause_category: 'INFRASTRUCTURE',
    root_cause_detail: '',
    fix_applied: '',
    prevention_steps: '',
    impact_summary: '',
    created_by: '',
  })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [serverError, setServerError] = useState('')

  const validate = () => {
    const e = {}
    if (!form.incident_start) e.incident_start = 'Required'
    if (!form.incident_end) e.incident_end = 'Required'
    if (form.incident_end <= form.incident_start) e.incident_end = 'End must be after start'
    if (form.root_cause_detail.length < 20) e.root_cause_detail = 'Minimum 20 characters'
    if (form.fix_applied.length < 10) e.fix_applied = 'Minimum 10 characters'
    if (form.prevention_steps.length < 10) e.prevention_steps = 'Minimum 10 characters'
    return e
  }

  const handleChange = e => {
    setForm(f => ({ ...f, [e.target.name]: e.target.value }))
    setErrors(err => ({ ...err, [e.target.name]: undefined }))
  }

  const handleSubmit = async e => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length > 0) { setErrors(errs); return }

    setLoading(true)
    setServerError('')
    try {
      const payload = {
        ...form,
        incident_start: new Date(form.incident_start).toISOString(),
        incident_end: new Date(form.incident_end).toISOString(),
      }
      await submitRCA(workItemId, payload)
      onSuccess?.()
    } catch (err) {
      setServerError(err.response?.data?.detail || 'Failed to submit RCA')
    } finally {
      setLoading(false)
    }
  }

  const Field = ({ name, label, type = 'text', rows, children }) => (
    <div>
      <label className="block text-xs text-gray-400 mb-1 font-semibold uppercase tracking-wide">
        {label} <span className="text-red-500">*</span>
      </label>
      {rows ? (
        <textarea
          name={name}
          value={form[name]}
          onChange={handleChange}
          rows={rows}
          className={`input resize-none ${errors[name] ? 'border-red-500' : ''}`}
          placeholder={children}
        />
      ) : (
        <input
          type={type}
          name={name}
          value={form[name]}
          onChange={handleChange}
          className={`input ${errors[name] ? 'border-red-500' : ''}`}
        />
      )}
      {errors[name] && <p className="text-red-400 text-xs mt-1">{errors[name]}</p>}
    </div>
  )

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Field name="incident_start" label="Incident Start" type="datetime-local" />
        <Field name="incident_end" label="Incident End" type="datetime-local" />
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-1 font-semibold uppercase tracking-wide">
          Root Cause Category <span className="text-red-500">*</span>
        </label>
        <select
          name="root_cause_category"
          value={form.root_cause_category}
          onChange={handleChange}
          className="input"
        >
          {CATEGORIES.map(c => <option key={c} value={c}>{c.replace('_', ' ')}</option>)}
        </select>
      </div>

      <Field name="root_cause_detail" label="Root Cause Detail" rows={3}>
        Describe the technical root cause in detail (min 20 chars)…
      </Field>

      <Field name="fix_applied" label="Fix Applied" rows={3}>
        What was done to resolve the incident…
      </Field>

      <Field name="prevention_steps" label="Prevention Steps" rows={3}>
        How will this be prevented in the future…
      </Field>

      <Field name="impact_summary" label="Impact Summary (optional)" rows={2}>
        Services affected, users impacted, data loss…
      </Field>

      <div>
        <label className="block text-xs text-gray-400 mb-1 font-semibold uppercase tracking-wide">Author</label>
        <input
          type="text"
          name="created_by"
          value={form.created_by}
          onChange={handleChange}
          className="input"
          placeholder="Your name or email"
        />
      </div>

      {serverError && (
        <div className="bg-red-950 border border-red-700 rounded p-3 text-red-300 text-sm">
          {serverError}
        </div>
      )}

      <button type="submit" disabled={loading} className="btn-primary w-full">
        {loading ? 'Submitting…' : 'Submit RCA'}
      </button>
    </form>
  )
}
