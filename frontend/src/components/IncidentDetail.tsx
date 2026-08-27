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
  const outage = incident.outage;
  const isOutage = incident.agency_code === 'SAPN';
  const googleMapsUrl = incident.latitude && incident.longitude
    ? `https://www.google.com/maps/search/?api=1&query=${incident.latitude},${incident.longitude}`
    : incident.address
      ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(incident.address + ', South Australia')}`
      : incident.suburb
        ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(incident.suburb + ', South Australia')}`
        : null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header" style={{ backgroundColor: incident.agency_color || '#E0E0E0' }}>
          <h2>{incident.agency_name || incident.agency_code}</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body">
          {outage && (
            <div className="detail-section">
              <h3>Power Outage</h3>
              <div className="detail-row">
                <span className="label">Cause:</span>
                <span className="value">{outage.reason || 'Unknown'}</span>
              </div>
              <div className="detail-row">
                <span className="label">Status:</span>
                <span className="value">
                  {outage.status_text || (outage.active ? 'In progress' : 'Restored')}
                </span>
              </div>
              <div className="detail-row">
                <span className="label">Type:</span>
                <span className="value">{outage.is_planned ? 'Planned' : 'Unplanned'}</span>
              </div>
              {outage.affected_customers != null && (
                <div className="detail-row">
                  <span className="label">Affected Customers:</span>
                  <span className="value">{outage.affected_customers.toLocaleString('en-AU')}</span>
                </div>
              )}
              {outage.start_time && (
                <div className="detail-row">
                  <span className="label">Started:</span>
                  <span className="value">{formatDateTime(outage.start_time)}</span>
                </div>
              )}
              <div className="detail-row">
                <span className="label">Est. Restoration:</span>
                <span className="value">
                  {outage.estimated_restoration ? formatDateTime(outage.estimated_restoration) : 'Unknown'}
                </span>
              </div>
              <div className="detail-row">
                <span className="label">Job ID:</span>
                <span className="value">{outage.job_id}</span>
              </div>
              {outage.suburbs.length > 0 && (
                <div className="detail-row">
                  <span className="label">Suburbs:</span>
                  <span className="value">
                    {outage.suburbs.map(s => s.name).filter(Boolean).join(', ')}
                  </span>
                </div>
              )}
            </div>
          )}

          {!isOutage && (
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
          )}

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
            {incident.location_source && (
              <div className="detail-row">
                <span className="label">Source:</span>
                <span className={`value location-source-badge ${incident.location_source === 'OFFICIAL_FEED' ? 'official' : 'estimated'}`}>
                  {incident.location_source === 'OFFICIAL_FEED' ? 'Official' : incident.location_source === 'LOCAL_LOOKUP' ? 'Estimated' : incident.location_source}
                </span>
              </div>
            )}
            {incident.cfs_resources && (
              <div className="detail-row">
                <span className="label">Resources:</span>
                <span className="value">{incident.cfs_resources}</span>
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

          {incident.cfs_description && (
            <div className="detail-section">
              <h3>CFS Description</h3>
              <div className="cfs-description">{incident.cfs_description}</div>
            </div>
          )}

          {!isOutage && (
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
          )}

          {incident.messages && incident.messages.length > 0 && (
            <div className="detail-section">
              <h3>Pager Messages ({incident.messages.length})</h3>
              <div className="messages-list">
                {incident.messages.map((msg, i) => (
                  <div key={i} className="message-item">
                    <div className="message-header">
                      <span className="message-time">
                        {formatDateTime(msg.timestamp)}
                      </span>
                      {msg.callsign && (
                        <span className="message-callsign">{msg.callsign}</span>
                      )}
                      {msg.message_type && (
                        <span className="message-type">{msg.message_type}</span>
                      )}
                    </div>
                    <div className="message-content">
                      {msg.raw_message}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
