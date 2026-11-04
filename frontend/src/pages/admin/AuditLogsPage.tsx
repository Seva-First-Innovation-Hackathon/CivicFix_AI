import React, { useEffect, useState } from 'react';
import { ShieldAlert, RefreshCw, Clock, User, FileText, CheckCircle2 } from 'lucide-react';
import { adminService } from '../../services/adminService';

export const AuditLogsPage: React.FC = () => {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const loadLogs = () => {
    setLoading(true);
    adminService.getAuditLogs()
      .then(setLogs)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadLogs();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-rose-600">Regulatory Compliance</span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">System Audit Trail</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Immutable log of state changes, account provisioning, and administrative decisions.
          </p>
        </div>
        <button
          onClick={loadLogs}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-xs transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh Log
        </button>
      </div>

      <div className="bg-white rounded-3xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold">
              <tr>
                <th className="px-5 py-3">Timestamp</th>
                <th className="px-5 py-3">Action Event</th>
                <th className="px-5 py-3">Entity Type & ID</th>
                <th className="px-5 py-3">User Reference</th>
                <th className="px-5 py-3">Details / Audit Payload</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-5 py-12 text-center text-slate-400">
                    Loading audit trail...
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-12 text-center text-slate-400">
                    No audit records accumulated yet.
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-5 py-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3">
                      <span className="font-semibold text-slate-900 bg-slate-100 px-2 py-0.5 rounded text-[11px]">
                        {log.action}
                      </span>
                    </td>
                    <td className="px-5 py-3 font-mono text-slate-600">
                      {log.entity_type} <span className="text-slate-400">({log.entity_id?.slice(0, 8)}...)</span>
                    </td>
                    <td className="px-5 py-3 font-mono text-slate-600">
                      {log.user_id ? `${log.user_id.slice(0, 8)}...` : 'System Automatic'}
                    </td>
                    <td className="px-5 py-3 text-slate-500 font-mono text-[11px] max-w-sm truncate" title={log.details}>
                      {log.details || '—'}
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

