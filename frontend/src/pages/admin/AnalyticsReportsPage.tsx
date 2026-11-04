import React, { useEffect, useState } from 'react';
import { 
  BarChart3, Download, TrendingUp, CheckCircle2, Clock, 
  AlertTriangle, ShieldCheck, Activity 
} from 'lucide-react';
import { adminService } from '../../services/adminService';
import { AnalyticsOverview } from '../../types';
import { Button } from '../../components/common/Button';

export const AnalyticsReportsPage: React.FC = () => {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    adminService.getDashboardMetrics()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="p-12 text-center text-xs text-slate-400">Loading municipal operational analytics...</div>;
  }

  const m = data?.metrics;

  return (
    <div className="space-y-8">
      {/* Header & Export */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Executive Reporting</span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Municipal Analytics & Auditing</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Real database metrics calculated to evaluate department responsiveness and SLA adherence.
          </p>
        </div>

        <a
          href={adminService.getExportCsvUrl()}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-xs font-semibold shadow-xs transition"
        >
          <Download className="w-4 h-4" />
          <span>Export Complete CSV Report</span>
        </a>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <span className="text-xs font-semibold text-slate-400 uppercase">Gross Complaints</span>
          <p className="text-3xl font-extrabold text-slate-900 mt-1">{m?.total_complaints || 0}</p>
          <span className="text-[11px] text-slate-500 mt-1 block">Registered in database</span>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <span className="text-xs font-semibold text-slate-400 uppercase">Verified Resolved</span>
          <p className="text-3xl font-extrabold text-emerald-600 mt-1">{m?.resolved_complaints || 0}</p>
          <span className="text-[11px] text-emerald-600 mt-1 block">Citizen confirmed</span>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <span className="text-xs font-semibold text-slate-400 uppercase">Average Fix Time</span>
          <p className="text-3xl font-extrabold text-slate-900 mt-1">{m?.average_resolution_hours}h</p>
          <span className="text-[11px] text-brand-600 mt-1 block">Submission to verified repair</span>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
          <span className="text-xs font-semibold text-slate-400 uppercase">Citizen Satisfaction</span>
          <p className="text-3xl font-extrabold text-emerald-600 mt-1">{m?.citizen_satisfaction_rate}%</p>
          <span className="text-[11px] text-emerald-600 mt-1 block">Satisfactory sign-offs</span>
        </div>
      </div>

      {/* Breakdown Grids */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Department Volume and Clearance */}
        <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
            Departmental Clearance Metrics
          </h3>
          <div className="space-y-3">
            {data?.by_department.map((dept, idx) => (
              <div key={idx} className="p-3 bg-slate-50 rounded-2xl border border-slate-100 flex items-center justify-between text-xs">
                <div>
                  <div className="font-bold text-slate-900">{dept.department_name}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    Clearance Rate: {dept.count > 0 ? Math.round((dept.resolved_count / (dept.count + dept.resolved_count)) * 100) : 100}%
                  </div>
                </div>
                <div className="text-right">
                  <span className="font-bold font-mono text-slate-800">{dept.count} open</span>
                  <span className="text-[10px] text-emerald-600 block">{dept.resolved_count} resolved</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Priority Escalation Breakdown */}
        <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
            Priority SLA Distribution
          </h3>
          <div className="space-y-4">
            {data?.by_priority.map((p, idx) => (
              <div key={idx} className="space-y-1">
                <div className="flex justify-between text-xs font-semibold">
                  <span>{p.priority} • {p.priority === 'P1' ? 'Critical (12h)' : p.priority === 'P2' ? 'High (24h)' : p.priority === 'P3' ? 'Normal (72h)' : 'Low (168h)'}</span>
                  <span className="font-mono text-slate-500">{p.count} tickets ({p.percentage}%)</span>
                </div>
                <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
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
      </div>
    </div>
  );
};

