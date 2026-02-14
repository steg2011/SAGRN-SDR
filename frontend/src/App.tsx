import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Incident, Agency, RawMessage, AgencyFilters } from './types';
import { getIncidents, getIncident, getAgencies, getRawMessages, searchIncidents, subscribeToEvents, getFrontendConfig } from './services/api';
import { IncidentCard } from './components/IncidentCard';
import { IncidentDetail } from './components/IncidentDetail';
import { FilterMenu } from './components/FilterMenu';
import { RawMessageCard } from './components/RawMessageCard';
import { SearchBar } from './components/SearchBar';
import { IncidentMap } from './components/IncidentMap';
import './App.css';

type ViewMode = 'list' | 'map' | 'raw';

const FALLBACK_REFRESH_INTERVAL = 30000; // 30 seconds fallback polling (SSE is primary)
const NEW_INCIDENT_DURATION = 30000; // How long to show "new" highlight (30 seconds)
const PAGE_SIZE = 20; // Incidents per page for infinite scroll

function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [agencies, setAgencies] = useState<Agency[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [newIncidentIds, setNewIncidentIds] = useState<Set<number>>(new Set());
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [rawMessages, setRawMessages] = useState<RawMessage[]>([]);
  const [mapboxToken, setMapboxToken] = useState<string>('');
  const [mapRefreshTrigger, setMapRefreshTrigger] = useState(0);
  const [newRawMessageIds, setNewRawMessageIds] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [pollerOffline, setPollerOffline] = useState(false);
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [agencyFilters, setAgencyFilters] = useState<AgencyFilters>({
    enabled: {},
    saasPriority: 'all',
    cfsAlarmLevel: 'all',
    mfsAlarmLevel: 'all',
    wazeCrashesOnly: false,
  });

  // Track which incidents we've seen (persists across renders)
  const seenIncidentIds = useRef<Set<number>>(new Set());
  const seenRawMessageIds = useRef<Set<number>>(new Set());
  const isFirstLoad = useRef(true);
  const isFirstRawLoad = useRef(true);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadingMoreRef = useRef(false);
  const fetchDebounceRef = useRef<NodeJS.Timeout | null>(null);
  const isFetchingRef = useRef(false);
  const emptyLoadCount = useRef(0); // tracks consecutive loads that added 0 visible items

  // Fetch first page - on initial load replaces list, on refresh merges new items in
  const fetchData = useCallback(async () => {
    try {
      const isSearch = searchQuery.trim() !== '';

      const incidentsPromise = isSearch
        ? searchIncidents(searchQuery, undefined, PAGE_SIZE, 0)
        : getIncidents(undefined, 168, PAGE_SIZE, 0);

      const [incidentsData, agenciesData] = await Promise.all([
        incidentsPromise,
        getAgencies(),
      ]);

      if (isFirstLoad.current || isSearch) {
        // First load or search: replace the entire list
        incidentsData.forEach(inc => seenIncidentIds.current.add(inc.id));
        isFirstLoad.current = false;
        setIncidents(incidentsData);
        setHasMore(incidentsData.length >= PAGE_SIZE);
      } else {
        // Subsequent refresh (SSE/poll): merge new incidents to the top and update existing
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

        // Single setState: prepend new incidents + update existing ones in one pass
        const newIncidents = incidentsData.filter(inc => !seenIncidentIds.current.has(inc.id));
        incidentsData.forEach(inc => seenIncidentIds.current.add(inc.id));
        const updatedMap = new Map(incidentsData.map(inc => [inc.id, inc]));
        setIncidents(prev => {
          const updated = prev.map(existing => updatedMap.get(existing.id) ?? existing);
          return [...newIncidents, ...updated];
        });
      }

      setAgencies(agenciesData);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      setError('Failed to load data. Retrying...');
      console.error('Fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [searchQuery]);

  // Load more incidents (append to existing list)
  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !hasMore) return;
    // Stop auto-loading if 3 consecutive pages added nothing visible (filter mismatch)
    if (emptyLoadCount.current >= 3) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);

    try {
      const isSearch = searchQuery.trim() !== '';
      const offset = incidents.length;

      const moreData = isSearch
        ? await searchIncidents(searchQuery, undefined, PAGE_SIZE, offset)
        : await getIncidents(undefined, 168, PAGE_SIZE, offset);

      if (moreData.length > 0) {
        // Deduplicate by ID
        const existingIds = new Set(incidents.map(inc => inc.id));
        const newIncidents = moreData.filter(inc => !existingIds.has(inc.id));
        setIncidents(prev => [...prev, ...newIncidents]);
        moreData.forEach(inc => seenIncidentIds.current.add(inc.id));

        // Track if this page had zero items matching current filters
        const hasAnyEnabled = Object.values(agencyFilters.enabled).some(v => v === false);
        if (hasAnyEnabled) {
          const matchesFilter = newIncidents.some(inc => {
            const code = inc.agency_code ?? '';
            return agencyFilters.enabled[code] !== false;
          });
          emptyLoadCount.current = matchesFilter ? 0 : emptyLoadCount.current + 1;
        } else {
          emptyLoadCount.current = 0;
        }
      }

      setHasMore(moreData.length >= PAGE_SIZE);
    } catch (err) {
      console.error('Load more error:', err);
    } finally {
      setLoadingMore(false);
      loadingMoreRef.current = false;
    }
  }, [incidents, hasMore, searchQuery, agencyFilters]);

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
    if (viewMode === 'raw') {
      fetchRawData();
    } else {
      fetchData();
    }
  }, [fetchData, fetchRawData, viewMode]);

  // Debounced fetch - coalesces rapid SSE events into a single fetch
  const debouncedFetch = useCallback(() => {
    const fetchCurrent = viewMode === 'raw' ? fetchRawData : fetchData;
    if (fetchDebounceRef.current) clearTimeout(fetchDebounceRef.current);
    fetchDebounceRef.current = setTimeout(() => {
      if (!isFetchingRef.current) {
        isFetchingRef.current = true;
        fetchCurrent().finally(() => { isFetchingRef.current = false; });
      }
      // Also trigger map refresh
      setMapRefreshTrigger(prev => prev + 1);
    }, 500);
  }, [fetchData, fetchRawData, viewMode]);

  // SSE subscription for real-time updates
  useEffect(() => {
    const unsubscribe = subscribeToEvents({
      onConnected: () => {
        console.log('SSE connected');
      },
      onNewMessage: () => {
        debouncedFetch();
      },
      onBatchProcessed: () => {
        debouncedFetch();
      },
      onError: (error) => {
        console.error('SSE error:', error);
      },
    });

    const fallbackInterval = setInterval(debouncedFetch, FALLBACK_REFRESH_INTERVAL);

    return () => {
      unsubscribe();
      clearInterval(fallbackInterval);
      if (fetchDebounceRef.current) clearTimeout(fetchDebounceRef.current);
    };
  }, [debouncedFetch]);

  // Fetch Mapbox token from backend config
  useEffect(() => {
    const envToken = process.env.REACT_APP_MAPBOX_TOKEN;
    if (envToken) {
      setMapboxToken(envToken);
    } else {
      getFrontendConfig().then(config => {
        if (config.mapbox_token) setMapboxToken(config.mapbox_token);
      }).catch(() => {});
    }
  }, []);

  // IntersectionObserver for infinite scroll
  useEffect(() => {
    if (viewMode !== 'list') return;

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
  }, [loadMore, hasMore, viewMode]);

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

  // Reset empty load counter when filters change
  useEffect(() => {
    emptyLoadCount.current = 0;
  }, [agencyFilters]);

  // Apply all client-side filters
  const hasAnyFilter = Object.values(agencyFilters.enabled).some(v => v === false);
  const visibleIncidents = incidents.filter((inc) => {
    const code = inc.agency_code ?? '';

    // Agency enabled/disabled filter
    if (agencyFilters.enabled[code] === false) return false;

    // SAAS priority filter
    if (code === 'SAAS' && agencyFilters.saasPriority !== 'all') {
      if (inc.priority === null || inc.priority > agencyFilters.saasPriority) return false;
    }

    // CFS alarm level filter
    if (code === 'CFS' && agencyFilters.cfsAlarmLevel !== 'all') {
      if (inc.alarm_level === null || inc.alarm_level < agencyFilters.cfsAlarmLevel) return false;
    }

    // MFS alarm level filter
    if (code === 'MFS' && agencyFilters.mfsAlarmLevel !== 'all') {
      if (inc.alarm_level === null || inc.alarm_level < agencyFilters.mfsAlarmLevel) return false;
    }

    // Waze crashes only filter
    if (code === 'WAZE' && agencyFilters.wazeCrashesOnly) {
      if (!inc.incident_type || !inc.incident_type.toLowerCase().includes('accident')) return false;
    }

    return true;
  });

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
          <button
            className={`hamburger-btn ${filterMenuOpen ? 'active' : ''} ${hasAnyFilter ? 'has-filters' : ''}`}
            onClick={() => setFilterMenuOpen(!filterMenuOpen)}
            aria-label="Toggle filters"
          >
            <span className="hamburger-line" />
            <span className="hamburger-line" />
            <span className="hamburger-line" />
          </button>
        </div>
      </header>

      <div className="filter-bar">
        <SearchBar
          value={searchQuery}
          onChange={setSearchQuery}
          disabled={viewMode !== 'list'}
        />
        <div className="view-mode-toggle">
          <button
            className={`view-btn ${viewMode === 'list' ? 'active' : ''}`}
            onClick={() => setViewMode('list')}
          >
            LIST
          </button>
          <button
            className={`view-btn ${viewMode === 'map' ? 'active' : ''}`}
            onClick={() => setViewMode('map')}
          >
            MAP
          </button>
          <button
            className={`view-btn ${viewMode === 'raw' ? 'active' : ''}`}
            onClick={() => setViewMode('raw')}
          >
            RAW
          </button>
        </div>
      </div>

      <FilterMenu
        isOpen={filterMenuOpen}
        onClose={() => setFilterMenuOpen(false)}
        agencies={agencies}
        filters={agencyFilters}
        onFiltersChange={setAgencyFilters}
      />

      {error && <div className="error-banner">{error}</div>}
      {pollerOffline && (
        <div className="health-warning">
          ⚠️ Poller Offline - No updates received in over 1 hour
        </div>
      )}

      {viewMode === 'raw' ? (
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
      ) : viewMode === 'map' ? (
        <IncidentMap
          mapboxToken={mapboxToken}
          onIncidentClick={(id) => {
            const cached = incidents.find(i => i.id === id);
            if (cached) {
              setSelectedIncident(cached);
            } else {
              getIncident(id).then(inc => setSelectedIncident(inc)).catch(() => {});
            }
          }}
          refreshTrigger={mapRefreshTrigger}
          agencyFilters={agencyFilters}
        />
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
