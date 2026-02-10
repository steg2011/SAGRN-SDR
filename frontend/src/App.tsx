import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Incident, Agency, Stats, RawMessage } from './types';
import { getIncidents, getAgencies, getStats, getRawMessages, searchIncidents, subscribeToEvents } from './services/api';
import { IncidentCard } from './components/IncidentCard';
import { IncidentDetail } from './components/IncidentDetail';
import { AgencyFilter } from './components/AgencyFilter';
import { RawMessageCard } from './components/RawMessageCard';
import { SearchBar } from './components/SearchBar';
import './App.css';

const FALLBACK_REFRESH_INTERVAL = 30000; // 30 seconds fallback polling (SSE is primary)
const NEW_INCIDENT_DURATION = 30000; // How long to show "new" highlight (30 seconds)
const PAGE_SIZE = 20; // Incidents per page for infinite scroll

function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [agencies, setAgencies] = useState<Agency[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selectedAgencies, setSelectedAgencies] = useState<Set<string>>(new Set());
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [newIncidentIds, setNewIncidentIds] = useState<Set<number>>(new Set());
  const [rawMode, setRawMode] = useState(false);
  const [rawMessages, setRawMessages] = useState<RawMessage[]>([]);
  const [newRawMessageIds, setNewRawMessageIds] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [pollerOffline, setPollerOffline] = useState(false);

  // Track which incidents we've seen (persists across renders)
  const seenIncidentIds = useRef<Set<number>>(new Set());
  const seenRawMessageIds = useRef<Set<number>>(new Set());
  const isFirstLoad = useRef(true);
  const isFirstRawLoad = useRef(true);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadingMoreRef = useRef(false);

  // Fetch initial page of incidents (replaces old list)
  const fetchData = useCallback(async () => {
    try {
      const agencyFilter = selectedAgencies.size === 1 ? Array.from(selectedAgencies)[0] : undefined;
      const isSearch = searchQuery.trim() !== '';

      const incidentsPromise = isSearch
        ? searchIncidents(searchQuery, agencyFilter, PAGE_SIZE, 0)
        : getIncidents(agencyFilter, 168, PAGE_SIZE, 0);

      const [incidentsData, agenciesData, statsData] = await Promise.all([
        incidentsPromise,
        getAgencies(),
        getStats(),
      ]);

      // Detect new incidents (skip on first load, skip for search results)
      if (!isFirstLoad.current && !isSearch) {
        const newIds: number[] = [];
        for (const incident of incidentsData) {
          if (!seenIncidentIds.current.has(incident.id)) {
            newIds.push(incident.id);
          }
        }

        if (newIds.length > 0) {
          setNewIncidentIds(prev => {
            const next = new Set(prev);
            newIds.forEach(id => next.add(id));
            return next;
          });

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
      setHasMore(incidentsData.length >= PAGE_SIZE);
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
  }, [searchQuery, selectedAgencies]);

  // Load more incidents (append to existing list)
  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !hasMore) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);

    try {
      const agencyFilter = selectedAgencies.size === 1 ? Array.from(selectedAgencies)[0] : undefined;
      const isSearch = searchQuery.trim() !== '';
      const offset = incidents.length;

      const moreData = isSearch
        ? await searchIncidents(searchQuery, agencyFilter, PAGE_SIZE, offset)
        : await getIncidents(agencyFilter, 168, PAGE_SIZE, offset);

      if (moreData.length > 0) {
        // Deduplicate by ID
        const existingIds = new Set(incidents.map(inc => inc.id));
        const newIncidents = moreData.filter(inc => !existingIds.has(inc.id));
        setIncidents(prev => [...prev, ...newIncidents]);
        moreData.forEach(inc => seenIncidentIds.current.add(inc.id));
      }

      setHasMore(moreData.length >= PAGE_SIZE);
    } catch (err) {
      console.error('Load more error:', err);
    } finally {
      setLoadingMore(false);
      loadingMoreRef.current = false;
    }
  }, [incidents, hasMore, searchQuery, selectedAgencies]);

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

    const unsubscribe = subscribeToEvents({
      onConnected: () => {
        console.log('SSE connected');
      },
      onNewMessage: () => {
        fetchCurrent();
      },
      onBatchProcessed: () => {
        fetchCurrent();
      },
      onError: (error) => {
        console.error('SSE error:', error);
      },
    });

    const fallbackInterval = setInterval(fetchCurrent, FALLBACK_REFRESH_INTERVAL);

    return () => {
      unsubscribe();
      clearInterval(fallbackInterval);
    };
  }, [fetchData, fetchRawData, rawMode]);

  // IntersectionObserver for infinite scroll
  useEffect(() => {
    if (rawMode) return;

    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loadingMoreRef.current && hasMore) {
          loadMore();
        }
      },
      { rootMargin: '200px' }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore, hasMore, rawMode]);

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
  };

  // Monitor poller health - check if no updates received in 1 hour
  useEffect(() => {
    const checkHealth = () => {
      const timeSinceUpdate = Date.now() - lastUpdate.getTime();
      const oneHourMs = 3600000;
      setPollerOffline(timeSinceUpdate > oneHourMs);
    };

    checkHealth();
    const interval = setInterval(checkHealth, 60000);

    return () => clearInterval(interval);
  }, [lastUpdate]);

  // Filter by agency client-side when multiple agencies selected
  const visibleIncidents = selectedAgencies.size > 1
    ? incidents.filter((inc) => inc.agency_code && selectedAgencies.has(inc.agency_code))
    : incidents;

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
            {visibleIncidents.length === 0 && !loading ? (
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
          <div ref={sentinelRef} className="scroll-sentinel">
            {loadingMore && (
              <div className="loading-more">Loading more incidents...</div>
            )}
          </div>
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
