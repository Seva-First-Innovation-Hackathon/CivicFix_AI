import React, { useEffect, useState } from 'react';
import { MapPin, Filter, RefreshCw, AlertCircle, Layers } from 'lucide-react';
import { adminService } from '../../services/adminService';
import { MapViewer } from '../../components/common/MapViewer';

export const LiveIssueMapPage: React.FC = () => {
  const [complaints, setComplaints] = useState<any[]>([]);
  const [category, setCategory] = useState<string>('');
  const [status, setStatus] = useState<string>('');
  const [priority, setPriority] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);

  const loadMapData = () => {
    setLoading(true);
    adminService.getMapComplaints({
      category: category || undefined,
      status: status || undefined,
      priority: priority || undefined,
    })
      .then((res) => setComplaints(res.complaints))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadMapData();
  }, [category, status, priority]);

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Spatial Intelligence</span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Live Municipal Issue Map</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Geospatial visualization of civic complaints across wards. Markers styled by priority SLA.
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

      {/* Filter Toolbar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <Filter className="w-4 h-4 text-slate-400" />
            <span className="font-semibold">Filters:</span>
          </div>

          <select
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
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="px-3 py-1.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-700"
          >
            <option value="">All Statuses</option>
            <option value="SUBMITTED">Submitted</option>
            <option value="UNDER_REVIEW">Under Review</option>
            <option value="IN_PROGRESS">In Progress</option>
            <option value="AWAITING_CITIZEN_CONFIRMATION">Awaiting Confirmation</option>
            <option value="RESOLVED">Resolved</option>
          </select>
        </div>

        <button
          onClick={loadMapData}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 border border-slate-200 hover:bg-slate-100 rounded-xl text-xs font-semibold text-slate-700 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh Map ({complaints.length} Pins)
        </button>
      </div>

      {/* Map Container */}
      <div className="bg-white p-3 rounded-3xl border border-slate-200 shadow-xs">
        <MapViewer
          complaints={complaints}
          height="620px"
          onSelectComplaint={(id) => (window.location.href = `/admin/complaints/${id}`)}
        />
      </div>
    </div>
  );
};

