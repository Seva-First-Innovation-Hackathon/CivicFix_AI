import React, { useState } from 'react';
import { Mail, Phone, MapPin, Send, CheckCircle2 } from 'lucide-react';
import { Button } from '../../components/common/Button';

export const ContactPage: React.FC = () => {
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16 space-y-12">
      <div className="text-center space-y-2">
        <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Municipal Helpdesk</span>
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Contact & Support</h1>
        <p className="text-sm text-slate-600">
          Have an administrative inquiry or need technical support with the CivicFix AI platform?
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-xs space-y-6">
          <h3 className="text-lg font-bold text-slate-900">Municipal Central Office</h3>
          
          <div className="space-y-4 text-xs text-slate-600">
            <div className="flex items-start gap-3">
              <MapPin className="w-4 h-4 text-brand-600 flex-shrink-0 mt-0.5" />
              <span>Municipal Corporation Headquarters, Civil Services Plaza, Main Boulevard</span>
            </div>
            <div className="flex items-center gap-3">
              <Phone className="w-4 h-4 text-brand-600 flex-shrink-0" />
              <span>General Grievance Helpline: 1800-425-0011 (9 AM - 6 PM)</span>
            </div>
            <div className="flex items-center gap-3">
              <Mail className="w-4 h-4 text-brand-600 flex-shrink-0" />
              <span>support@civicfix.gov</span>
            </div>
          </div>

          <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 text-xs leading-relaxed">
            <strong>Emergency Reminder:</strong> For active vehicle accidents, fires, or life-threatening emergencies, dial 112 immediately.
          </div>
        </div>

        <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-xs">
          {submitted ? (
            <div className="text-center py-8 space-y-3">
              <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h4 className="text-base font-bold text-slate-900">Inquiry Dispatched</h4>
              <p className="text-xs text-slate-500">
                Your message has been assigned a tracking token and forwarded to the municipal grievance desk.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Your Name</label>
                <input
                  type="text"
                  required
                  placeholder="Full name"
                  className="w-full px-3.5 py-2 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  placeholder="name@example.com"
                  className="w-full px-3.5 py-2 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Message</label>
                <textarea
                  required
                  rows={4}
                  placeholder="How can we assist you with CivicFix AI?"
                  className="w-full px-3.5 py-2 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <Button type="submit" variant="primary" className="w-full justify-center">
                Send Inquiry
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

