export interface Unit {
  callsign: string;
  status: string;
  dispatched_at: string | null;
}

export interface IncidentMessage {
  id: number;
  raw_message: string;
  timestamp: string;
  callsign: string | null;
  message_type: string | null;
}

export interface Incident {
  id: number;
  unique_id: string;
  incident_number: string;
  incident_date: string;
  incident_type: string | null;
  alarm_level: number | null;
  status: string;
  address: string | null;
  suburb: string | null;
  map_reference: string | null;
  latitude: number | null;
  longitude: number | null;
  agency_code: string | null;
  agency_name: string | null;
  agency_color: string | null;
  units: Unit[];
  messages: IncidentMessage[];
  created_at: string;
  updated_at: string;
}

export interface Agency {
  code: string;
  name: string;
  color: string;
}

export interface Stats {
  total_incidents_24h: number;
  active_incidents: number;
  by_agency: Record<string, number>;
}

export interface RawMessage {
  id: number;
  message: string;
  timestamp: string;
}
