import axios from 'axios'

const BASE = '/api/v1'

export const api = axios.create({
  baseURL: BASE,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

// Incidents
export const getIncidents = (params = {}) =>
  api.get('/incidents', { params }).then(r => r.data)

export const getDashboard = () =>
  api.get('/incidents/dashboard').then(r => r.data)

export const getIncident = id =>
  api.get(`/incidents/${id}`).then(r => r.data)

export const getSignals = (id, limit = 100) =>
  api.get(`/incidents/${id}/signals`, { params: { limit } }).then(r => r.data)

export const getReplay = id =>
  api.get(`/incidents/${id}/replay`).then(r => r.data)

export const updateStatus = (id, new_status) =>
  api.patch(`/incidents/${id}/status`, { new_status }).then(r => r.data)

export const submitRCA = (id, data) =>
  api.post(`/incidents/${id}/rca`, data).then(r => r.data)

// Signals
export const ingestSignal = data =>
  api.post('/signals', data, {
    headers: { 'X-API-Key': 'ims-ingest-key-2024' },
  }).then(r => r.data)

// Simulation
export const simulateBurst = () =>
  api.post('/simulate/burst').then(r => r.data)

export const simulateDbFailure = (duration = 15) =>
  api.post('/simulate/db-failure', { duration_seconds: duration }).then(r => r.data)

export const resetSimulation = () =>
  api.post('/simulate/reset').then(r => r.data)

export const getSimStatus = () =>
  api.get('/simulate/status').then(r => r.data)

// Health
export const getHealth = () =>
  axios.get('/health').then(r => r.data)
