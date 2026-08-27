import React, { useCallback } from 'react';
import { Agency, AgencyFilters } from '../types';

interface FilterMenuProps {
  isOpen: boolean;
  onClose: () => void;
  agencies: Agency[];
  filters: AgencyFilters;
  onFiltersChange: (filters: AgencyFilters) => void;
}

export const FilterMenu: React.FC<FilterMenuProps> = ({
  isOpen,
  onClose,
  agencies,
  filters,
  onFiltersChange,
}) => {
  const toggleAgency = useCallback((code: string) => {
    const currentlyEnabled = filters.enabled[code] !== false;
    const newEnabled = { ...filters.enabled };
    if (currentlyEnabled) {
      newEnabled[code] = false;
    } else {
      delete newEnabled[code];
    }
    onFiltersChange({
      ...filters,
      enabled: newEnabled,
    });
  }, [filters, onFiltersChange]);

  const agencyColor = (code: string): string => {
    return agencies.find(a => a.code === code)?.color ?? '#555';
  };

  const agencyName = (code: string): string => {
    return agencies.find(a => a.code === code)?.name ?? code;
  };

  const isEnabled = (code: string): boolean => {
    return filters.enabled[code] !== false;
  };

  return (
    <>
      {isOpen && <div className="filter-overlay" onClick={onClose} />}
      <div className={`filter-panel ${isOpen ? 'open' : ''}`}>
        <div className="filter-panel-header">
          <h2>Filters</h2>
          <button className="filter-panel-close" onClick={onClose}>&times;</button>
        </div>
        <div className="filter-panel-body">

          {/* SAAS */}
          <div className="filter-agency-section">
            <div className="filter-agency-row">
              <button
                className={`filter-agency-toggle ${isEnabled('SAAS') ? 'on' : 'off'}`}
                style={{ borderColor: isEnabled('SAAS') ? agencyColor('SAAS') : '#555' }}
                onClick={() => toggleAgency('SAAS')}
              >
                <span className="toggle-indicator">{isEnabled('SAAS') ? 'ON' : 'OFF'}</span>
                <span className="toggle-label">SAAS</span>
                <span className="toggle-name">{agencyName('SAAS')}</span>
              </button>
            </div>
            {isEnabled('SAAS') && (
              <div className="filter-sub-options">
                <span className="filter-sub-label">Priority</span>
                <div className="filter-btn-group">
                  {(['all', 1, 2, 3] as const).map((val) => (
                    <button
                      key={val}
                      className={`filter-option-btn ${filters.saasPriority === val ? 'selected' : ''}`}
                      onClick={() => onFiltersChange({ ...filters, saasPriority: val })}
                    >
                      {val === 'all' ? 'All' : `P${val}`}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* MedStar */}
          <div className="filter-agency-section">
            <div className="filter-agency-row">
              <button
                className={`filter-agency-toggle ${isEnabled('MedStar') ? 'on' : 'off'}`}
                style={{ borderColor: isEnabled('MedStar') ? agencyColor('MedStar') : '#555' }}
                onClick={() => toggleAgency('MedStar')}
              >
                <span className="toggle-indicator">{isEnabled('MedStar') ? 'ON' : 'OFF'}</span>
                <span className="toggle-label">MedStar</span>
                <span className="toggle-name">{agencyName('MedStar')}</span>
              </button>
            </div>
          </div>

          {/* CFS */}
          <div className="filter-agency-section">
            <div className="filter-agency-row">
              <button
                className={`filter-agency-toggle ${isEnabled('CFS') ? 'on' : 'off'}`}
                style={{ borderColor: isEnabled('CFS') ? agencyColor('CFS') : '#555' }}
                onClick={() => toggleAgency('CFS')}
              >
                <span className="toggle-indicator">{isEnabled('CFS') ? 'ON' : 'OFF'}</span>
                <span className="toggle-label">CFS</span>
                <span className="toggle-name">{agencyName('CFS')}</span>
              </button>
            </div>
            {isEnabled('CFS') && (
              <div className="filter-sub-options">
                <span className="filter-sub-label">Alarm Level</span>
                <div className="filter-btn-group">
                  {(['all', 2, 3, 4] as const).map((val) => (
                    <button
                      key={val}
                      className={`filter-option-btn ${filters.cfsAlarmLevel === val ? 'selected' : ''}`}
                      onClick={() => onFiltersChange({ ...filters, cfsAlarmLevel: val })}
                    >
                      {val === 'all' ? 'All' : `${val}+`}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* MFS */}
          <div className="filter-agency-section">
            <div className="filter-agency-row">
              <button
                className={`filter-agency-toggle ${isEnabled('MFS') ? 'on' : 'off'}`}
                style={{ borderColor: isEnabled('MFS') ? agencyColor('MFS') : '#555' }}
                onClick={() => toggleAgency('MFS')}
              >
                <span className="toggle-indicator">{isEnabled('MFS') ? 'ON' : 'OFF'}</span>
                <span className="toggle-label">MFS</span>
                <span className="toggle-name">{agencyName('MFS')}</span>
              </button>
            </div>
            {isEnabled('MFS') && (
              <div className="filter-sub-options">
                <span className="filter-sub-label">Alarm Level</span>
                <div className="filter-btn-group">
                  {(['all', 2, 3, 4] as const).map((val) => (
                    <button
                      key={val}
                      className={`filter-option-btn ${filters.mfsAlarmLevel === val ? 'selected' : ''}`}
                      onClick={() => onFiltersChange({ ...filters, mfsAlarmLevel: val })}
                    >
                      {val === 'all' ? 'All' : `${val}+`}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* SES */}
          <div className="filter-agency-section">
            <div className="filter-agency-row">
              <button
                className={`filter-agency-toggle ${isEnabled('SES') ? 'on' : 'off'}`}
                style={{ borderColor: isEnabled('SES') ? agencyColor('SES') : '#555' }}
                onClick={() => toggleAgency('SES')}
              >
                <span className="toggle-indicator">{isEnabled('SES') ? 'ON' : 'OFF'}</span>
                <span className="toggle-label">SES</span>
                <span className="toggle-name">{agencyName('SES')}</span>
              </button>
            </div>
          </div>

          {/* TMC */}
          <div className="filter-agency-section">
            <div className="filter-agency-row">
              <button
                className={`filter-agency-toggle ${isEnabled('TMC') ? 'on' : 'off'}`}
                style={{ borderColor: isEnabled('TMC') ? agencyColor('TMC') : '#555' }}
                onClick={() => toggleAgency('TMC')}
              >
                <span className="toggle-indicator">{isEnabled('TMC') ? 'ON' : 'OFF'}</span>
                <span className="toggle-label">TMC</span>
                <span className="toggle-name">{agencyName('TMC')}</span>
              </button>
            </div>
          </div>

          {/* WAZE */}
          <div className="filter-agency-section">
            <div className="filter-agency-row">
              <button
                className={`filter-agency-toggle ${isEnabled('WAZE') ? 'on' : 'off'}`}
                style={{ borderColor: isEnabled('WAZE') ? agencyColor('WAZE') : '#555' }}
                onClick={() => toggleAgency('WAZE')}
              >
                <span className="toggle-indicator">{isEnabled('WAZE') ? 'ON' : 'OFF'}</span>
                <span className="toggle-label">WAZE</span>
                <span className="toggle-name">{agencyName('WAZE')}</span>
              </button>
            </div>
            {isEnabled('WAZE') && (
              <div className="filter-sub-options">
                <span className="filter-sub-label">Type</span>
                <div className="filter-btn-group">
                  <button
                    className={`filter-option-btn ${!filters.wazeCrashesOnly && !filters.wazeDitRoadsOnly && !filters.wazeMotorwaysOnly ? 'selected' : ''}`}
                    onClick={() => onFiltersChange({
                      ...filters,
                      wazeCrashesOnly: false,
                      wazeDitRoadsOnly: false,
                      wazeMotorwaysOnly: false,
                    })}
                  >
                    All
                  </button>
                  <button
                    className={`filter-option-btn ${filters.wazeCrashesOnly ? 'selected' : ''}`}
                    onClick={() => onFiltersChange({ ...filters, wazeCrashesOnly: !filters.wazeCrashesOnly })}
                  >
                    Crashes Only
                  </button>
                  {/* DIT Roads and Motorways are both road-scope filters, and motorways
                      are a subset of DIT roads, so selecting one clears the other. */}
                  <button
                    className={`filter-option-btn ${filters.wazeDitRoadsOnly ? 'selected' : ''}`}
                    onClick={() => onFiltersChange({
                      ...filters,
                      wazeDitRoadsOnly: !filters.wazeDitRoadsOnly,
                      wazeMotorwaysOnly: false,
                    })}
                  >
                    DIT Roads
                  </button>
                  <button
                    className={`filter-option-btn ${filters.wazeMotorwaysOnly ? 'selected' : ''}`}
                    onClick={() => onFiltersChange({
                      ...filters,
                      wazeMotorwaysOnly: !filters.wazeMotorwaysOnly,
                      wazeDitRoadsOnly: false,
                    })}
                  >
                    Motorways
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* SAPN - SA Power Networks outages */}
          <div className="filter-agency-section">
            <div className="filter-agency-row">
              <button
                className={`filter-agency-toggle ${isEnabled('SAPN') ? 'on' : 'off'}`}
                style={{ borderColor: isEnabled('SAPN') ? agencyColor('SAPN') : '#555' }}
                onClick={() => toggleAgency('SAPN')}
              >
                <span className="toggle-indicator">{isEnabled('SAPN') ? 'ON' : 'OFF'}</span>
                <span className="toggle-label">SAPN</span>
                <span className="toggle-name">Power Outages</span>
              </button>
            </div>
            {isEnabled('SAPN') && (
              <div className="filter-sub-options">
                <span className="filter-sub-label">Type</span>
                <div className="filter-btn-group">
                  {(['all', 'unplanned', 'planned'] as const).map((val) => (
                    <button
                      key={val}
                      className={`filter-option-btn ${filters.sapnType === val ? 'selected' : ''}`}
                      onClick={() => onFiltersChange({ ...filters, sapnType: val })}
                    >
                      {val === 'all' ? 'All' : val === 'unplanned' ? 'Unplanned' : 'Planned'}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

        </div>
      </div>
    </>
  );
};
