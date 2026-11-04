import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { ShieldCheck, Mail, Lock, ArrowRight, AlertCircle, UserCheck } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { authService } from '../../services/authService';
import { Button } from '../../components/common/Button';

export const CitizenLoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as any)?.from?.pathname || '/citizen';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const resp = await authService.login({ email, password });
      
      // If user is municipal staff attempting to login at citizen portal, redirect them appropriately
      if (resp.role !== 'CITIZEN') {
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

      navigate(from, { replace: true });
    } catch (err: any) {
      setError(err.message || 'Invalid email address or password.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickDemo = (demoEmail: string, demoPass: string) => {
    setEmail(demoEmail);
    setPassword(demoPass);
  };

  return (
    <div className="min-h-[80vh] flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center space-y-2">
        <div className="w-12 h-12 rounded-2xl bg-brand-600 text-white flex items-center justify-center mx-auto shadow-md shadow-brand-500/20">
          <ShieldCheck className="w-7 h-7" />
        </div>
        <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">Citizen Sign In</h2>
        <p className="text-xs text-slate-500">
          Sign in to report civic problems and verify municipal repairs.
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
                Email Address
              </label>
              <div className="relative">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full px-3.5 py-2.5 pl-10 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition"
                />
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                Password
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
              variant="primary"
              size="md"
              isLoading={loading}
              className="w-full justify-center"
            >
              Sign In as Citizen
            </Button>
          </form>

          {/* Quick Demo Credentials */}
          <div className="pt-4 border-t border-slate-100 space-y-2">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block text-center">
              Demonstration Accounts
            </span>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => handleQuickDemo('citizen.arjun@example.com', 'CitizenPass2026!')}
                className="p-2 border border-slate-200 hover:border-brand-300 rounded-xl bg-slate-50 hover:bg-brand-50/50 text-left text-xs transition"
              >
                <div className="font-semibold text-slate-800">Arjun Reddy</div>
                <div className="text-[10px] text-slate-500">Active reports</div>
              </button>
              <button
                type="button"
                onClick={() => handleQuickDemo('citizen.priya@example.com', 'CitizenPass2026!')}
                className="p-2 border border-slate-200 hover:border-brand-300 rounded-xl bg-slate-50 hover:bg-brand-50/50 text-left text-xs transition"
              >
                <div className="font-semibold text-slate-800">Priya Nair</div>
                <div className="text-[10px] text-slate-500">Verified reports</div>
              </button>
            </div>
          </div>

          <div className="text-center pt-2 space-y-2">
            <p className="text-xs text-slate-600">
              Don't have an account?{' '}
              <Link to="/register" className="font-semibold text-brand-600 hover:text-brand-700">
                Register as a Citizen
              </Link>
            </p>
            <p className="text-[11px] text-slate-400">
              Are you municipal staff?{' '}
              <Link to="/staff/login" className="font-semibold text-slate-600 hover:text-slate-800">
                Municipal Staff Login &rarr;
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

