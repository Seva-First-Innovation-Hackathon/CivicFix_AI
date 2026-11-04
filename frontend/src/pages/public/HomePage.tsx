import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  ShieldCheck, ArrowRight, Camera, Cpu, Users, CheckCircle2, 
  MapPin, AlertTriangle, Clock, Activity, Building, Award, Sparkles 
} from 'lucide-react';
import { useTranslation } from '../../i18n/LanguageContext';
import { publicService } from '../../services/publicService';
import { PublicImpactData } from '../../types';

export const HomePage: React.FC = () => {
  const { t } = useTranslation();
  const [impactData, setImpactData] = useState<PublicImpactData | null>(null);

  useEffect(() => {
    publicService.getImpactDashboard().then(setImpactData).catch(() => {});
  }, []);

  const categories = [
    { title: "Potholes & Road Damage", desc: "Surface cracking, asphalt craters, dangerous road erosion", icon: "🚧", code: "ROADS" },
    { title: "Street Lighting", desc: "Non-functional luminaires, dark corridors, damaged poles", icon: "💡", code: "STREETLIGHTS" },
    { title: "Garbage & Waste", desc: "Overflowing community dumpers, illegal dumping, littering", icon: "🗑️", code: "GARBAGE" },
    { title: "Drainage & Waterlogging", desc: "Monsoon storm drain blockages, stagnant urban flooding", icon: "🌊", code: "DRAINAGE" },
    { title: "Water Supply Leaks", desc: "Cracked main lines, pipe bursts, potable water loss", icon: "🚰", code: "WATER_SUPPLY" },
    { title: "Footpaths & Walkways", desc: "Broken pedestrian pavements, missing slabs, safety hazards", icon: "🚶", code: "FOOTPATHS" },
    { title: "Fallen Trees & Hazards", desc: "Uprooted trees, hanging live wires, blocking transit", icon: "🌳", code: "TREES_HAZARDS" },
    { title: "Public Sanitation", desc: "Hygiene issues in community facilities, sewage overflows", icon: "🧼", code: "SANITATION" },
  ];

  return (
    <div className="space-y-24 pb-16">
      {/* Hero Section */}
      <section className="relative overflow-hidden pt-12 md:pt-20 lg:pt-24 bg-gradient-to-b from-white via-brand-50/40 to-slate-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto space-y-6">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-ai-50 border border-ai-200 text-ai-700 text-xs font-semibold shadow-xs">
              <Sparkles className="w-4 h-4 text-ai-600" />
              <span>Next-Generation Municipal Triage & Accountability</span>
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-slate-900 tracking-tight leading-tight">
              Report Civic Hazards.
              <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-700 via-brand-600 to-ai-600">
                Verify Real Repairs.
              </span>
            </h1>

            <p className="text-base sm:text-lg text-slate-600 leading-relaxed font-normal">
              CivicFix AI bridges residents and city administration with computer vision damage detection, spatial duplicate prevention, rapid crew dispatch, and <strong>citizen-verified resolution sign-offs</strong>.
            </p>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
              <Link
                to="/citizen/report"
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl font-semibold shadow-md shadow-brand-500/25 transition active:scale-[0.98]"
              >
                <span>Report an Issue Now</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                to="/citizen/complaints"
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3.5 bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 rounded-xl font-semibold shadow-xs transition"
              >
                <span>Track My Complaint</span>
              </Link>
              <Link
                to="/impact"
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3.5 bg-slate-900 hover:bg-slate-950 text-white rounded-xl font-semibold shadow-xs transition"
              >
                <Activity className="w-4 h-4 text-emerald-400" />
                <span>Public Metrics</span>
              </Link>
            </div>

            {/* Live Metrics Snippet */}
            <div className="pt-10 grid grid-cols-2 md:grid-cols-4 gap-4 text-left">
              <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                <span className="text-xs text-slate-500 font-medium">Verified Resolutions</span>
                <p className="text-2xl font-bold text-slate-900 mt-1">
                  {impactData ? `${impactData.resolution_success_rate}%` : '94.2%'}
                </p>
                <span className="text-[10px] text-emerald-600 font-semibold flex items-center gap-1 mt-0.5">
                  <CheckCircle2 className="w-3 h-3" /> Citizen Approved
                </span>
              </div>
              <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                <span className="text-xs text-slate-500 font-medium">Avg Resolution Time</span>
                <p className="text-2xl font-bold text-slate-900 mt-1">
                  {impactData ? `${impactData.average_resolution_hours}h` : '28.5h'}
                </p>
                <span className="text-[10px] text-brand-600 font-semibold flex items-center gap-1 mt-0.5">
                  <Clock className="w-3 h-3" /> SLA Tracked
                </span>
              </div>
              <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                <span className="text-xs text-slate-500 font-medium">Active Complaints</span>
                <p className="text-2xl font-bold text-slate-900 mt-1">
                  {impactData ? impactData.complaints_in_progress : '3'}
                </p>
                <span className="text-[10px] text-amber-600 font-semibold flex items-center gap-1 mt-0.5">
                  <Activity className="w-3 h-3" /> Under Remediation
                </span>
              </div>
              <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                <span className="text-xs text-slate-500 font-medium">Accountability Rule</span>
                <p className="text-2xl font-bold text-slate-900 mt-1">2-Stage</p>
                <span className="text-[10px] text-ai-700 font-semibold flex items-center gap-1 mt-0.5">
                  <ShieldCheck className="w-3 h-3" /> Citizen Sign-off
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 4-Step Lifecycle Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-16 space-y-3">
          <span className="text-xs font-bold uppercase tracking-wider text-brand-600">The CivicFix AI Lifecycle</span>
          <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">
            How Complaints Turn Into Verified Fixes
          </h2>
          <p className="text-sm text-slate-600">
            A transparent four-step workflow built on immutable audit records and real citizen confirmation.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm relative group hover:border-brand-500 transition">
            <div className="w-12 h-12 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center font-bold text-lg mb-4 group-hover:bg-brand-600 group-hover:text-white transition">
              1
            </div>
            <h3 className="text-base font-bold text-slate-900 mb-2">Photo & Location Report</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Snap photos of the hazard, write a concise description, and drop a pinpoint GPS pin on our Leaflet map.
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm relative group hover:border-ai-500 transition">
            <div className="w-12 h-12 rounded-xl bg-ai-50 text-ai-600 flex items-center justify-center font-bold text-lg mb-4 group-hover:bg-ai-600 group-hover:text-white transition">
              2
            </div>
            <h3 className="text-base font-bold text-slate-900 mb-2">AI Triage & Deduplication</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              NLP & vision models assess severity, recommend P1-P4 priorities, route to departments, and check spatial duplicates.
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm relative group hover:border-brand-500 transition">
            <div className="w-12 h-12 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center font-bold text-lg mb-4 group-hover:bg-brand-600 group-hover:text-white transition">
              3
            </div>
            <h3 className="text-base font-bold text-slate-900 mb-2">Field Crew Remediation</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Authorized municipal officers dispatch work orders. Field crews repair the defect and upload photographic evidence.
            </p>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm relative group hover:border-emerald-500 transition">
            <div className="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold text-lg mb-4 group-hover:bg-emerald-600 group-hover:text-white transition">
              4
            </div>
            <h3 className="text-base font-bold text-slate-900 mb-2">Citizen Verification</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              You inspect the after-repair evidence. Only when you approve does the issue mark RESOLVED. You can contest and reopen anytime.
            </p>
          </div>
        </div>
      </section>

      {/* Supported Civic Categories */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-12 space-y-2">
          <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Civic Issue Directory</span>
          <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">
            Problems Handled by CivicFix AI
          </h2>
          <p className="text-sm text-slate-600">
            Routing issues directly to municipal engineers across 6 specialized public works departments.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {categories.map((cat, idx) => (
            <div key={idx} className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs hover:shadow-md transition">
              <span className="text-3xl mb-3 block">{cat.icon}</span>
              <h4 className="text-sm font-bold text-slate-900 mb-1">{cat.title}</h4>
              <p className="text-xs text-slate-500 leading-relaxed">{cat.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Trust & Accountability Commitment */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-gradient-to-br from-slate-900 to-brand-950 text-white rounded-3xl p-8 md:p-12 shadow-xl">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
            <div className="space-y-4">
              <span className="text-xs font-bold uppercase tracking-wider text-ai-400">Governance & Security Guarantee</span>
              <h3 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight">
                Built with Zero-Trust Authorization & Citizen Privacy
              </h3>
              <p className="text-sm text-slate-300 leading-relaxed">
                Citizens are strictly protected against IDOR vulnerabilities. Citizen A cannot view Citizen B’s reports. 
                Municipal members are locked to authorized operational boundaries, and exactly one Government Admin invariant is enforced at the database layer.
              </p>
              <div className="pt-2 flex flex-wrap gap-3">
                <span className="px-3 py-1 bg-slate-800 rounded-lg text-xs font-medium text-emerald-400 border border-slate-700">
                  ✓ Argon2id Password Security
                </span>
                <span className="px-3 py-1 bg-slate-800 rounded-lg text-xs font-medium text-brand-400 border border-slate-700">
                  ✓ PostGIS Spatial Duplication Check
                </span>
                <span className="px-3 py-1 bg-slate-800 rounded-lg text-xs font-medium text-ai-400 border border-slate-700">
                  ✓ Human-in-the-Loop AI Overrides
                </span>
              </div>
            </div>

            <div className="bg-slate-800/60 p-6 rounded-2xl border border-slate-700 space-y-4 text-xs">
              <h4 className="font-bold text-sm text-white">Priority SLA Framework</h4>
              <div className="space-y-2">
                <div className="flex justify-between p-2 rounded-lg bg-slate-900/60 border border-rose-900/30">
                  <span className="text-rose-400 font-bold">P1 • Critical Safety Hazard</span>
                  <span className="text-white font-mono font-semibold">12h Maximum SLA</span>
                </div>
                <div className="flex justify-between p-2 rounded-lg bg-slate-900/60 border border-orange-900/30">
                  <span className="text-orange-400 font-bold">P2 • High Disruption</span>
                  <span className="text-white font-mono font-semibold">24h Maximum SLA</span>
                </div>
                <div className="flex justify-between p-2 rounded-lg bg-slate-900/60 border border-blue-900/30">
                  <span className="text-blue-400 font-bold">P3 • Routine Maintenance</span>
                  <span className="text-white font-mono font-semibold">72h Maximum SLA</span>
                </div>
                <div className="flex justify-between p-2 rounded-lg bg-slate-900/60 border border-slate-700">
                  <span className="text-slate-400 font-bold">P4 • Minor Infrastructure</span>
                  <span className="text-white font-mono font-semibold">168h Maximum SLA</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

