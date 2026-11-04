import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, Heart, AlertOctagon, ExternalLink } from 'lucide-react';

export const Footer: React.FC = () => {
  return (
    <footer className="bg-slate-900 text-slate-400 border-t border-slate-800 mt-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-10">
          {/* Brand & mission */}
          <div className="md:col-span-1 space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-brand-600 text-white flex items-center justify-center">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <span className="text-lg font-bold text-white tracking-tight">CivicFix AI</span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              "Report. Resolve. Rebuild Trust."
              <br />
              Bridging citizens and local municipal administration through transparent AI triage, accountable field crew dispatch, and citizen-verified resolutions.
            </p>
          </div>

          {/* Citizen services */}
          <div>
            <h4 className="text-xs font-semibold text-white uppercase tracking-wider mb-3">Citizens</h4>
            <ul className="space-y-2 text-xs">
              <li>
                <Link to="/citizen/report" className="hover:text-white transition">Report a Civic Hazard</Link>
              </li>
              <li>
                <Link to="/citizen/complaints" className="hover:text-white transition">Track My Complaint</Link>
              </li>
              <li>
                <Link to="/impact" className="hover:text-white transition">Public Impact Metrics</Link>
              </li>
              <li>
                <Link to="/categories" className="hover:text-white transition">Civic Issue Directory</Link>
              </li>
            </ul>
          </div>

          {/* Municipal Staff */}
          <div>
            <h4 className="text-xs font-semibold text-white uppercase tracking-wider mb-3">Administration</h4>
            <ul className="space-y-2 text-xs">
              <li>
                <Link to="/staff/login" className="hover:text-white transition">Municipal Staff Portal</Link>
              </li>
              <li>
                <Link to="/how-it-works" className="hover:text-white transition">AI Prioritization Policy</Link>
              </li>
              <li>
                <Link to="/accessibility" className="hover:text-white transition">WCAG 2.2 AA Compliance</Link>
              </li>
              <li>
                <Link to="/contact" className="hover:text-white transition">Municipal Grievance Cell</Link>
              </li>
            </ul>
          </div>

          {/* Legal & Trust */}
          <div>
            <h4 className="text-xs font-semibold text-white uppercase tracking-wider mb-3">Legal & Privacy</h4>
            <ul className="space-y-2 text-xs">
              <li>
                <Link to="/privacy" className="hover:text-white transition">Citizen Privacy Policy</Link>
              </li>
              <li>
                <Link to="/terms" className="hover:text-white transition">Terms of Service</Link>
              </li>
              <li>
                <Link to="/accessibility" className="hover:text-white transition">Accessibility Statement</Link>
              </li>
              <li className="pt-2 text-[11px] text-slate-500">
                Single-Admin Invariant Enforced
              </li>
            </ul>
          </div>
        </div>

        {/* Emergency disclaimer banner */}
        <div className="p-3.5 bg-slate-800/80 rounded-xl border border-slate-700/80 text-xs text-slate-300 flex items-start sm:items-center gap-3 mb-8">
          <AlertOctagon className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5 sm:mt-0" />
          <p>
            <strong>EMERGENCY SERVICES NOTICE:</strong> CivicFix AI is designed for municipal non-emergency civil complaints and routine infrastructure remediation. If there is an active fire, medical crisis, or imminent life-threatening emergency, please dial <strong>112</strong> immediately.
          </p>
        </div>

        <div className="pt-6 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-4">
          <p>&copy; {new Date().getFullYear()} CivicFix AI Platform. All rights reserved. Built for Municipal Accountability.</p>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              Made with <Heart className="w-3 h-3 text-rose-500 fill-rose-500" /> for civic empowerment
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
};

