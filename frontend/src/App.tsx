import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Incident, Agency, Stats, RawMessage } from './types';
import { getIncidents, getAgencies, getStats, getRawMessages, subscribeToEvents } from './services/api';
import { IncidentCard } from './components/IncidentCard';
import { IncidentDetail } from './components/IncidentDetail';
import { AgencyFilter } from './components/AgencyFilter';
import { RawMessageCard } from './components/RawMessageCard';
import { SearchBar } from './components/SearchBar';
import './App.css';

const FALLBACK_REFRESH_INTERVAL = 30000; // 30 seconds fallback polling (SSE is primary)
const NEW_INCIDENT_DURATION = 30000; // How long to show "new" highlight (30 seconds)
const INITIAL_LOAD = 20; // Initial incidents to display
const LOAD_MORE_INCREMENT = 20; // Incidents to load per "Load More" click

function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [agencies, setAgencies] = useState<Agency[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selectedAgencies, setSelectedAgencies] = useState<Set<string>>(new Set());
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [newIncidentIds, setNewIncidentIds] = useState<Set<number>>(new Set());
  const [rawMode, setRawMode] = useState(false);
  const [rawMessages, setRawMessages] = useState<RawMessage[]>([]);
  const [newRawMessageIds, setNewRawMessageIds] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [displayLimit, setDisplayLimit] = useState(INITIAL_LOAD);
  const [pollerOffline, setPollerOffline] = useState(false);

  // Track which incidents we've seen (persists across renders)
  const seenIncidentIds = useRef<Set<number>>(new Set());
  const seenRawMessageIds = useRef<Set<number>>(new Set());
  const isFirstLoad = useRef(true);
  const isFirstRawLoad = useRef(true);

  const fetchData = useCallback(async () => {
    try {
      // Always fetch all incidents, filter client-side
      const [incidentsData, agenciesData, statsData] = await Promise.all([
        getIncidents(),
        getAgencies(),
        getStats(),
      ]);

      // Detect new incidents (skip on first load)
      if (!isFirstLoad.current) {
        const newIds: number[] = [];
        for (const incident of incidentsData) {
          if (!seenIncidentIds.current.has(incident.id)) {
            newIds.push(incident.id);
          }
        }

        if (newIds.length > 0) {
          // Mark these as new
          setNewIncidentIds(prev => {
            const next = new Set(prev);
            newIds.forEach(id => next.add(id));
            return next;
          });

          // Remove "new" status after duration
          setTimeout(() => {
            setNewIncidentIds(prev => {
              const next = new Set(prev);
              newIds.forEach(id => next.delete(id));
              return next;
            });
          }, NEW_INCIDENT_DURATION);
        }
      }

      // Update seen incidents
      incidentsData.forEach(inc => seenIncidentIds.current.add(inc.id));
      isFirstLoad.current = false;

      setIncidents(incidentsData);
      setAgencies(agenciesData);
      setStats(statsData);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      setError('Failed to load data. Retrying...');
      console.error('Fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchRawData = useCallback(async () => {
    try {
      const rawData = await getRawMessages(200);

      // Detect new raw messages (skip on first load)
      if (!isFirstRawLoad.current) {
        const newIds: number[] = [];
        for (const msg of rawData) {
          if (!seenRawMessageIds.current.has(msg.id)) {
            newIds.push(msg.id);
          }
        }

        if (newIds.length > 0) {
          setNewRawMessageIds(prev => {
            const next = new Set(prev);
            newIds.forEach(id => next.add(id));
            return next;
          });

          setTimeout(() => {
            setNewRawMessageIds(prev => {
              const next = new Set(prev);
              newIds.forEach(id => next.delete(id));
              return next;
            });
          }, NEW_INCIDENT_DURATION);
        }
      }

      rawData.forEach(msg => seenRawMessageIds.current.add(msg.id));
      isFirstRawLoad.current = false;

      setRawMessages(rawData);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      setError('Failed to load raw messages. Retrying...');
      console.error('Fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial data fetch
  useEffect(() => {
    if (rawMode) {
      fetchRawData();
    } else {
      fetchData();
    }
  }, [fetchData, fetchRawData, rawMode]);

  // SSE subscription for real-time updates
  useEffect(() => {
    const fetchCurrent = rawMode ? fetchRawData : fetchData;

    // Subscribe to SSE events
    const unsubscribe = subscribeToEvents({
      onConnected: () => {
        console.log('SSE connected');
      },
      onNewMessage: () => {
        // Refetch data when new message arrives
        fetchCurrent();
      },
      onBatchProcessed: () => {
        // Refetch data when batch is processed
        fetchCurrent();
      },
      onError: (error) => {
        console.error('SSE error:', error);
      },
    });

    // Fallback polling in case SSE has issues
    const fallbackInterval = setInterval(fetchCurrent, FALLBACK_REFRESH_INTERVAL);

    return () => {
      unsubscribe();
      clearInterval(fallbackInterval);
    };
  }, [fetchData, fetchRawData, rawMode]);

  const handleAgencyToggle = (agencyCode: string) => {
    setSelectedAgencies((prev) => {
      const next = new Set(prev);
      if (next.has(agencyCode)) {
        next.delete(agencyCode);
      } else {
        next.add(agencyCode);
      }
      return next;
    });
    // Reset display limit when filter changes
    setDisplayLimit(INITIAL_LOAD);
  };

  // Reset display limit when search query changes
  useEffect(() => {
    setDisplayLimit(INITIAL_LOAD);
  }, [searchQuery]);

  // Monitor poller health - check if no updates received in 1 hour
  useEffect(() => {
    const checkHealth = () => {
      const timeSinceUpdate = Date.now() - lastUpdate.getTime();
      const oneHourMs = 3600000; // 1 hour in milliseconds
      setPollerOffline(timeSinceUpdate > oneHourMs);
    };

    checkHealth();
    const interval = setInterval(checkHealth, 60000); // Check every minute

    return () => clearInterval(interval);
  }, [lastUpdate]);

  // Filter incidents based on selected agencies (empty = show all)
  const agencyFilteredIncidents = selectedAgencies.size === 0
    ? incidents
    : incidents.filter((inc) => inc.agency_code && selectedAgencies.has(inc.agency_code));

  // Filter incidents based on search query
  const filteredIncidents = searchQuery.trim() === ''
    ? agencyFilteredIncidents
    : agencyFilteredIncidents.filter((inc) => {
        const q = searchQuery.toLowerCase();
        return (
          inc.incident_type?.toLowerCase().includes(q) ||
          inc.address?.toLowerCase().includes(q) ||
          inc.suburb?.toLowerCase().includes(q) ||
          inc.incident_number?.toLowerCase().includes(q) ||
          inc.units.some(u => u.callsign.toLowerCase().includes(q))
        );
      });

  // Apply display limit for lazy loading
  const visibleIncidents = filteredIncidents.slice(0, displayLimit);
  const hasMore = filteredIncidents.length > displayLimit;

  if (loading && incidents.length === 0) {
    return (
      <div className="app">
        <div className="loading">Loading incidents...</div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <h1>SAGRN Pager Feed</h1>
          <span className="subtitle">South Australia Emergency Services</span>
        </div>
        <div className="header-right">
          {stats && (
            <div className="stats">
              <span className="stat">
                <strong>{stats.total_incidents_24h}</strong> today
              </span>
            </div>
          )}
          <span className="last-update">
            Updated: {lastUpdate.toLocaleTimeString()}
          </span>
        </div>
      </header>

      <div className="filter-bar">
        <AgencyFilter
          agencies={agencies}
          selectedAgencies={selectedAgencies}
          onToggle={handleAgencyToggle}
          disabled={rawMode}
        />
        <SearchBar
          value={searchQuery}
          onChange={setSearchQuery}
          disabled={rawMode}
        />
        <button
          className={`raw-btn ${rawMode ? 'active' : ''}`}
          onClick={() => {
            setRawMode(!rawMode);
            setDisplayLimit(INITIAL_LOAD);
          }}
        >
          RAW
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {pollerOffline && (
        <div className="health-warning">
          ⚠️ Poller Offline - No updates received in over 1 hour
        </div>
      )}

      {rawMode ? (
        <main className="raw-message-list">
          {rawMessages.length === 0 ? (
            <div className="no-incidents">
              No raw messages available.
            </div>
          ) : (
            rawMessages.map((msg) => (
              <RawMessageCard
                key={msg.id}
                message={msg}
                isNew={newRawMessageIds.has(msg.id)}
              />
            ))
          )}
        </main>
      ) : (
        <div>
          <main className="incident-list">
            {filteredIncidents.length === 0 ? (
              <div className="no-incidents">
                No incidents found for the selected filter.
              </div>
            ) : (
              visibleIncidents.map((incident) => (
                <IncidentCard
                  key={incident.id}
                  incident={incident}
                  isNew={newIncidentIds.has(incident.id)}
                  onClick={() => setSelectedIncident(incident)}
                />
              ))
            )}
          </main>
          {hasMore && (
            <div className="load-more-container">
              <button
                className="load-more-btn"
                onClick={() => setDisplayLimit(prev => prev + LOAD_MORE_INCREMENT)}
              >
                Load More ({filteredIncidents.length - displayLimit} remaining)
              </button>
            </div>
          )}
        </div>
      )}

      {selectedIncident && (
        <IncidentDetail
          incident={selectedIncident}
          onClose={() => setSelectedIncident(null)}
        />
      )}
    </div>
  );
}

export default App;
