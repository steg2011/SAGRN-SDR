import React, { useState, useEffect, useRef } from 'react';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({ value, onChange, disabled }) => {
  const [localValue, setLocalValue] = useState(value);
  const [isOpen, setIsOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Debounce - only update parent after 300ms of no typing
  useEffect(() => {
    const timer = setTimeout(() => {
      onChange(localValue);
    }, 300);

    return () => clearTimeout(timer);
  }, [localValue, onChange]);

  // Focus the field as it pops out
  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  // Collapse when search isn't available (map/raw views)
  useEffect(() => {
    if (disabled) setIsOpen(false);
  }, [disabled]);

  // Collapse on outside click - any active query is kept, flagged by the dot
  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (e: MouseEvent | TouchEvent) => {
      if (!wrapperRef.current?.contains(e.target as Node)) setIsOpen(false);
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, [isOpen]);

  const handleClear = () => {
    setLocalValue('');
    inputRef.current?.focus();
  };

  return (
    <div className={`search-bar ${isOpen ? 'open' : ''}`} ref={wrapperRef}>
      <button
        type="button"
        className={`search-toggle ${localValue ? 'has-query' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        aria-label={isOpen ? 'Close search' : 'Search incidents'}
        aria-expanded={isOpen}
      >
        <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
          <line
            x1="15.5" y1="15.5" x2="20.5" y2="20.5"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          />
        </svg>
      </button>

      <div className="search-popout">
        <input
          ref={inputRef}
          type="text"
          placeholder="Search incidents..."
          value={localValue}
          onChange={(e) => setLocalValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Escape') setIsOpen(false); }}
          disabled={disabled}
          tabIndex={isOpen ? 0 : -1}
          className="search-input"
        />
        {localValue && (
          <button
            className="search-clear"
            onClick={handleClear}
            disabled={disabled}
            tabIndex={isOpen ? 0 : -1}
            aria-label="Clear search"
          >
            &times;
          </button>
        )}
      </div>
    </div>
  );
};
