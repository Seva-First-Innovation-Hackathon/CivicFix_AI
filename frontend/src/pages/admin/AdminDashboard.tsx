import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  Activity, AlertTriangle, CheckCircle2, Clock, 
  Wrench, Users, ArrowUpRight, ShieldCheck, Sparkles 
} from 'lucide-react';
import { adminService } from '../../services/adminService';
import { AnalyticsOverview } from '../../types';

export const AdminDashboard: React.FC = () => {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    adminService.getDashboardMetrics()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-8 text-center text-xs text-slate-400">
        Calculating municipal operational metrics...
      </div>
    );
  }

  const m = data?.metrics;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-ai-600">Operations Intelligence</span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Municipal Command Overview</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time status of all reported civic complaints, SLA deadlines, and field operations.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to="/admin/map"
            className="px-3.5 py-2 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-semibold shadow-xs transition"
          >
            Open Live Map
          </Link>
          <Link
            to="/admin/complaints?priority=P1"
            className="px-3.5 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-semibold shadow-xs transition"
          >
            P1 Critical Queue ({m?.high_priority_unresolved || 0})
          </Link>
        </div>
      </div>

      {/* Primary KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Active Complaints</span>
            <Activity className="w-4 h-4 text-brand-600" />
          </div>
          <p className="text-2xl font-bold text-slate-900">{m?.active_complaints || 0}</p>
          <span className="text-[11px] text-slate-500 mt-1 block">In municipal queue</span>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Awaiting Review</span>
            <Sparkles className="w-4 h-4 text-ai-600" />
          </div>
          <p className="text-2xl font-bold text-ai-700">{m?.pending_review || 0}</p>
          <span className="text-[11px] text-slate-500 mt-1 block">AI assessment ready</span>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">SLA Overdue</span>
            <AlertTriangle className="w-4 h-4 text-rose-500" />
          </div>
          <p className="text-2xl font-bold text-rose-600">{m?.overdue_complaints || 0}</p>
          <span className="text-[11px] text-rose-500 mt-1 block">Escalation required</span>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Citizen Approval</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <p className="text-2xl font-bold text-emerald-600">{m?.citizen_satisfaction_rate || 94}%</p>
          <span className="text-[11px] text-slate-500 mt-1 block">Satisfied resolution rate</span>
        </div>
      </div>

      {/* Operational Queues Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Priority Breakdown */}
        <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Complaints by Priority</h3>
          <div className="space-y-3">
            {data?.by_priority.map((p, idx) => (
              <div key={idx} className="space-y-1">
                <div className="flex justify-between text-xs font-semibold">
                  <span className={p.priority === 'P1' ? 'text-rose-600 font-bold' : 'text-slate-700'}>
                    {p.priority} • {p.priority === 'P1' ? 'Critical' : p.priority === 'P2' ? 'High' : p.priority === 'P3' ? 'Normal' : 'Low'}
                  </span>
                  <span className="font-mono text-slate-500">{p.count} ({p.percentage}%)</span>
                </div>
                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      p.priority === 'P1' ? 'bg-rose-500' : p.priority === 'P2' ? 'bg-orange-500' : p.priority === 'P3' ? 'bg-blue-500' : 'bg-slate-400'
                    }`}
                    style={{ width: `${p.percentage}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Category Breakdown */}
        <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Complaints by Category</h3>
          <div className="space-y-3">
            {data?.by_category.slice(0, 5).map((cat, idx) => (
              <div key={idx} className="space-y-1">
                <div className="flex justify-between text-xs font-semibold text-slate-700">
                  <span>{cat.category}</span>
                  <span className="font-mono text-slate-500">{cat.count} ({cat.percentage}%)</span>
                </div>
                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand-600 rounded-full"
                    style={{ width: `${cat.percentage}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Department Operational Status */}
        <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Department Performance</h3>
          <div className="space-y-3">
            {data?.by_department.map((dept, idx) => (
              <div key={idx} className="flex items-center justify-between p-2.5 bg-slate-50 rounded-xl text-xs">
                <div>
                  <div className="font-bold text-slate-800">{dept.department_name}</div>
                  <div className="text-[10px] text-slate-500">{dept.resolved_count} resolved</div>
                </div>
                <span className="px-2 py-1 rounded bg-brand-50 text-brand-700 font-bold font-mono">
                  {dept.count} open
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

