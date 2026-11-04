import React from 'react';
import { ShieldCheck, Heart, Award, Users, CheckCircle2 } from 'lucide-react';

export const AboutPage: React.FC = () => {
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 space-y-12">
      <div className="space-y-4 text-center">
        <span className="text-xs font-bold uppercase tracking-wider text-brand-600">About CivicFix AI</span>
        <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">
          "Report. Resolve. Rebuild Trust."
        </h1>
        <p className="text-base text-slate-600 leading-relaxed max-w-2xl mx-auto">
          CivicFix AI was engineered to solve the most pervasive frustration in urban municipal administration: the black hole between a citizen lodging a complaint and receiving an accountable, verified repair.
        </p>
      </div>

      <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-xs space-y-6 text-sm text-slate-600 leading-relaxed">
        <h2 className="text-xl font-bold text-slate-900">Our Core Principles</h2>
        
        <div className="space-y-4">
          <div className="flex gap-4 items-start">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
            <div>
              <strong className="text-slate-900">Two-Stage Verification:</strong>
              <p>Municipal field crews cannot mark an issue resolved on their own word. The reporting citizen must inspect the after-repair evidence and sign off.</p>
            </div>
          </div>

          <div className="flex gap-4 items-start">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
            <div>
              <strong className="text-slate-900">Explainable AI Triage:</strong>
              <p>Machine learning models suggest categories, detect safety hazards, and compute SLAs without acting as black boxes. Every recommendation includes confidence scores and human override audit trails.</p>
            </div>
          </div>

          <div className="flex gap-4 items-start">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
            <div>
              <strong className="text-slate-900">Single-Admin Governance:</strong>
              <p>Exactly one highest-privilege Government Admin seat is provisioned per municipality through a cryptographically secured bootstrap mechanism, preventing unmonitored backdoors.</p>
            </div>
          </div>

          <div className="flex gap-4 items-start">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
            <div>
              <strong className="text-slate-900">Citizen Privacy & Anti-IDOR:</strong>
              <p>Citizen A can never view Citizen B’s private complaint details, addresses, or photos. Public statistics are strictly aggregated and anonymized.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

