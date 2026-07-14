// Patient-account session: a backend-issued JWT kept in localStorage and attached
// to the authed /api/account/* endpoints. Distinct from the clinician (Supabase)
// auth used on /clinician.

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const TOKEN_KEY = 'mgc_patient_token';

export function getPatientToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setPatientToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearPatientToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/** Fetch an /api/account/* path with the patient bearer token attached. */
export function patientFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getPatientToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

export { API_BASE };
