import React from 'react';
import { Incident } from '../types';

interface IncidentCardProps {
  incident: Incident;
  onClick: () => void;
}

function parseAsUTC(dateString: string): Date {
  // Ensure the date string is treated as UTC by adding Z if not present
  let utcString = dateString;
  if (!dateString.endsWith('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
    // Replace space with T for ISO format and add Z for UTC
    utcString = dateString.replace(' ', 'T') + 'Z';
  }
  return new Date(utcString);
}

function formatAdelaideTime(dateString: string): string {
  const date = parseAsUTC(dateString);
  return date.toLocaleTimeString('en-AU', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Australia/Adelaide'
  });
}

function formatAdelaideDateTime(dateString: string): string {
  const date = parseAsUTC(dateString);
  const todayAdelaide = new Date().toLocaleDateString('en-AU', { timeZone: 'Australia/Adelaide' });
  const dateAdelaide = date.toLocaleDateString('en-AU', { timeZone: 'Australia/Adelaide' });
  const isToday = dateAdelaide === todayAdelaide;

  if (isToday) {
    return formatAdelaideTime(dateString);
  }

  return date.toLocaleDateString('en-AU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Australia/Adelaide'
  });
}

export const IncidentCard: React.FC<IncidentCardProps> = ({ incident, onClick }) => {
  const bgColor = incident.agency_color || '#E0E0E0';

  return (
    <div
      className="incident-card"
      style={{ backgroundColor: bgColor }}
      onClick={onClick}
    >
      <div className="incident-header">
        <span className="incident-agency">{incident.agency_code || 'UNK'}</span>
        <span className="incident-time">{formatAdelaideDateTime(incident.created_at)}</span>
      </div>

      <div className="incident-type">
        {incident.incident_type || 'Unknown Incident'}
      </div>

      <div className="incident-location">
        {incident.suburb || incident.address || 'Location unavailable'}
      </div>

      <div className="incident-footer">
        <div className="incident-units">
          {incident.units.slice(0, 3).map((unit, i) => (
            <span key={i} className="unit-badge">{unit.callsign}</span>
          ))}
          {incident.units.length > 3 && (
            <span className="unit-badge">+{incident.units.length - 3}</span>
          )}
        </div>
        <div className="incident-meta">
          {incident.map_reference && (
            <span className="map-ref">{incident.map_reference}</span>
          )}
        </div>
      </div>
    </div>
  );
};
