import React from 'react';
import { Agency } from '../types';

interface AgencyFilterProps {
  agencies: Agency[];
  selectedAgencies: Set<string>;
  onToggle: (agencyCode: string) => void;
}

export const AgencyFilter: React.FC<AgencyFilterProps> = ({
  agencies,
  selectedAgencies,
  onToggle,
}) => {
  const isSelected = (code: string) => selectedAgencies.has(code);
  const noneSelected = selectedAgencies.size === 0;

  return (
    <div className="agency-filter">
      {agencies.map((agency) => (
        <button
          key={agency.code}
          className={`agency-btn ${isSelected(agency.code) || noneSelected ? 'active' : 'inactive'}`}
          style={{
            borderColor: isSelected(agency.code) || noneSelected ? agency.color : '#555',
          }}
          onClick={() => onToggle(agency.code)}
        >
          {agency.code}
        </button>
      ))}
    </div>
  );
};
