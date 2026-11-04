import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { CivicFixMap } from '../components/common/CivicFixMap';
import { resolveTileConfig, DEFAULT_MAP_TILE_URL } from '../config/mapConfig';

describe('CivicFixMap Interactive Leaflet Component', () => {
  it('uses the verified keyless Esri raster tile configuration', () => {
    const tileConfig = resolveTileConfig();
    expect(tileConfig.tileUrl).toBe(DEFAULT_MAP_TILE_URL);
    expect(tileConfig.tileUrl).toContain('server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}');
    expect(tileConfig.subdomains).toEqual(['a', 'b', 'c', 'd']);
    expect(tileConfig.attribution).toContain('Esri');
  });

  it('renders in picker mode with coordinate display and manual fallback inputs', () => {
    const onLocationChange = vi.fn();

    render(
      <BrowserRouter>
        <CivicFixMap
          mode="picker"
          latitude={17.4399}
          longitude={78.4983}
          onLocationChange={onLocationChange}
          height="350px"
        />
      </BrowserRouter>
    );

    // Coordinate badges and manual inputs are rendered
    expect(screen.getByText(/17\.43990,\s*78\.49830/i)).toBeInTheDocument();
    expect(screen.getByText(/Use My Current Location/i)).toBeInTheDocument();
    expect(screen.getByText(/Manual GPS Coordinate Entry/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText('17.4399')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('78.4983')).toBeInTheDocument();
  });

  it('allows manual coordinate entry and calls onLocationChange with sanitized values', () => {
    const onLocationChange = vi.fn();

    render(
      <BrowserRouter>
        <CivicFixMap
          mode="picker"
          latitude={17.4399}
          longitude={78.4983}
          onLocationChange={onLocationChange}
        />
      </BrowserRouter>
    );

    const latInput = screen.getByPlaceholderText('17.4399');
    const lonInput = screen.getByPlaceholderText('78.4983');
    const submitBtn = screen.getByText('Update Pin on Map');

    fireEvent.change(latInput, { target: { value: '17.3850' } });
    fireEvent.change(lonInput, { target: { value: '78.4867' } });
    fireEvent.click(submitBtn);

    expect(onLocationChange).toHaveBeenCalledWith(17.385, 78.4867);
  });

  it('rejects invalid manual coordinates gracefully without crashing', () => {
    const onLocationChange = vi.fn();

    render(
      <BrowserRouter>
        <CivicFixMap
          mode="picker"
          latitude={17.4399}
          longitude={78.4983}
          onLocationChange={onLocationChange}
        />
      </BrowserRouter>
    );

    const latInput = screen.getByPlaceholderText('17.4399');
    const submitBtn = screen.getByText('Update Pin on Map');

    fireEvent.change(latInput, { target: { value: '999.0' } });
    fireEvent.click(submitBtn);

    expect(screen.getByText(/Latitude must be between -90 and 90/i)).toBeInTheDocument();
    expect(onLocationChange).not.toHaveBeenCalled();
  });

  it('renders in viewer mode displaying complaint markers with Esri attribution', () => {
    const mockComplaints = [
      {
        id: 'comp-1',
        reference_number: 'CF-2026-0001',
        title: 'Deep pothole on arterial road',
        category: 'ROADS',
        latitude: 17.4420,
        longitude: 78.4910,
        priority: 'P1',
        status: 'IN_PROGRESS',
        address: '5th Avenue'
      },
      {
        id: 'comp-2',
        reference_number: 'CF-2026-0002',
        title: 'Faulty sodium lamp',
        category: 'STREETLIGHTS',
        latitude: 17.4450,
        longitude: 78.4950,
        priority: 'P3',
        status: 'SUBMITTED',
        address: '8th Cross'
      }
    ];

    const { container } = render(
      <BrowserRouter>
        <CivicFixMap
          mode="viewer"
          complaints={mockComplaints}
          height="450px"
        />
      </BrowserRouter>
    );

    // Leaflet markers are created for valid complaints
    const markers = container.querySelectorAll('.leaflet-marker-icon');
    expect(markers.length).toBe(2);

    // Verified Esri tile attribution is present
    expect(screen.getByText(/Tiles © Esri/i)).toBeInTheDocument();
  });

  it('renders in crew mode displaying dispatch task markers', () => {
    const mockWorkOrders: any[] = [
      {
        id: 'wo-1',
        complaint_id: 'comp-1',
        complaint_reference: 'CF-2026-0001',
        title: 'Repair crater at 5th Avenue',
        status: 'ASSIGNED',
        complaint_latitude: 17.4420,
        complaint_longitude: 78.4910,
        complaint_priority: 'P1'
      }
    ];

    const { container } = render(
      <BrowserRouter>
        <CivicFixMap
          mode="crew"
          workOrders={mockWorkOrders}
          height="400px"
        />
      </BrowserRouter>
    );

    const markers = container.querySelectorAll('.leaflet-marker-icon');
    expect(markers.length).toBe(1);
    expect(screen.getByText(/Tiles © Esri/i)).toBeInTheDocument();
  });
});

