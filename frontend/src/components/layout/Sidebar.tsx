import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, FileText, Map, Sparkles, Wrench, 
  Truck, Building2, Copy, BarChart3, ShieldCheck, 
  Users, Settings, ShieldAlert 
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export const Sidebar: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'GOVERNMENT_ADMIN';
  const isCrew = user?.role === 'FIELD_CREW';

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all ${
      isActive
        ? 'bg-brand-600 text-white shadow-sm shadow-brand-500/20'
        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
    }`;

  return (
    <aside className="w-64 bg-white border-r border-slate-200 min-h-[calc(100vh-64px)] p-4 flex flex-col justify-between">
      <div className="space-y-6">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-3">
            Operations Center
          </span>
          <nav className="mt-2 space-y-1">
            <NavLink to="/admin" end className={navLinkClass}>
              <LayoutDashboard className="w-4 h-4" />
              Overview Dashboard
            </NavLink>
            <NavLink to="/admin/complaints" className={navLinkClass}>
              <FileText className="w-4 h-4" />
              All Complaints
            </NavLink>
            <NavLink to="/admin/map" className={navLinkClass}>
              <Map className="w-4 h-4" />
              Live Issue Map
            </NavLink>
            <NavLink to="/admin/work-orders" className={navLinkClass}>
              <Wrench className="w-4 h-4" />
              Work Orders & Dispatch
            </NavLink>
            {isCrew && (
              <NavLink to="/admin/crew-tasks" className={navLinkClass}>
                <Truck className="w-4 h-4" />
                My Field Orders
              </NavLink>
            )}
          </nav>
        </div>

        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-3">
            Intelligence & Quality
          </span>
          <nav className="mt-2 space-y-1">
            <NavLink to="/admin/duplicates" className={navLinkClass}>
              <Copy className="w-4 h-4" />
              Flagged Duplicates
            </NavLink>
            <NavLink to="/admin/analytics" className={navLinkClass}>
              <BarChart3 className="w-4 h-4" />
              Analytics & Reports
            </NavLink>
          </nav>
        </div>

        {isAdmin && (
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-3">
              Administration (Gov Admin)
            </span>
            <nav className="mt-2 space-y-1">
              <NavLink to="/admin/departments" className={navLinkClass}>
                <Building2 className="w-4 h-4" />
                Departments
              </NavLink>
              <NavLink to="/admin/users" className={navLinkClass}>
                <Users className="w-4 h-4" />
                Staff & Field Crews
              </NavLink>
              <NavLink to="/admin/audit-logs" className={navLinkClass}>
                <ShieldAlert className="w-4 h-4" />
                Audit Logs
              </NavLink>
            </nav>
          </div>
        )}
      </div>

      <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl mt-6">
        <div className="flex items-center gap-2 mb-1">
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          <span className="text-xs font-bold text-slate-800">
            {isAdmin ? 'Gov Admin Seat' : 'Authorized Staff'}
          </span>
        </div>
        <p className="text-[11px] text-slate-500 leading-tight">
          {user?.email}
        </p>
      </div>
    </aside>
  );
};

