import React from 'react';

export const PrivacyPolicyPage: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 space-y-8">
      <div className="space-y-2 border-b border-slate-200 pb-6">
        <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Governance & Compliance</span>
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Citizen Privacy Policy</h1>
        <p className="text-xs text-slate-500">Effective Date: October 2026 • Strict IDOR & Non-Disclosure Protections</p>
      </div>

      <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-xs space-y-6 text-xs text-slate-600 leading-relaxed">
        <section className="space-y-2">
          <h2 className="text-sm font-bold text-slate-900">1. Data Minimization Principle</h2>
          <p>
            CivicFix AI only requests the minimum information strictly required to identify and resolve civic issues. We collect title, description, category, issue location coordinates, and uploaded defect photos. We never track your location continuously in the background. Geolocation permissions are requested solely at the time of report submission.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-bold text-slate-900">2. Strict Isolation and IDOR Prevention</h2>
          <p>
            Every citizen's private complaint history is strictly segmented on the backend database level. Other citizens cannot view your submitted complaints, contact details, or photos. Public maps and aggregate impact dashboards only expose high-level hazard categories and status flags, completely stripped of citizen identifying details.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-bold text-slate-900">3. Photographic Evidence & Object Storage</h2>
          <p>
            Photographs uploaded as evidence are stored in secure object storage with strict MIME validation and random UUID server filenames to prevent path traversal. Access to evidence is authorized only to the reporting citizen and verified municipal personnel.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-bold text-slate-900">4. Immutable Audit Logs</h2>
          <p>
            Administrative actions, AI assessment overrides, and crew assignments generate immutable audit records to guarantee municipal transparency while keeping citizen personal passwords and tokens strictly redacted.
          </p>
        </section>
      </div>
    </div>
  );
};

