import React, { useEffect, useState } from 'react';
import { Filter, RefreshCw, Flame } from 'lucide-react';
import { adminService } from '../../services/adminService';
import { MapViewer } from '../../components/common/MapViewer';
import { HotspotCluster } from '../../types';

export const LiveIssueMapPage: React.FC = () => {
  const [complaints, setComplaints] = useState<any[]>([]);
  const [hotspots, setHotspots] = useState<HotspotCluster[]>([]);
  const [showHotspots, setShowHotspots] = useState<boolean>(true);
  const [showMarkers, setShowMarkers] = useState<boolean>(true);
  const [gridMeters, setGridMeters] = useState<number>(500);
  const [isDemoMode, setIsDemoMode] = useState<boolean>(false);
  const [category, setCategory] = useState<string>('');
  const [status, setStatus] = useState<string>('');
  const [priority, setPriority] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [overdueOnly, setOverdueOnly] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);

  const loadMapData = () => {
    setLoading(true);
    Promise.all([
      adminService.getMapComplaints({
        category: category || undefined,
        status: status || undefined,
        priority: priority || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
      adminService.getMapHotspots({
        category: category || undefined,
        status: status || undefined,
        priority: priority || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        overdue_only: overdueOnly,
        grid_size_meters: gridMeters,
      }).catch(() => null),
    ])
      .then(([pinsRes, hotspotRes]) => {
        setComplaints(pinsRes.complaints || []);
        if (hotspotRes) {
          setHotspots(hotspotRes.hotspots || []);
          setIsDemoMode(Boolean(hotspotRes.is_demonstration_mode));
        }
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadMapData();
  }, [category, status, priority, dateFrom, dateTo, overdueOnly, gridMeters]);

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Spatial Intelligence</span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Live Municipal Issue Map</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Geospatial complaint density hotspots and incident markers using live persisted database coordinates.
          </p>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-2.5 bg-white p-2.5 rounded-2xl border border-slate-200 shadow-xs text-xs font-semibold self-start sm:self-auto">
          <div className="flex items-center gap-1.5 text-rose-600 bg-rose-50 px-2 py-0.5 rounded-lg border border-rose-100">
            <span className="font-bold">▲</span>
            <span>P1 Critical</span>
          </div>
          <div className="flex items-center gap-1.5 text-orange-600 bg-orange-50 px-2 py-0.5 rounded-lg border border-orange-100">
            <span className="font-bold">◆</span>
            <span>P2 High</span>
          </div>
          <div className="flex items-center gap-1.5 text-blue-600 bg-blue-50 px-2 py-0.5 rounded-lg border border-blue-100">
            <span className="font-bold">●</span>
            <span>P3 Normal</span>
          </div>
          <div className="flex items-center gap-1.5 text-slate-600 bg-slate-100 px-2 py-0.5 rounded-lg border border-slate-200">
            <span className="font-bold">■</span>
            <span>P4 Low</span>
          </div>
          <div className="flex items-center gap-1.5 text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-lg border border-emerald-100">
            <span className="font-bold">✓</span>
            <span>Resolved</span>
          </div>
        </div>
      </div>

      {isDemoMode && (
        <div className="px-3 py-2 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs font-medium">
          Dataset Notice: Demonstration or seeded sample citizen accounts exist in this environment; all hotspot buckets remain dynamically computed from database records.
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <Filter className="w-4 h-4 text-slate-400" />
              <span className="font-semibold">Filters:</span>
            </div>

            <select
              aria-label="Filter Category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="px-3 py-1.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-700"
            >
              <option value="">All Categories</option>
              <option value="ROADS">Roads & Potholes</option>
              <option value="STREETLIGHTS">Street Lighting</option>
              <option value="GARBAGE">Garbage Accumulation</option>
              <option value="DRAINAGE">Drainage & Waterlogging</option>
              <option value="WATER_SUPPLY">Water Supply Leaks</option>
              <option value="FOOTPATHS">Footpaths</option>
              <option value="TREES_HAZARDS">Trees & Hazards</option>
              <option value="SANITATION">Sanitation</option>
            </select>

            <select
              aria-label="Filter Priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="px-3 py-1.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-700"
            >
              <option value="">All Priorities</option>
              <option value="P1">P1 Critical (Red)</option>
              <option value="P2">P2 High (Orange)</option>
              <option value="P3">P3 Normal (Blue)</option>
              <option value="P4">P4 Low (Slate)</option>
            </select>

            <select
              aria-label="Filter Status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="px-3 py-1.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-700"
            >
              <option value="">All Statuses</option>
              <option value="SUBMITTED">Submitted</option>
              <option value="AI_ANALYSIS_PENDING">AI Analysis Pending</option>
              <option value="UNDER_REVIEW">Under Review</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="AWAITING_CITIZEN_CONFIRMATION">Awaiting Confirmation</option>
              <option value="RESOLVED">Resolved</option>
            </select>

            <input
              type="date"
              aria-label="From Date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="px-2.5 py-1.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-700"
            />
            <input
              type="date"
              aria-label="To Date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="px-2.5 py-1.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-700"
            />
          </div>

          <button
            onClick={loadMapData}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 border border-slate-200 hover:bg-slate-100 rounded-xl text-xs font-semibold text-slate-700 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh ({complaints.length} Pins • {hotspots.length} Hotspots)
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-slate-100 text-xs text-slate-700">
          <label className="inline-flex items-center gap-1.5 cursor-pointer font-semibold">
            <input
              type="checkbox"
              checked={showHotspots}
              onChange={(e) => setShowHotspots(e.target.checked)}
              className="rounded border-slate-300"
            />
            <Flame className="w-3.5 h-3.5 text-rose-500" />
            Show Hotspot Density Overlay
          </label>

          <label className="inline-flex items-center gap-1.5 cursor-pointer font-semibold">
            <input
              type="checkbox"
              checked={showMarkers}
              onChange={(e) => setShowMarkers(e.target.checked)}
              className="rounded border-slate-300"
            />
            Show Incident Pins
          </label>

          <label className="inline-flex items-center gap-1.5 cursor-pointer font-semibold text-rose-700">
            <input
              type="checkbox"
              checked={overdueOnly}
              onChange={(e) => setOverdueOnly(e.target.checked)}
              className="rounded border-slate-300"
            />
            SLA Overdue Hotspots Only
          </label>

          <div className="flex items-center gap-1.5">
            <span className="text-slate-500">Cluster Grid:</span>
            <select
              aria-label="Hotspot Grid Size"
              value={gridMeters}
              onChange={(e) => setGridMeters(Number(e.target.value))}
              className="px-2 py-1 border border-slate-300 rounded-lg text-xs bg-white"
            >
              <option value={250}>250m</option>
              <option value={500}>500m</option>
              <option value={1000}>1 km</option>
              <option value={2000}>2 km</option>
            </select>
          </div>
        </div>
      </div>

      {/* Map Container */}
      <div className="bg-white p-3 rounded-3xl border border-slate-200 shadow-xs">
        <MapViewer
          complaints={complaints}
          hotspots={hotspots}
          showHotspots={showHotspots}
          showMarkers={showMarkers}
          height="620px"
          onSelectComplaint={(id) => (window.location.href = `/admin/complaints/${id}`)}
        />
      </div>
    </div>
  );
};
