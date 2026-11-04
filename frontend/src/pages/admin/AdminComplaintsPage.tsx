import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Search, Filter, RefreshCw, ChevronLeft, ChevronRight, Eye, MapPin } from 'lucide-react';
import { adminService } from '../../services/adminService';
import { Complaint, Department } from '../../types';
import { StatusBadge, PriorityBadge } from '../../components/common/Badge';

export const AdminComplaintsPage: React.FC = () => {
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);

  const [searchParams, setSearchParams] = useSearchParams();
  const categoryFilter = searchParams.get('category') || '';
  const statusFilter = searchParams.get('status') || '';
  const priorityFilter = searchParams.get('priority') || '';
  const departmentFilter = searchParams.get('department_id') || '';
  const [searchInput, setSearchInput] = useState<string>('');

  const loadData = () => {
    setLoading(true);
    adminService.listComplaints({
      page,
      page_size: 15,
      category: categoryFilter || undefined,
      status: statusFilter || undefined,
      priority: priorityFilter || undefined,
      department_id: departmentFilter || undefined,
      search: searchInput || undefined,
    })
      .then((res) => {
        setComplaints(res.complaints);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    adminService.getDepartments().then(setDepartments).catch(() => {});
  }, []);

  useEffect(() => {
    loadData();
  }, [page, categoryFilter, statusFilter, priorityFilter, departmentFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    loadData();
  };

  const handleFilterChange = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setPage(1);
    setSearchParams(next);
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Municipal Complaints Register</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Manage, triage, and route civic defect submissions across all municipal jurisdictions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 bg-white border border-slate-300 rounded-xl text-slate-600 hover:bg-slate-50 transition"
            title="Refresh Table"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <a
            href={adminService.getExportCsvUrl()}
            target="_blank"
            rel="noreferrer"
            className="px-3 py-2 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-semibold shadow-xs transition"
          >
            Export CSV
          </a>
        </div>
      </div>

      {/* Filters & Search Toolbar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs space-y-3">
        <form onSubmit={handleSearchSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search by reference #, title, description, or street..."
              className="w-full px-3.5 py-2 pl-9 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500 focus:outline-none"
            />
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          </div>
          <button
            type="submit"
            className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-xs font-semibold shadow-xs transition"
          >
            Search
          </button>
        </form>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 border-t border-slate-100">
          <select
            value={categoryFilter}
            onChange={(e) => handleFilterChange('category', e.target.value)}
            className="px-2.5 py-1.5 border border-slate-300 rounded-lg text-xs bg-white text-slate-700"
          >
            <option value="">All Categories</option>
            <option value="ROADS">Roads & Potholes</option>
            <option value="STREETLIGHTS">Street Lighting</option>
            <option value="GARBAGE">Garbage & Waste</option>
            <option value="DRAINAGE">Drainage & Flooding</option>
            <option value="WATER_SUPPLY">Water Supply</option>
            <option value="FOOTPATHS">Footpaths</option>
            <option value="TREES_HAZARDS">Trees & Hazards</option>
            <option value="SANITATION">Sanitation</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => handleFilterChange('status', e.target.value)}
            className="px-2.5 py-1.5 border border-slate-300 rounded-lg text-xs bg-white text-slate-700"
          >
            <option value="">All Statuses</option>
            <option value="SUBMITTED">Submitted</option>
            <option value="UNDER_REVIEW">Under Review</option>
            <option value="ASSIGNED">Assigned</option>
            <option value="IN_PROGRESS">In Progress</option>
            <option value="AWAITING_CITIZEN_CONFIRMATION">Awaiting Confirmation</option>
            <option value="RESOLVED">Resolved</option>
            <option value="REOPENED">Reopened</option>
          </select>

          <select
            value={priorityFilter}
            onChange={(e) => handleFilterChange('priority', e.target.value)}
            className="px-2.5 py-1.5 border border-slate-300 rounded-lg text-xs bg-white text-slate-700"
          >
            <option value="">All Priorities</option>
            <option value="P1">P1 Critical</option>
            <option value="P2">P2 High</option>
            <option value="P3">P3 Normal</option>
            <option value="P4">P4 Low</option>
          </select>

          <select
            value={departmentFilter}
            onChange={(e) => handleFilterChange('department_id', e.target.value)}
            className="px-2.5 py-1.5 border border-slate-300 rounded-lg text-xs bg-white text-slate-700"
          >
            <option value="">All Departments</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Complaints Table */}
      <div className="bg-white rounded-3xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold">
              <tr>
                <th className="px-5 py-3">Reference & Title</th>
                <th className="px-5 py-3">Category</th>
                <th className="px-5 py-3">Priority</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Department</th>
                <th className="px-5 py-3">Date</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-slate-400">
                    Loading records from municipal registry...
                  </td>
                </tr>
              ) : complaints.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-slate-400">
                    No complaints found matching the criteria.
                  </td>
                </tr>
              ) : (
                complaints.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-5 py-3.5 max-w-xs">
                      <span className="font-mono font-bold text-brand-700 block text-[11px]">
                        #{c.reference_number}
                      </span>
                      <span className="font-semibold text-slate-900 block truncate" title={c.title}>
                        {c.title}
                      </span>
                      {c.address && (
                        <span className="text-[10px] text-slate-400 truncate block">
                          {c.address}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                        {c.category}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <PriorityBadge priority={c.priority} />
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 font-medium">
                      {c.department_name || 'Unassigned'}
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 text-[11px] font-mono">
                      {new Date(c.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <Link
                        to={`/admin/complaints/${c.id}`}
                        className="inline-flex items-center gap-1 px-3 py-1.5 bg-brand-50 hover:bg-brand-100 text-brand-700 rounded-lg text-xs font-semibold transition"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Inspect</span>
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="px-5 py-3.5 border-t border-slate-200 bg-slate-50/50 flex items-center justify-between text-xs text-slate-500">
          <span>
            Showing {complaints.length > 0 ? (page - 1) * 15 + 1 : 0} to{' '}
            {Math.min(page * 15, total)} of {total} records
          </span>
          <div className="flex items-center gap-1">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="p-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-2 font-mono font-semibold">{page}</span>
            <button
              disabled={page * 15 >= total}
              onClick={() => setPage((p) => p + 1)}
              className="p-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

