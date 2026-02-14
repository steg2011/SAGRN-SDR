import { Incident, Agency, Stats, RawMessage, MapIncident } from '../types';

// Dynamically determine API URL based on current host
const getApiBase = (): string => {
  // Allow override via environment variable
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }

  // In production (served from same server), use relative URL
  // In development (separate React dev server), use backend port 8000
  const { protocol, hostname, port } = window.location;

  // If running on port 3000 (React dev server), connect to port 8000
  if (port === '3000') {
    return `${protocol}//${hostname}:8000/api`;
  }

  // Otherwise, use same origin (production mode - frontend served by FastAPI)
  return '/api';
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
  hours: number = 168,
  limit: number = 20,
  offset: number = 0
): Promise<Incident[]> {
  let url = `${API_BASE}/incidents?hours=${hours}&limit=${limit}&offset=${offset}`;
  if (agency && agency !== 'ALL') {
    url += `&agency=${agency}`;
  }
  return fetchJson<Incident[]>(url);
}

export async function searchIncidents(
  query: string,
  agency?: string,
  limit: number = 20,
  offset: number = 0
): Promise<Incident[]> {
  let url = `${API_BASE}/incidents/search?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`;
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

export async function getMapIncidents(
  hours: number = 24,
  agency?: string
): Promise<MapIncident[]> {
  let url = `${API_BASE}/incidents/map?hours=${hours}`;
  if (agency && agency !== 'ALL') {
    url += `&agency=${agency}`;
  }
  return fetchJson<MapIncident[]>(url);
}

export async function getFrontendConfig(): Promise<{ mapbox_token: string }> {
  return fetchJson<{ mapbox_token: string }>(`${API_BASE}/config`);
}

// Server-Sent Events
export interface SSECallbacks {
  onConnected?: () => void;
  onNewMessage?: (data: { message_id: number; incident_id: number | null; agency: string; type: string }) => void;
  onBatchProcessed?: (data: { processed: number; skipped: number; combined: number }) => void;
  onError?: (error: Event) => void;
}

export function subscribeToEvents(callbacks: SSECallbacks): () => void {
  const eventSource = new EventSource(`${API_BASE}/events`);

  eventSource.addEventListener('connected', () => {
    callbacks.onConnected?.();
  });

  eventSource.addEventListener('new_message', (event) => {
    const data = JSON.parse(event.data);
    callbacks.onNewMessage?.(data);
  });

  eventSource.addEventListener('batch_processed', (event) => {
    const data = JSON.parse(event.data);
    callbacks.onBatchProcessed?.(data);
  });

  eventSource.onerror = (error) => {
    callbacks.onError?.(error);
  };

  // Return cleanup function
  return () => {
    eventSource.close();
  };
}
