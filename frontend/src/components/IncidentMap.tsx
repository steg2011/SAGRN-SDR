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

const ADELAIDE_CENTER: [number, number] = [138.6007, -34.9285];
const DEFAULT_ZOOM = 10;

const AGENCY_COLORS: Record<string, string> = {
  CFS: '#FFC107',
  MFS: '#F44336',
  SES: '#FF9800',
  SAAS: '#4CAF50',
  TMC: '#2196F3',
  WAZE: '#00BCD4',
  MedStar: '#9C27B0',
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

// Abbreviated incident type for zoomed-in labels
const shortType = (type: string | null): string => {
  if (!type) return '?';
  const t = type.toUpperCase();
  if (t.includes('STRUCTURE') || t.includes('HOUSE') || t.includes('BUILDING')) return 'STRUCT';
  if (t.includes('GRASS') || t.includes('SCRUB') || t.includes('BUSH')) return 'GRASS';
  if (t.includes('VEHICLE') || t.includes('MVA') || t.includes('ACCIDENT')) return 'MVA';
  if (t.includes('MEDICAL') || t.includes('CARDIAC') || t.includes('RESUS')) return 'MED';
  if (t.includes('RESCUE')) return 'RESCUE';
  if (t.includes('HAZMAT') || t.includes('CHEMICAL')) return 'HAZ';
  if (t.includes('STORM') || t.includes('FLOOD')) return 'STORM';
  if (t.includes('ASSIST')) return 'ASSIST';
  return type.substring(0, 6).toUpperCase();
};

export const IncidentMap: React.FC<IncidentMapProps> = ({
  mapboxToken,
  onIncidentClick,
  refreshTrigger,
  agencyFilters,
}) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const [incidents, setIncidents] = useState<MapIncident[]>([]);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const animFrameRef = useRef<number>(0);
  const popupRef = useRef<mapboxgl.Popup | null>(null);
  // Keep callback ref fresh to avoid stale closures inside map event handlers
  const onIncidentClickRef = useRef(onIncidentClick);
  useEffect(() => { onIncidentClickRef.current = onIncidentClick; }, [onIncidentClick]);

  // Initialize map and GL layers once
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

    mapInstance.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right');

    mapInstance.on('load', () => {
      // ── GeoJSON source with built-in clustering ──────────────────────
      mapInstance.addSource('incidents', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        cluster: true,
        clusterRadius: 50,
        clusterMaxZoom: 13,
        promoteId: 'id',
      });

      // ── Cluster: outer glow ring ─────────────────────────────────────
      mapInstance.addLayer({
        id: 'cluster-halo',
        type: 'circle',
        source: 'incidents',
        filter: ['has', 'point_count'],
        paint: {
          'circle-radius': [
            'interpolate', ['linear'], ['get', 'point_count'],
            1, 26, 15, 42, 50, 58,
          ],
          'circle-color': '#ffffff',
          'circle-opacity': 0.07,
        },
      });

      // ── Cluster: main circle, colour-stepped by count ────────────────
      mapInstance.addLayer({
        id: 'clusters',
        type: 'circle',
        source: 'incidents',
        filter: ['has', 'point_count'],
        paint: {
          'circle-radius': [
            'interpolate', ['linear'], ['get', 'point_count'],
            1, 18, 15, 30, 50, 42,
          ],
          'circle-color': [
            'step', ['get', 'point_count'],
            '#2196F3',  // 1–4 → blue
            5,  '#FF9800',  // 5–14 → orange
            15, '#F44336',  // 15+ → red
          ],
          'circle-opacity': 0.92,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-opacity': 0.25,
        },
      });

      // ── Cluster: count label ─────────────────────────────────────────
      mapInstance.addLayer({
        id: 'cluster-count',
        type: 'symbol',
        source: 'incidents',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': '{point_count_abbreviated}',
          'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Bold'],
          'text-size': [
            'interpolate', ['linear'], ['get', 'point_count'],
            1, 13, 50, 17,
          ],
        },
        paint: {
          'text-color': '#ffffff',
        },
      });

      // ── Individual: animated pulse halo for active incidents ─────────
      mapInstance.addLayer({
        id: 'active-halo',
        type: 'circle',
        source: 'incidents',
        filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 'status'], 'active']],
        paint: {
          'circle-radius': 18,
          'circle-color': '#ffffff',
          'circle-opacity': 0.12,
          'circle-blur': 0.6,
        },
      });

      // ── Individual: incident circle, sized by alarm level + zoom ─────
      mapInstance.addLayer({
        id: 'unclustered',
        type: 'circle',
        source: 'incidents',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-radius': [
            'interpolate', ['linear'], ['zoom'],
            8,  ['case', ['>=', ['coalesce', ['get', 'alarm_level'], 0], 3], 8,  6],
            13, ['case', ['>=', ['coalesce', ['get', 'alarm_level'], 0], 3], 14, 10],
          ],
          'circle-color': ['get', 'color'],
          'circle-opacity': [
            'case', ['==', ['get', 'location_source'], 'LOCAL_LOOKUP'], 0.6, 0.95,
          ],
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-opacity': 0.8,
        },
      });

      // ── Individual: incident-type label, appears from zoom 12 ────────
      mapInstance.addLayer({
        id: 'unclustered-label',
        type: 'symbol',
        source: 'incidents',
        filter: ['!', ['has', 'point_count']],
        minzoom: 12,
        layout: {
          'text-field': ['get', 'short_type'],
          'text-font': ['DIN Offc Pro Bold', 'Arial Unicode MS Bold'],
          'text-size': 10,
          'text-offset': [0, 1.8],
          'text-anchor': 'top',
          'text-allow-overlap': false,
        },
        paint: {
          'text-color': '#ffffff',
          'text-halo-color': 'rgba(0,0,0,0.8)',
          'text-halo-width': 1.5,
        },
      });

      setMapLoaded(true);

      // ── Cluster click → zoom in ──────────────────────────────────────
      mapInstance.on('click', 'clusters', (e: any) => {
        const features = mapInstance.queryRenderedFeatures(e.point, { layers: ['clusters'] });
        if (!features.length) return;
        const clusterId = features[0].properties?.cluster_id;
        (mapInstance.getSource('incidents') as mapboxgl.GeoJSONSource).getClusterExpansionZoom(
          clusterId,
          (err: Error | null, zoom: number) => {
            if (err) return;
            mapInstance.easeTo({
              center: (features[0].geometry as any).coordinates,
              zoom: zoom + 0.5,
              duration: 400,
            });
          }
        );
      });

      // ── Individual hover → popup ─────────────────────────────────────
      mapInstance.on('mouseenter', 'unclustered', (e: any) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const props = feature.properties as any;
        const coords = (feature.geometry as any).coordinates.slice() as [number, number];
        const color = props.color || '#888';
        const location = [props.address, props.suburb].filter(Boolean).join(', ') || 'Unknown location';
        const sourceLabel = props.location_source === 'OFFICIAL_FEED' ? '● Official' : '◌ Estimated';

        popupRef.current?.remove();
        const popup = new mapboxgl.Popup({
          offset: 16,
          closeButton: false,
          closeOnClick: false,
          className: 'map-incident-popup',
          maxWidth: '280px',
        }).setHTML(`
          <div class="map-popup-card">
            <div class="map-popup-accent" style="background:${color}"></div>
            <div class="map-popup-body">
              <div class="map-popup-agency" style="color:${color}">${props.agency_code || 'UNK'}</div>
              <div class="map-popup-type">${props.incident_type || 'Unknown incident'}</div>
              <div class="map-popup-location">${location}</div>
              <div class="map-popup-footer">
                <span class="map-popup-time">${props.time}</span>
                <span class="map-popup-source">${sourceLabel}</span>
              </div>
            </div>
          </div>
        `).setLngLat(coords).addTo(mapInstance);

        popupRef.current = popup;
        mapInstance.getCanvas().style.cursor = 'pointer';
      });

      mapInstance.on('mouseleave', 'unclustered', () => {
        popupRef.current?.remove();
        popupRef.current = null;
        mapInstance.getCanvas().style.cursor = '';
      });

      mapInstance.on('mouseenter', 'clusters', () => {
        mapInstance.getCanvas().style.cursor = 'pointer';
      });
      mapInstance.on('mouseleave', 'clusters', () => {
        mapInstance.getCanvas().style.cursor = '';
      });

      // ── Individual click → open modal ────────────────────────────────
      mapInstance.on('click', 'unclustered', (e: any) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const id = feature.properties?.id;
        if (id != null) onIncidentClickRef.current(Number(id));
      });
    });

    map.current = mapInstance;

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      popupRef.current?.remove();
      mapInstance.remove();
      map.current = null;
      setMapLoaded(false);
    };
  }, [mapboxToken]);

  // Pulse animation for active-halo layer
  useEffect(() => {
    if (!mapLoaded || !map.current) return;
    let phase = 0;
    const animate = () => {
      phase += 0.04;
      const radius = 14 + 7 * Math.sin(phase);
      const opacity = 0.06 + 0.14 * Math.abs(Math.sin(phase));
      try {
        map.current?.setPaintProperty('active-halo', 'circle-radius', radius);
        map.current?.setPaintProperty('active-halo', 'circle-opacity', opacity);
      } catch {
        /* map removing */
      }
      animFrameRef.current = requestAnimationFrame(animate);
    };
    animFrameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [mapLoaded]);

  useEffect(() => {
    if (map.current) setTimeout(() => map.current?.resize(), 50);
  }, [isFullscreen]);

  useEffect(() => {
    if (!isFullscreen) return;
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsFullscreen(false); };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isFullscreen]);

  const fetchMapData = useCallback(async () => {
    try {
      const data = await getMapIncidents(48);
      setIncidents(data);
    } catch (err) {
      console.error('Failed to fetch map incidents:', err);
    }
  }, []);

  useEffect(() => { fetchMapData(); }, [fetchMapData, refreshTrigger]);

  // Apply agency filters
  const filteredIncidents = incidents.filter((inc) => {
    const code = inc.agency_code ?? '';
    if (agencyFilters.enabled[code] === false) return false;
    if (code === 'CFS' && agencyFilters.cfsAlarmLevel !== 'all') {
      if (inc.alarm_level === null || inc.alarm_level < agencyFilters.cfsAlarmLevel) return false;
    }
    if (code === 'MFS' && agencyFilters.mfsAlarmLevel !== 'all') {
      if (inc.alarm_level === null || inc.alarm_level < agencyFilters.mfsAlarmLevel) return false;
    }
    if (code === 'WAZE' && agencyFilters.wazeCrashesOnly) {
      if (!inc.incident_type?.toLowerCase().includes('accident')) return false;
    }
    return true;
  });

  // Push filtered incidents to the GeoJSON source
  useEffect(() => {
    if (!map.current || !mapLoaded) return;
    const source = map.current.getSource('incidents') as mapboxgl.GeoJSONSource | undefined;
    if (!source) return;

    source.setData({
      type: 'FeatureCollection',
      features: filteredIncidents
        .filter(inc => inc.latitude && inc.longitude)
        .map(inc => ({
          type: 'Feature' as const,
          id: inc.id,
          geometry: {
            type: 'Point' as const,
            coordinates: [inc.longitude, inc.latitude],
          },
          properties: {
            id: inc.id,
            agency_code: inc.agency_code,
            incident_type: inc.incident_type,
            alarm_level: inc.alarm_level ?? 0,
            status: inc.status,
            address: inc.address,
            suburb: inc.suburb,
            location_source: inc.location_source,
            color: AGENCY_COLORS[inc.agency_code || ''] || '#888888',
            short_type: shortType(inc.incident_type),
            time: formatTime(inc.incident_date),
          },
        })),
    });
  }, [filteredIncidents, mapLoaded]);

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
