import { Incident, Agency, Stats } from '../types';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function getIncidents(
  agency?: string,
  hours: number = 24,
  limit: number = 100
): Promise<Incident[]> {
  let url = `${API_BASE}/incidents?hours=${hours}&limit=${limit}`;
  if (agency && agency !== 'ALL') {
    url += `&agency=${agency}`;
  }
  return fetchJson<Incident[]>(url);
}

export async function getIncident(id: number): Promise<Incident> {
  return fetchJson<Incident>(`${API_BASE}/incidents/${id}`);
}

export async function getAgencies(): Promise<Agency[]> {
  return fetchJson<Agency[]>(`${API_BASE}/agencies`);
}

export async function getStats(): Promise<Stats> {
  return fetchJson<Stats>(`${API_BASE}/stats`);
}
