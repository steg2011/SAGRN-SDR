import React from 'react';
import { Incident } from '../types';

interface IncidentRowProps {
  incident: Incident;
  isNew?: boolean;
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
    second: '2-digit',
    hour12: false,
    timeZone: 'Australia/Adelaide'
  });
}

function formatAdelaideDate(dateString: string): string | null {
  const date = parseAsUTC(dateString);
  const todayAdelaide = new Date().toLocaleDateString('en-AU', { timeZone: 'Australia/Adelaide' });
  const dateAdelaide = date.toLocaleDateString('en-AU', { timeZone: 'Australia/Adelaide' });
  if (dateAdelaide === todayAdelaide) return null;

  return date.toLocaleDateString('en-AU', {
    day: '2-digit',
    month: '2-digit',
    timeZone: 'Australia/Adelaide'
  });
}

function isMedstarUnit(callsign: string): boolean {
  return /^MS\d+$/i.test(callsign);
}

const MAX_ROW_UNITS = 4;

export const IncidentRow: React.FC<IncidentRowProps> = ({ incident, isNew, onClick }) => {
  const agencyColor = incident.agency_color || '#888';
  const date = formatAdelaideDate(incident.created_at);

  const medstarUnits = incident.units.filter(u => isMedstarUnit(u.callsign));
  const otherUnits = incident.units.filter(u => !isMedstarUnit(u.callsign));
  const shownOther = otherUnits.slice(0, Math.max(0, MAX_ROW_UNITS - medstarUnits.length));
  const hiddenCount = incident.units.length - medstarUnits.length - shownOther.length;

  const location = [incident.address, incident.suburb].filter(Boolean).join(', ');

  return (
    <div
      className={`incident-row ${isNew ? 'incident-new' : ''}`}
      style={{ borderLeftColor: agencyColor }}
      onClick={onClick}
    >
      <span className="row-time">
        {date && <span className="row-date">{date} </span>}
        {formatAdelaideTime(incident.created_at)}
      </span>

      <span className="row-agency" style={{ backgroundColor: agencyColor }}>
        {incident.agency_code || 'UNK'}
      </span>

      {incident.agency_code === 'SAAS' && incident.priority != null && (
        <span className={`row-priority ${incident.priority === 1 ? 'priority-1' : ''}`}>
          P{incident.priority}
        </span>
      )}
      {incident.alarm_level != null && incident.alarm_level > 1 && (
        <span className="row-priority">A{incident.alarm_level}</span>
      )}

      <span className="row-main">
        <span className="row-type">{incident.incident_type || 'Unknown Incident'}</span>
        {location && <span className="row-location">{location}</span>}
      </span>

      <span className="row-units">
        {medstarUnits.map((unit, i) => (
          <span key={`ms-${i}`} className="unit-badge unit-medstar">{unit.callsign}</span>
        ))}
        {shownOther.map((unit, i) => (
          <span key={`unit-${i}`} className="unit-badge">{unit.callsign}</span>
        ))}
        {hiddenCount > 0 && (
          <span className="unit-badge">+{hiddenCount}</span>
        )}
      </span>

      {incident.map_reference && (
        <span className="row-map-ref">{incident.map_reference}</span>
      )}
    </div>
  );
};
