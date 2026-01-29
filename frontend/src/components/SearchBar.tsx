import React, { useState, useEffect } from 'react';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({ value, onChange, disabled }) => {
  const [localValue, setLocalValue] = useState(value);

  // Debounce - only update parent after 300ms of no typing
  useEffect(() => {
    const timer = setTimeout(() => {
      onChange(localValue);
    }, 300);

    return () => clearTimeout(timer);
  }, [localValue, onChange]);

  const handleClear = () => {
    setLocalValue('');
  };

  return (
    <div className="search-bar">
      <input
        type="text"
        placeholder="Search incidents..."
        value={localValue}
        onChange={(e) => setLocalValue(e.target.value)}
        disabled={disabled}
        className="search-input"
      />
      {localValue && (
        <button
          className="search-clear"
          onClick={handleClear}
          disabled={disabled}
          aria-label="Clear search"
        >
          ×
        </button>
      )}
    </div>
  );
};
