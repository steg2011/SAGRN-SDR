import { Incident, Agency, Stats, RawMessage } from '../types';

// Dynamically determine API URL based on current host (for accessing from other devices)
const getApiBase = (): string => {
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }
  // Use the same hostname the page was loaded from, with backend port 8000
  const host = window.location.hostname;
  return `http://${host}:8000/api`;
};

const API_BASE = getApiBase();

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

export async function getRawMessages(limit: number = 100): Promise<RawMessage[]> {
  return fetchJson<RawMessage[]>(`${API_BASE}/messages/raw?limit=${limit}`);
}
