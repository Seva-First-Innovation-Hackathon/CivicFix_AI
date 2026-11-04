import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  PlusCircle, FileText, CheckCircle2, Clock, AlertTriangle, 
  MapPin, ArrowRight, ShieldCheck, ChevronRight 
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { complaintsService } from '../../services/complaintsService';
import { Complaint } from '../../types';
import { StatusBadge, PriorityBadge } from '../../components/common/Badge';
import { MapViewer } from '../../components/common/MapViewer';

export const CitizenDashboard: React.FC = () => {
  const { user } = useAuth();
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    complaintsService.getMyComplaints({ page: 1, page_size: 50 })
      .then((res) => setComplaints(res.complaints))
      .finally(() => setLoading(false));
  }, []);

  const total = complaints.length;
  const active = complaints.filter((c) => !['RESOLVED', 'CANCELLED'].includes(c.status)).length;
  const awaitingVerification = complaints.filter((c) => c.status === 'AWAITING_CITIZEN_CONFIRMATION').length;
  const resolved = complaints.filter((c) => c.status === 'RESOLVED').length;

  const mapItems = complaints.map((c) => ({
    id: c.id,
    reference_number: c.reference_number,
    title: c.title,
    category: c.category,
    status: c.status,
    priority: c.priority,
    latitude: c.latitude,
    longitude: c.longitude,
    address: c.address,
    first_image: c.attachments?.[0]?.file_path,
  }));

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Welcome header & CTA */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-6 rounded-3xl border border-slate-200 shadow-xs">
        <div>
          <span className="text-xs font-bold text-brand-600 uppercase tracking-wider">Citizen Portal</span>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            Hello, {user?.full_name}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Track your reports, inspect repair evidence, and verify municipal resolutions.
          </p>
        </div>
        <Link
          to="/citizen/report"
          className="inline-flex items-center gap-2 px-5 py-3 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-sm font-semibold shadow-sm transition active:scale-[0.98] self-start sm:self-auto"
        >
          <PlusCircle className="w-4 h-4" />
          <span>Report New Issue</span>
        </Link>
      </div>

      {/* Prominent Action Alert if complaints are awaiting citizen confirmation */}
      {awaitingVerification > 0 && (
        <div className="bg-gradient-to-r from-emerald-50 to-teal-50 border border-emerald-200 p-5 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-xs">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-600 text-white flex items-center justify-center flex-shrink-0">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-emerald-950">
                Action Required: {awaitingVerification} Repair{awaitingVerification > 1 ? 's' : ''} Awaiting Your Sign-Off
              </h4>
              <p className="text-xs text-emerald-800">
                Field crew has completed the work. Please inspect the after-repair evidence to confirm or contest the fix.
              </p>
            </div>
          </div>
          <Link
            to="/citizen/complaints?status=AWAITING_CITIZEN_CONFIRMATION"
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold shadow-xs transition"
          >
            Review Repairs &rarr;
          </Link>
        </div>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Submitted</span>
            <FileText className="w-4 h-4 text-slate-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900">{total}</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Under Remediation</span>
            <Clock className="w-4 h-4 text-amber-500" />
          </div>
          <p className="text-2xl font-bold text-amber-600">{active}</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Awaiting Sign-off</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <p className="text-2xl font-bold text-emerald-600">{awaitingVerification}</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Confirmed Closed</span>
            <ShieldCheck className="w-4 h-4 text-brand-600" />
          </div>
          <p className="text-2xl font-bold text-slate-900">{resolved}</p>
        </div>
      </div>

      {/* Main Content Grid: Recent Complaints + Personal Map */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left: Complaints List */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-slate-900">My Recent Reports</h3>
            <Link to="/citizen/complaints" className="text-xs font-semibold text-brand-600 hover:text-brand-700">
              View All ({total}) &rarr;
            </Link>
          </div>

          {loading ? (
            <div className="bg-white p-8 rounded-2xl border border-slate-200 text-center text-xs text-slate-400">
              Loading your complaints...
            </div>
          ) : complaints.length === 0 ? (
            <div className="bg-white p-12 rounded-3xl border border-slate-200 text-center space-y-3">
              <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
                <FileText className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-bold text-slate-800">No Complaints Lodged Yet</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Notice a pothole, broken streetlight, or garbage overflow in your ward? Submit a report with photographic evidence.
              </p>
              <Link
                to="/citizen/report"
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand-600 text-white rounded-xl text-xs font-semibold shadow-xs"
              >
                + Report Your First Issue
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {complaints.slice(0, 5).map((complaint) => (
                <Link
                  key={complaint.id}
                  to={`/citizen/complaints/${complaint.id}`}
                  className="block bg-white p-5 rounded-2xl border border-slate-200 hover:border-brand-300 shadow-xs hover:shadow-sm transition"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-brand-700">
                          #{complaint.reference_number}
                        </span>
                        <StatusBadge status={complaint.status} />
                        <PriorityBadge priority={complaint.priority} />
                      </div>
                      <h4 className="text-sm font-bold text-slate-900 line-clamp-1">{complaint.title}</h4>
                      <p className="text-xs text-slate-500 line-clamp-1">{complaint.description}</p>
                      {complaint.address && (
                        <div className="flex items-center gap-1 text-[11px] text-slate-400 pt-1">
                          <MapPin className="w-3 h-3 text-slate-400 flex-shrink-0" />
                          <span className="truncate">{complaint.address}</span>
                        </div>
                      )}
                    </div>
                    <ChevronRight className="w-5 h-5 text-slate-300 flex-shrink-0 mt-2" />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Right: Personal Interactive Map */}
        <div className="space-y-4">
          <h3 className="text-base font-bold text-slate-900">My Issue Locations</h3>
          <div className="bg-white p-3 rounded-3xl border border-slate-200 shadow-xs">
            <MapViewer
              complaints={mapItems}
              height="380px"
              onSelectComplaint={(id) => (window.location.href = `/citizen/complaints/${id}`)}
            />
            <p className="text-[11px] text-slate-500 text-center mt-2">
              Pins show your reported hazards. Click a marker to inspect details.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

