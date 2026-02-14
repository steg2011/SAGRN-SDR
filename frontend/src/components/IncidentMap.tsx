import React, { useEffect, useRef, useState, useCallback } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { MapIncident, AgencyFilters } from '../types';
import { getMapIncidents } from '../services/api';

interface IncidentMapProps {
  mapboxToken: string;
  onIncidentClick: (incidentId: number) => void;
  refreshTrigger: number;
  agencyFilters: AgencyFilters;
}

// Adelaide center coordinates
const ADELAIDE_CENTER: [number, number] = [138.6007, -34.9285];
const DEFAULT_ZOOM = 10;

// Agency colors for markers (matching backend AGENCY_CONFIG)
const AGENCY_COLORS: Record<string, string> = {
  CFS: '#FFC107',   // Yellow
  MFS: '#F44336',   // Red
  SES: '#FF9800',   // Orange
  SAAS: '#4CAF50',  // Green
  TMC: '#2196F3',   // Blue
  WAZE: '#00BCD4',  // Cyan
  MedStar: '#9C27B0', // Purple
};

const formatTime = (dateStr: string): string => {
  try {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-AU', {
      timeZone: 'Australia/Adelaide',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
};

export const IncidentMap: React.FC<IncidentMapProps> = ({
  mapboxToken,
  onIncidentClick,
  refreshTrigger,
  agencyFilters,
}) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const [incidents, setIncidents] = useState<MapIncident[]>([]);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current || !mapboxToken) return;

    mapboxgl.accessToken = mapboxToken;

    const mapInstance = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: ADELAIDE_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: true,
    });

    mapInstance.addControl(new mapboxgl.NavigationControl(), 'top-right');

    mapInstance.on('load', () => {
      setMapLoaded(true);
    });

    map.current = mapInstance;

    return () => {
      mapInstance.remove();
      map.current = null;
      setMapLoaded(false);
    };
  }, [mapboxToken]);

  // Resize map when fullscreen toggles
  useEffect(() => {
    if (map.current) {
      setTimeout(() => map.current?.resize(), 50);
    }
  }, [isFullscreen]);

  // Handle Escape key to exit fullscreen
  useEffect(() => {
    if (!isFullscreen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsFullscreen(false);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isFullscreen]);

  // Fetch map incidents
  const fetchMapData = useCallback(async () => {
    try {
      const data = await getMapIncidents(48);
      setIncidents(data);
    } catch (err) {
      console.error('Failed to fetch map incidents:', err);
    }
  }, []);

  // Fetch on mount and when refreshTrigger changes (SSE events)
  useEffect(() => {
    fetchMapData();
  }, [fetchMapData, refreshTrigger]);

  // Apply agency filters to map incidents
  const filteredIncidents = incidents.filter((inc) => {
    const code = inc.agency_code ?? '';

    if (agencyFilters.enabled[code] === false) return false;

    if (code === 'SAAS' && agencyFilters.saasPriority !== 'all') {
      // MapIncident doesn't have priority, skip this filter on map
    }

    if (code === 'CFS' && agencyFilters.cfsAlarmLevel !== 'all') {
      if (inc.alarm_level === null || inc.alarm_level < agencyFilters.cfsAlarmLevel) return false;
    }

    if (code === 'MFS' && agencyFilters.mfsAlarmLevel !== 'all') {
      if (inc.alarm_level === null || inc.alarm_level < agencyFilters.mfsAlarmLevel) return false;
    }

    if (code === 'WAZE' && agencyFilters.wazeCrashesOnly) {
      if (!inc.incident_type || !inc.incident_type.toLowerCase().includes('accident')) return false;
    }

    return true;
  });

  // Update markers when incidents or filters change
  useEffect(() => {
    if (!map.current || !mapLoaded) return;

    // Remove existing markers
    markersRef.current.forEach(m => m.remove());
    markersRef.current = [];

    filteredIncidents.forEach(inc => {
      if (!inc.latitude || !inc.longitude) return;

      const color = AGENCY_COLORS[inc.agency_code || ''] || '#888888';
      const isEstimated = inc.location_source === 'LOCAL_LOOKUP';

      // Create marker element
      const el = document.createElement('div');
      el.className = 'map-marker';
      el.style.width = '14px';
      el.style.height = '14px';
      el.style.borderRadius = '50%';
      el.style.backgroundColor = color;
      el.style.border = '2px solid #fff';
      el.style.cursor = 'pointer';
      el.style.boxShadow = '0 0 4px rgba(0,0,0,0.5)';

      if (isEstimated) {
        el.style.opacity = '0.7';
        el.style.border = '2px dashed #fff';
      }

      // Larger markers for higher alarm levels
      if (inc.alarm_level && inc.alarm_level >= 3) {
        el.style.width = '20px';
        el.style.height = '20px';
      } else if (inc.alarm_level && inc.alarm_level >= 2) {
        el.style.width = '16px';
        el.style.height = '16px';
      }

      // Active incidents pulse
      if (inc.status === 'active') {
        el.style.animation = 'map-marker-pulse 2s infinite';
      }

      // Build popup content
      const location = [inc.address, inc.suburb].filter(Boolean).join(', ') || 'Unknown';
      const time = formatTime(inc.incident_date);
      const sourceLabel = inc.location_source === 'OFFICIAL_FEED' ? 'Official' : 'Estimated';

      const popupHtml = `
        <div class="map-popup">
          <div class="map-popup-header" style="background:${color}; color: #000; padding: 4px 8px; font-weight: bold; border-radius: 4px 4px 0 0;">
            ${inc.agency_code || 'UNKNOWN'} - ${time}
          </div>
          <div class="map-popup-body" style="padding: 8px;">
            <div style="font-weight:bold; margin-bottom:4px;">${inc.incident_type || 'Unknown type'}</div>
            <div style="font-size:0.85em; color:#ccc; margin-bottom:4px;">${location}</div>
            <div style="font-size:0.75em; color:#888;">${sourceLabel} location</div>
          </div>
        </div>
      `;

      const popup = new mapboxgl.Popup({
        offset: 15,
        closeButton: false,
        closeOnClick: true,
        className: 'map-incident-popup',
      }).setHTML(popupHtml);

      const marker = new mapboxgl.Marker({ element: el })
        .setLngLat([inc.longitude, inc.latitude])
        .addTo(map.current!);

      // Hover to show popup, click to open detail modal
      el.addEventListener('mouseenter', () => {
        marker.setPopup(popup);
        marker.togglePopup();
      });
      el.addEventListener('mouseleave', () => {
        if (marker.getPopup()?.isOpen()) {
          marker.togglePopup();
        }
        marker.setPopup(undefined as any);
      });
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        onIncidentClick(inc.id);
      });

      markersRef.current.push(marker);
    });
  }, [filteredIncidents, mapLoaded, onIncidentClick]);

  if (!mapboxToken) {
    return (
      <div className="map-container map-no-token">
        <p>Mapbox token not configured.</p>
        <p>Set MAPBOX_TOKEN in your backend .env file.</p>
      </div>
    );
  }

  return (
    <div className={`map-container ${isFullscreen ? 'map-fullscreen' : ''}`}>
      <div ref={mapContainer} className="map-view" />
      <button
        className="map-fullscreen-btn"
        onClick={() => setIsFullscreen(!isFullscreen)}
        aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
        title={isFullscreen ? 'Exit fullscreen (Esc)' : 'Fullscreen'}
      >
        {isFullscreen ? '\u2716' : '\u26F6'}
      </button>
      <div className="map-legend">
        {Object.entries(AGENCY_COLORS).map(([code, color]) => (
          <span key={code} className="map-legend-item">
            <span className="map-legend-dot" style={{ backgroundColor: color }} />
            {code}
          </span>
        ))}
      </div>
    </div>
  );
};
