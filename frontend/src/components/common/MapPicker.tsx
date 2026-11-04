import React from 'react';
import { CivicFixMap } from './CivicFixMap';

interface MapPickerProps {
  latitude: number;
  longitude: number;
  onChange: (lat: number, lon: number, addressSuggestion?: string) => void;
  height?: string;
  disabled?: boolean;
}

export const MapPicker: React.FC<MapPickerProps> = ({
  latitude,
  longitude,
  onChange,
  height = '320px',
  disabled = false,
}) => {
  return (
    <CivicFixMap
      mode="picker"
      latitude={latitude}
      longitude={longitude}
      onLocationChange={onChange}
      height={height}
      disabled={disabled}
    />
  );
};
