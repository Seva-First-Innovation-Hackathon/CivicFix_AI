import React from 'react';
import { Eye, CheckCircle2, ShieldCheck } from 'lucide-react';

export const AccessibilityPage: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 space-y-8">
      <div className="space-y-2 border-b border-slate-200 pb-6">
        <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Universal Access</span>
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Accessibility Statement</h1>
        <p className="text-xs text-slate-500">WCAG 2.2 AA Compliance Commitment</p>
      </div>

      <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-xs space-y-6 text-xs text-slate-600 leading-relaxed">
        <p>
          CivicFix AI is committed to ensuring digital accessibility for people with disabilities, seniors, and non-native English speakers across diverse devices and assistive technologies.
        </p>

        <h3 className="text-sm font-bold text-slate-900">Key Standards Implemented</h3>
        <ul className="space-y-2">
          <li className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>High-contrast color palettes exceeding WCAG AA minimum 4.5:1 ratio.</span>
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>Full keyboard navigability for forms, tabs, dialogs, and map controls.</span>
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>Semantic HTML5 elements with accessible aria labels and screen-reader status announcements.</span>
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>Non-color-only indicators: all priorities (P1-P4) and statuses include distinct text badges and icons.</span>
          </li>
          <li className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>Multilingual localization supporting English, Telugu, and Hindi.</span>
          </li>
        </ul>
      </div>
    </div>
  );
};

export const NotFoundPage: React.FC = () => {
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center px-4 space-y-4">
      <span className="text-6xl font-extrabold text-brand-600">404</span>
      <h2 className="text-2xl font-bold text-slate-900">Page Not Found</h2>
      <p className="text-xs text-slate-500 max-w-sm">
        The requested municipal address does not exist or has been relocated.
      </p>
      <a
        href="/"
        className="mt-4 px-5 py-2.5 bg-brand-600 text-white text-xs font-semibold rounded-xl hover:bg-brand-700 transition"
      >
        Return to Home
      </a>
    </div>
  );
};

