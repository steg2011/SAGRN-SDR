import React from 'react';
import { Agency } from '../types';

interface AgencyFilterProps {
  agencies: Agency[];
  selectedAgencies: Set<string>;
  onToggle: (agencyCode: string) => void;
  disabled?: boolean;
}

export const AgencyFilter: React.FC<AgencyFilterProps> = ({
  agencies,
  selectedAgencies,
  onToggle,
  disabled = false,
}) => {
  const isSelected = (code: string) => selectedAgencies.has(code);
  const noneSelected = selectedAgencies.size === 0;

  return (
    <div className={`agency-filter ${disabled ? 'disabled' : ''}`}>
      {agencies.map((agency) => (
        <button
          key={agency.code}
          className={`agency-btn ${isSelected(agency.code) || noneSelected ? 'active' : 'inactive'}`}
          style={{
            borderColor: disabled ? '#444' : (isSelected(agency.code) || noneSelected ? agency.color : '#555'),
          }}
          onClick={() => !disabled && onToggle(agency.code)}
          disabled={disabled}
        >
          {agency.code}
        </button>
      ))}
    </div>
  );
};
