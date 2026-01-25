import React from 'react';
import { Agency } from '../types';

interface AgencyFilterProps {
  agencies: Agency[];
  selectedAgency: string;
  onSelect: (agency: string) => void;
}

export const AgencyFilter: React.FC<AgencyFilterProps> = ({
  agencies,
  selectedAgency,
  onSelect,
}) => {
  return (
    <div className="agency-filter">
      <button
        className={`agency-btn ${selectedAgency === 'ALL' ? 'active' : ''}`}
        onClick={() => onSelect('ALL')}
      >
        ALL
      </button>
      {agencies.map((agency) => (
        <button
          key={agency.code}
          className={`agency-btn ${selectedAgency === agency.code ? 'active' : ''}`}
          style={{
            backgroundColor: selectedAgency === agency.code ? agency.color : undefined,
            borderColor: agency.color,
          }}
          onClick={() => onSelect(agency.code)}
        >
          {agency.code}
        </button>
      ))}
    </div>
  );
};
