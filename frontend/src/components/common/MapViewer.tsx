import React from 'react';
import { CivicFixMap, MapComplaintItem, MapHotspotItem } from './CivicFixMap';

export type { MapComplaintItem, MapHotspotItem };

interface MapViewerProps {
  complaints: MapComplaintItem[];
  hotspots?: MapHotspotItem[];
  showHotspots?: boolean;
  showMarkers?: boolean;
  height?: string;
  center?: [number, number];
  zoom?: number;
  onSelectComplaint?: (id: string) => void;
}

export const MapViewer: React.FC<MapViewerProps> = ({
  complaints,
  hotspots = [],
  showHotspots = false,
  showMarkers = true,
  height = '500px',
  center,
  zoom,
  onSelectComplaint,
}) => {
  return (
    <CivicFixMap
      mode="viewer"
      complaints={complaints}
      hotspots={hotspots}
      showHotspots={showHotspots}
      showMarkers={showMarkers}
      height={height}
      center={center}
      zoom={zoom}
      onSelectComplaint={onSelectComplaint}
    />
  );
};
