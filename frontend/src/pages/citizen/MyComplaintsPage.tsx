import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Search, Filter, PlusCircle, MapPin, ChevronRight, FileText } from 'lucide-react';
import { complaintsService } from '../../services/complaintsService';
import { Complaint } from '../../types';
import { StatusBadge, PriorityBadge } from '../../components/common/Badge';

export const MyComplaintsPage: React.FC = () => {
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchTerm, setSearchTerm] = useState('');
  
  const statusFilter = searchParams.get('status') || '';

  useEffect(() => {
    setLoading(true);
    complaintsService.getMyComplaints({
      page: 1,
      page_size: 50,
      status_filter: statusFilter || undefined,
    })
      .then((res) => setComplaints(res.complaints))
      .finally(() => setLoading(false));
  }, [statusFilter]);

  const filtered = complaints.filter((c) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      c.title.toLowerCase().includes(term) ||
      c.reference_number.toLowerCase().includes(term) ||
      (c.address && c.address.toLowerCase().includes(term))
    );
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">My Complaint History</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            View status, operational updates, and verify completed repairs for your reports.
          </p>
        </div>
        <Link
          to="/citizen/report"
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-xs font-semibold shadow-xs transition self-start sm:self-auto"
        >
          <PlusCircle className="w-4 h-4" />
          <span>New Report</span>
        </Link>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="relative w-full sm:w-96">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by reference, title, or street..."
            className="w-full px-3.5 py-2 pl-9 border border-slate-300 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Filter className="w-4 h-4 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => setSearchParams(e.target.value ? { status: e.target.value } : {})}
            className="w-full sm:w-auto px-3 py-2 border border-slate-300 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
          >
            <option value="">All Statuses</option>
            <option value="SUBMITTED">Submitted</option>
            <option value="UNDER_REVIEW">Under Review</option>
            <option value="IN_PROGRESS">In Progress</option>
            <option value="AWAITING_CITIZEN_CONFIRMATION">Awaiting Confirmation</option>
            <option value="RESOLVED">Resolved</option>
            <option value="REOPENED">Reopened</option>
          </select>
        </div>
      </div>

      {/* Complaints List */}
      {loading ? (
        <div className="bg-white p-12 rounded-3xl border border-slate-200 text-center text-xs text-slate-400">
          Loading your complaints...
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white p-12 rounded-3xl border border-slate-200 text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <FileText className="w-6 h-6" />
          </div>
          <h4 className="text-sm font-bold text-slate-800">No Complaints Match Your Criteria</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Try adjusting your search query or status filter.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {filtered.map((complaint) => (
            <Link
              key={complaint.id}
              to={`/citizen/complaints/${complaint.id}`}
              className="bg-white p-5 rounded-2xl border border-slate-200 hover:border-brand-300 shadow-xs hover:shadow-sm transition flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
              <div className="space-y-1.5 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-mono font-bold text-brand-700">
                    #{complaint.reference_number}
                  </span>
                  <StatusBadge status={complaint.status} />
                  <PriorityBadge priority={complaint.priority} />
                  <span className="text-[11px] text-slate-400">
                    {new Date(complaint.created_at).toLocaleDateString()}
                  </span>
                </div>

                <h3 className="text-sm font-bold text-slate-900">{complaint.title}</h3>
                <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">{complaint.description}</p>

                {complaint.address && (
                  <div className="flex items-center gap-1 text-[11px] text-slate-400 pt-1">
                    <MapPin className="w-3 h-3 text-slate-400 flex-shrink-0" />
                    <span>{complaint.address}</span>
                  </div>
                )}
              </div>

              <div className="flex items-center gap-3 self-end sm:self-center flex-shrink-0">
                {complaint.status === 'AWAITING_CITIZEN_CONFIRMATION' && (
                  <span className="px-3 py-1 rounded-lg bg-emerald-600 text-white text-[11px] font-bold animate-pulse">
                    Action: Verify Fix
                  </span>
                )}
                <ChevronRight className="w-5 h-5 text-slate-400" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

