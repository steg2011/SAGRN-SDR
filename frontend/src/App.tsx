import React, { useState, useEffect, useCallback } from 'react';
import { Incident, Agency, Stats } from './types';
import { getIncidents, getAgencies, getStats } from './services/api';
import { IncidentCard } from './components/IncidentCard';
import { IncidentDetail } from './components/IncidentDetail';
import { AgencyFilter } from './components/AgencyFilter';
import './App.css';

const REFRESH_INTERVAL = 10000; // 10 seconds

function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [agencies, setAgencies] = useState<Agency[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selectedAgency, setSelectedAgency] = useState<string>('ALL');
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const fetchData = useCallback(async () => {
    try {
      const [incidentsData, agenciesData, statsData] = await Promise.all([
        getIncidents(selectedAgency === 'ALL' ? undefined : selectedAgency),
        getAgencies(),
        getStats(),
      ]);

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
  }, [selectedAgency]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleAgencySelect = (agency: string) => {
    setSelectedAgency(agency);
    setLoading(true);
  };

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
          <h1>SAGRN SDR Monitor</h1>
          <span className="subtitle">South Australia Emergency Services</span>
        </div>
        <div className="header-right">
          {stats && (
            <div className="stats">
              <span className="stat">
                <strong>{stats.active_incidents}</strong> active
              </span>
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

      <AgencyFilter
        agencies={agencies}
        selectedAgency={selectedAgency}
        onSelect={handleAgencySelect}
      />

      {error && <div className="error-banner">{error}</div>}

      <main className="incident-list">
        {incidents.length === 0 ? (
          <div className="no-incidents">
            No incidents found for the selected filter.
          </div>
        ) : (
          incidents.map((incident) => (
            <IncidentCard
              key={incident.id}
              incident={incident}
              onClick={() => setSelectedIncident(incident)}
            />
          ))
        )}
      </main>

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
