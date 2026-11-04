import React from 'react';
import { CivicFixMap, MapComplaintItem } from './CivicFixMap';

export type { MapComplaintItem };

interface MapViewerProps {
  complaints: MapComplaintItem[];
  height?: string;
  center?: [number, number];
  zoom?: number;
  onSelectComplaint?: (id: string) => void;
}

export const MapViewer: React.FC<MapViewerProps> = ({
  complaints,
  height = '500px',
  center,
  zoom,
  onSelectComplaint,
}) => {
  return (
    <CivicFixMap
      mode="viewer"
      complaints={complaints}
      height={height}
      center={center}
      zoom={zoom}
      onSelectComplaint={onSelectComplaint}
    />
  );
};
