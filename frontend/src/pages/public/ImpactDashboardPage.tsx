import React, { useEffect, useState } from 'react';
import { 
  BarChart3, CheckCircle2, Clock, AlertTriangle, 
  TrendingUp, Activity, Award, ShieldCheck, RefreshCw 
} from 'lucide-react';
import { publicService } from '../../services/publicService';
import { PublicImpactData } from '../../types';

export const ImpactDashboardPage: React.FC = () => {
  const [data, setData] = useState<PublicImpactData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchMetrics = () => {
    setLoading(true);
    publicService.getImpactDashboard()
      .then(setData)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchMetrics();
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-10">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold mb-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Public Transparency Feed
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Public Impact Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time aggregate municipal performance statistics directly computed from database operational records.
          </p>
        </div>
        <button
          onClick={fetchMetrics}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-300 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-xs transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh Metrics
        </button>
      </div>

      {/* Aggregate KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Reports</span>
            <Activity className="w-5 h-5 text-brand-600" />
          </div>
          <p className="text-3xl font-extrabold text-slate-900">
            {data ? data.total_complaints_reported : 0}
          </p>
          <span className="text-xs text-slate-500 mt-1 block">Civic complaints recorded</span>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Citizen Verified</span>
            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
          </div>
          <p className="text-3xl font-extrabold text-emerald-600">
            {data ? data.complaints_resolved : 0}
          </p>
          <span className="text-xs text-slate-500 mt-1 block">Satisfactorily repaired & confirmed</span>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Resolution Rate</span>
            <TrendingUp className="w-5 h-5 text-brand-600" />
          </div>
          <p className="text-3xl font-extrabold text-slate-900">
            {data ? `${data.resolution_success_rate}%` : '0%'}
          </p>
          <span className="text-xs text-slate-500 mt-1 block">Approval without dispute</span>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Avg SLA Closure</span>
            <Clock className="w-5 h-5 text-ai-600" />
          </div>
          <p className="text-3xl font-extrabold text-slate-900">
            {data ? `${data.average_resolution_hours}h` : '0h'}
          </p>
          <span className="text-xs text-slate-500 mt-1 block">Submission to verified repair</span>
        </div>
      </div>

      {/* Top Reported Categories Breakdown */}
      <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-xs space-y-6">
        <div>
          <h3 className="text-lg font-bold text-slate-900">Top Civic Categories Reported</h3>
          <p className="text-xs text-slate-500">Breakdown of reported issues prioritized for municipal budget allocation.</p>
        </div>

        <div className="space-y-4">
          {data?.top_categories && data.top_categories.length > 0 ? (
            data.top_categories.map((cat, idx) => {
              const maxCount = Math.max(...data.top_categories.map((c) => c.count), 1);
              const percentage = Math.round((cat.count / (data.total_complaints_reported || 1)) * 100);
              return (
                <div key={idx} className="space-y-1.5">
                  <div className="flex justify-between text-xs font-semibold text-slate-800">
                    <span>{cat.category}</span>
                    <span className="font-mono text-slate-500">{cat.count} reports ({percentage}%)</span>
                  </div>
                  <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-600 rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, (cat.count / maxCount) * 100)}%` }}
                    />
                  </div>
                </div>
              );
            })
          ) : (
            <p className="text-xs text-slate-400 py-4">No aggregate data accumulated yet.</p>
          )}
        </div>
      </div>

      {/* Privacy Notice */}
      <div className="p-4 bg-slate-100 rounded-2xl text-xs text-slate-500 leading-relaxed border border-slate-200">
        <strong>Privacy Assurance:</strong> Public statistics are aggregated on an anonymized basis without revealing private names, residential addresses, contact numbers, or uploaded citizen photographs.
      </div>
    </div>
  );
};

