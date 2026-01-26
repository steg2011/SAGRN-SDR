import React from 'react';
import { RawMessage } from '../types';

interface RawMessageCardProps {
  message: RawMessage;
  isNew?: boolean;
}

function parseAsUTC(dateString: string): Date {
  let utcString = dateString;
  if (!dateString.endsWith('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
    utcString = dateString.replace(' ', 'T') + 'Z';
  }
  return new Date(utcString);
}

function formatAdelaideTime(dateString: string): string {
  const date = parseAsUTC(dateString);
  return date.toLocaleTimeString('en-AU', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Australia/Adelaide'
  });
}

export const RawMessageCard: React.FC<RawMessageCardProps> = ({ message, isNew }) => {
  return (
    <div className={`raw-message-card ${isNew ? 'raw-message-new' : ''}`}>
      <span className="raw-message-time">{formatAdelaideTime(message.timestamp)}</span>
      <span className="raw-message-content">{message.message}</span>
    </div>
  );
};
