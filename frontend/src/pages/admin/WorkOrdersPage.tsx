import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Wrench, Clock, CheckCircle2, AlertOctagon, User, FileText, ChevronRight } from 'lucide-react';
import { adminService } from '../../services/adminService';
import { WorkOrder } from '../../types';

export const WorkOrdersPage: React.FC = () => {
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    adminService.getWorkOrders()
      .then(setWorkOrders)
      .finally(() => setLoading(false));
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ASSIGNED':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">Assigned</span>;
      case 'IN_PROGRESS':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200 animate-pulse">In Progress</span>;
      case 'BLOCKED':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">Blocked</span>;
      case 'COMPLETED':
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">Completed</span>;
      default:
        return <span>{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Operations Execution</span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Work Orders & Crew Dispatch</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Active field task assignments, scheduled maintenance, and on-site remediation tracking.
          </p>
        </div>
      </div>

      <div className="bg-white rounded-3xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold">
              <tr>
                <th className="px-5 py-3">Work Order & Complaint</th>
                <th className="px-5 py-3">Department</th>
                <th className="px-5 py-3">Assigned Field Crew</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Dispatched Date</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-slate-400">
                    Loading dispatched work orders...
                  </td>
                </tr>
              ) : workOrders.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-slate-400">
                    No work orders dispatched yet.
                  </td>
                </tr>
              ) : (
                workOrders.map((wo) => (
                  <tr key={wo.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-5 py-3.5 max-w-xs">
                      <span className="font-bold text-slate-900 block truncate">{wo.title}</span>
                      <span className="text-[11px] font-mono text-brand-700 block mt-0.5">
                        #{wo.complaint_reference} • {wo.complaint_title}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 font-medium text-slate-700">
                      {wo.department_name || 'General'}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="font-semibold text-slate-900 block">{wo.crew_name || 'Unassigned Crew'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      {getStatusBadge(wo.status)}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-[11px] text-slate-500">
                      {new Date(wo.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <Link
                        to={`/admin/complaints/${wo.complaint_id}`}
                        className="px-3 py-1.5 bg-brand-50 hover:bg-brand-100 text-brand-700 rounded-lg text-xs font-semibold transition"
                      >
                        Inspect Complaint
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

