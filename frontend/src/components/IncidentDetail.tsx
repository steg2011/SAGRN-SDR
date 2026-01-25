import React from 'react';
import { Incident } from '../types';

interface IncidentDetailProps {
  incident: Incident;
  onClose: () => void;
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

function formatDateTime(dateString: string): string {
  const date = parseAsUTC(dateString);
  return date.toLocaleString('en-AU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Australia/Adelaide'
  });
}

export const IncidentDetail: React.FC<IncidentDetailProps> = ({ incident, onClose }) => {
  const googleMapsUrl = incident.latitude && incident.longitude
    ? `https://www.google.com/maps/search/?api=1&query=${incident.latitude},${incident.longitude}`
    : incident.address
      ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(incident.address + ', South Australia')}`
      : null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header" style={{ backgroundColor: incident.agency_color || '#E0E0E0' }}>
          <h2>{incident.agency_name || incident.agency_code}</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body">
          <div className="detail-section">
            <h3>Incident Details</h3>
            <div className="detail-row">
              <span className="label">Type:</span>
              <span className="value">{incident.incident_type || 'Unknown'}</span>
            </div>
            <div className="detail-row">
              <span className="label">Number:</span>
              <span className="value">{incident.incident_number}</span>
            </div>
            <div className="detail-row">
              <span className="label">Status:</span>
              <span className={`value status-${incident.status}`}>{incident.status}</span>
            </div>
            {incident.alarm_level && (
              <div className="detail-row">
                <span className="label">Alarm Level:</span>
                <span className="value">{incident.alarm_level}</span>
              </div>
            )}
            <div className="detail-row">
              <span className="label">Created:</span>
              <span className="value">{formatDateTime(incident.created_at)}</span>
            </div>
          </div>

          <div className="detail-section">
            <h3>Location</h3>
            <div className="detail-row">
              <span className="label">Address:</span>
              <span className="value">{incident.address || 'Not available'}</span>
            </div>
            {incident.suburb && (
              <div className="detail-row">
                <span className="label">Suburb:</span>
                <span className="value">{incident.suburb}</span>
              </div>
            )}
            {incident.map_reference && (
              <div className="detail-row">
                <span className="label">Map Ref:</span>
                <span className="value">{incident.map_reference}</span>
              </div>
            )}
            {googleMapsUrl && (
              <div className="detail-row">
                <a
                  href={googleMapsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="map-link"
                >
                  View on Google Maps
                </a>
              </div>
            )}
          </div>

          <div className="detail-section">
            <h3>Units Assigned ({incident.units.length})</h3>
            <div className="units-list">
              {incident.units.map((unit, i) => (
                <div key={i} className="unit-item">
                  <span className="unit-callsign">{unit.callsign}</span>
                  <span className={`unit-status status-${unit.status}`}>{unit.status}</span>
                </div>
              ))}
              {incident.units.length === 0 && (
                <span className="no-units">No units assigned</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
