import React from 'react';

export const TermsPage: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 space-y-8">
      <div className="space-y-2 border-b border-slate-200 pb-6">
        <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Legal Agreement</span>
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Terms of Service</h1>
        <p className="text-xs text-slate-500">Guidelines for Municipal Operations & Citizen Reporting</p>
      </div>

      <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-xs space-y-6 text-xs text-slate-600 leading-relaxed">
        <section className="space-y-2">
          <h2 className="text-sm font-bold text-slate-900">1. Proper Use of the Platform</h2>
          <p>
            CivicFix AI is intended for genuine civic infrastructure complaints within municipal jurisdiction. Users agree not to submit fraudulent reports, defamatory statements, obscene imagery, or malicious content.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-bold text-slate-900">2. Emergency Disclaimer</h2>
          <p>
            CivicFix AI does not replace police, ambulance, or fire emergency lines. In emergencies threatening human life, dial 112 directly.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-bold text-slate-900">3. Resolution Accountability</h2>
          <p>
            The two-stage verification policy gives citizens the right to confirm resolution or contest an incomplete repair by reopening the ticket with written justification.
          </p>
        </section>
      </div>
    </div>
  );
};

