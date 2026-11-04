import React from 'react';
import { 
  Camera, MapPin, Cpu, CheckCircle2, ShieldCheck, 
  RotateCcw, Clock, AlertTriangle, Layers 
} from 'lucide-react';

export const HowItWorksPage: React.FC = () => {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-16 space-y-16">
      <div className="text-center max-w-2xl mx-auto space-y-3">
        <span className="text-xs font-bold uppercase tracking-wider text-brand-600">The Municipal Workflow</span>
        <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">How CivicFix AI Works</h1>
        <p className="text-base text-slate-600">
          From the instant a hazard is reported to the final citizen signature: a complete end-to-end accountable cycle.
        </p>
      </div>

      <div className="space-y-12">
        {/* Step 1 */}
        <div className="flex flex-col md:flex-row gap-8 items-start bg-white p-8 rounded-3xl border border-slate-200 shadow-xs">
          <div className="w-14 h-14 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center font-extrabold text-xl flex-shrink-0">
            01
          </div>
          <div className="space-y-3 flex-1">
            <h3 className="text-xl font-bold text-slate-900">Citizen Submission & Evidence Capture</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Citizens submit civic defects through our multi-step wizard. You capture photographic evidence, enter an issue description, and use our Leaflet-powered map picker to set the exact latitude and longitude. Browser geolocation is requested explicitly and never tracked continuously.
            </p>
            <div className="flex flex-wrap gap-2 pt-2">
              <span className="px-3 py-1 bg-slate-100 rounded-lg text-xs font-medium text-slate-700">MIME Type & Size Validation</span>
              <span className="px-3 py-1 bg-slate-100 rounded-lg text-xs font-medium text-slate-700">GPS & Map Pinning</span>
              <span className="px-3 py-1 bg-slate-100 rounded-lg text-xs font-medium text-slate-700">Unique Reference Generated</span>
            </div>
          </div>
        </div>

        {/* Step 2 */}
        <div className="flex flex-col md:flex-row gap-8 items-start bg-white p-8 rounded-3xl border border-slate-200 shadow-xs">
          <div className="w-14 h-14 rounded-2xl bg-ai-50 text-ai-600 flex items-center justify-center font-extrabold text-xl flex-shrink-0">
            02
          </div>
          <div className="space-y-3 flex-1">
            <h3 className="text-xl font-bold text-slate-900">AI Triage, Deduplication & SLA Assignment</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              As soon as the report is saved in PostgreSQL, the AI intelligence pipeline classifies the complaint, evaluates safety risks, checks for nearby spatial duplicates within 100 meters, and suggests an initial priority (P1 to P4) with an exact SLA deadline.
            </p>
            <div className="flex flex-wrap gap-2 pt-2">
              <span className="px-3 py-1 bg-ai-50 text-ai-700 rounded-lg text-xs font-medium border border-ai-200">Haversine Spatial Proximity</span>
              <span className="px-3 py-1 bg-ai-50 text-ai-700 rounded-lg text-xs font-medium border border-ai-200">P1-P4 Severity Rules</span>
              <span className="px-3 py-1 bg-ai-50 text-ai-700 rounded-lg text-xs font-medium border border-ai-200">Human-in-the-Loop Override Log</span>
            </div>
          </div>
        </div>

        {/* Step 3 */}
        <div className="flex flex-col md:flex-row gap-8 items-start bg-white p-8 rounded-3xl border border-slate-200 shadow-xs">
          <div className="w-14 h-14 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center font-extrabold text-xl flex-shrink-0">
            03
          </div>
          <div className="space-y-3 flex-1">
            <h3 className="text-xl font-bold text-slate-900">Municipal Review & Field Crew Dispatch</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              Authorized municipal officers inspect complaints in their department queue, review the AI triage, and create work orders for certified field crews. The field crew receives task directions, updates progress, and uploads after-repair completion photographs.
            </p>
            <div className="flex flex-wrap gap-2 pt-2">
              <span className="px-3 py-1 bg-slate-100 rounded-lg text-xs font-medium text-slate-700">Department Scope Enforcement</span>
              <span className="px-3 py-1 bg-slate-100 rounded-lg text-xs font-medium text-slate-700">Stage 1 Resolution Evidence</span>
            </div>
          </div>
        </div>

        {/* Step 4 */}
        <div className="flex flex-col md:flex-row gap-8 items-start bg-white p-8 rounded-3xl border border-slate-200 shadow-xs">
          <div className="w-14 h-14 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-extrabold text-xl flex-shrink-0">
            04
          </div>
          <div className="space-y-3 flex-1">
            <h3 className="text-xl font-bold text-slate-900">Stage 2: Citizen Verification or Reopening</h3>
            <p className="text-sm text-slate-600 leading-relaxed">
              A complaint cannot be finalized simply because a crew claimed it was done. The reporting citizen receives an in-app alert, views side-by-side before-and-after evidence, and either clicks <strong>"Confirm Resolution"</strong> or <strong>"Issue Still Exists"</strong> to reopen the task with an explanation.
            </p>
            <div className="flex flex-wrap gap-2 pt-2">
              <span className="px-3 py-1 bg-emerald-50 text-emerald-800 rounded-lg text-xs font-medium border border-emerald-200">Citizen Sign-Off Rule</span>
              <span className="px-3 py-1 bg-emerald-50 text-emerald-800 rounded-lg text-xs font-medium border border-emerald-200">Reopening Audit History</span>
              <span className="px-3 py-1 bg-emerald-50 text-emerald-800 rounded-lg text-xs font-medium border border-emerald-200">1 to 5 Star Feedback Rating</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

