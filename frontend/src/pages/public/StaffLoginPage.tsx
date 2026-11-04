import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShieldCheck, Mail, Lock, AlertCircle, Building2, Wrench, ShieldAlert } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { authService } from '../../services/authService';
import { Button } from '../../components/common/Button';

export const StaffLoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const resp = await authService.login({ email, password });

      // Check role permissions: must not be CITIZEN
      if (resp.role === 'CITIZEN') {
        setError('Access Denied: Citizen accounts cannot enter the Municipal Staff Portal. Please use the Citizen Login.');
        setLoading(false);
        return;
      }

      login(resp.access_token, {
        id: resp.user_id,
        email: resp.email,
        full_name: resp.full_name,
        role: resp.role,
        is_active: true,
        is_verified: true,
        created_at: new Date().toISOString()
      }, resp.refresh_token);

      navigate('/admin');
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickDemo = (demoEmail: string, demoPass: string) => {
    setEmail(demoEmail);
    setPassword(demoPass);
  };

  return (
    <div className="min-h-[85vh] flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center space-y-2">
        <div className="w-12 h-12 rounded-2xl bg-slate-900 text-white flex items-center justify-center mx-auto shadow-md">
          <Building2 className="w-6 h-6 text-ai-400" />
        </div>
        <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">Municipal Command Portal</h2>
        <p className="text-xs text-slate-500">
          Authorized Municipal Staff, Field Crews & Government Administration Only.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-6 shadow-sm border border-slate-200 rounded-2xl sm:px-8 space-y-6">
          {error && (
            <div className="flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Official Staff Email
              </label>
              <div className="relative">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="officer@civicfix.gov"
                  className="w-full px-3.5 py-2.5 pl-10 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition"
                />
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Security Password
              </label>
              <div className="relative">
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-3.5 py-2.5 pl-10 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition"
                />
                <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
              </div>
            </div>

            <Button
              type="submit"
              variant="secondary"
              size="md"
              isLoading={loading}
              className="w-full justify-center bg-slate-900 hover:bg-slate-950"
            >
              Sign In to Command Portal
            </Button>
          </form>

          {/* Quick Staff Demo Fill */}
          <div className="pt-4 border-t border-slate-100 space-y-2">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block text-center">
              Municipal Roles Demo Login
            </span>
            <div className="grid grid-cols-1 gap-2">
              <button
                type="button"
                onClick={() => handleQuickDemo('admin@civicfix.gov', 'AdminSecure2026!')}
                className="p-2.5 border border-slate-200 hover:border-ai-400 rounded-xl bg-slate-50 hover:bg-ai-50/50 text-left text-xs transition flex items-center justify-between"
              >
                <div>
                  <div className="font-semibold text-slate-800">1. Government Admin (Highest Privilege)</div>
                  <div className="text-[10px] text-slate-500">Full municipal control • Single Admin Invariant</div>
                </div>
                <ShieldAlert className="w-4 h-4 text-ai-600" />
              </button>

              <button
                type="button"
                onClick={() => handleQuickDemo('officer.sharma@civicfix.gov', 'StaffSecure2026!')}
                className="p-2.5 border border-slate-200 hover:border-brand-400 rounded-xl bg-slate-50 hover:bg-brand-50/50 text-left text-xs transition flex items-center justify-between"
              >
                <div>
                  <div className="font-semibold text-slate-800">2. Municipal Member (Roads Officer)</div>
                  <div className="text-[10px] text-slate-500">Triage review • Dispatch work orders</div>
                </div>
                <Building2 className="w-4 h-4 text-brand-600" />
              </button>

              <button
                type="button"
                onClick={() => handleQuickDemo('crew.patel@civicfix.gov', 'CrewSecure2026!')}
                className="p-2.5 border border-slate-200 hover:border-amber-400 rounded-xl bg-slate-50 hover:bg-amber-50/50 text-left text-xs transition flex items-center justify-between"
              >
                <div>
                  <div className="font-semibold text-slate-800">3. Field Crew (Rapid Road Crew)</div>
                  <div className="text-[10px] text-slate-500">Execute repairs • Upload after-evidence</div>
                </div>
                <Wrench className="w-4 h-4 text-amber-600" />
              </button>
            </div>
          </div>

          <div className="text-center pt-2">
            <Link to="/login" className="text-xs text-brand-600 hover:text-brand-700 font-semibold">
              &larr; Return to Citizen Portal Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

