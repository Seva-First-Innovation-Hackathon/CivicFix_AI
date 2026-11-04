import React, { useEffect, useState } from 'react';
import { Copy, CheckCircle2, XCircle, MapPin, AlertCircle } from 'lucide-react';
import { adminService } from '../../services/adminService';
import { PotentialDuplicate } from '../../types';
import { Button } from '../../components/common/Button';
import { useToast } from '../../context/ToastContext';

export const DuplicatesPage: React.FC = () => {
  const [duplicates, setDuplicates] = useState<PotentialDuplicate[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const { success, error: toastError } = useToast();

  const loadDuplicates = () => {
    setLoading(true);
    adminService.getPotentialDuplicates()
      .then(setDuplicates)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadDuplicates();
  }, []);

  const handleReview = async (id: string, decision: 'CONFIRMED_MERGED' | 'DISMISSED') => {
    setActionLoading(id);
    try {
      await adminService.reviewDuplicate(id, decision);
      success('Duplicate Reviewed', `Record marked as ${decision}`);
      loadDuplicates();
    } catch (err: any) {
      toastError('Review Failed', err.message);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <span className="text-xs font-bold uppercase tracking-wider text-ai-600">AI Spatial Intelligence</span>
        <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Flagged Duplicate Complaints</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Proximity cluster analysis flags potential duplicate complaints within 100 meters to prevent duplicate crew dispatches.
        </p>
      </div>

      {loading ? (
        <div className="p-12 bg-white rounded-3xl border border-slate-200 text-center text-xs text-slate-400">
          Scanning spatial duplicate index...
        </div>
      ) : duplicates.length === 0 ? (
        <div className="p-12 bg-white rounded-3xl border border-slate-200 text-center space-y-2">
          <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto" />
          <h4 className="text-sm font-bold text-slate-800">No Duplicate Clashes Flagged</h4>
          <p className="text-xs text-slate-500">
            All submitted complaints represent unique spatial locations or distinct civic categories.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {duplicates.map((item) => (
            <div key={item.id} className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-bold text-brand-700">
                    Similarity Score: {Math.round(item.similarity_score * 100)}%
                  </span>
                  <span className="text-xs font-mono text-slate-500">
                    • Distance: {item.distance_meters}m
                  </span>
                </div>
                <span className="text-xs text-slate-400">
                  Detected on {new Date(item.created_at).toLocaleString()}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                {/* Primary Complaint */}
                <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 space-y-1">
                  <span className="font-bold text-brand-700 uppercase tracking-wider text-[10px]">Primary Complaint</span>
                  <div className="font-bold text-slate-900">#{item.primary_reference}</div>
                  <p className="text-slate-600 line-clamp-2">{item.primary_title}</p>
                </div>

                {/* Candidate Duplicate */}
                <div className="p-4 bg-amber-50/50 rounded-2xl border border-amber-200 space-y-1">
                  <span className="font-bold text-amber-700 uppercase tracking-wider text-[10px]">Flagged Potential Duplicate</span>
                  <div className="font-bold text-slate-900">#{item.duplicate_reference}</div>
                  <p className="text-slate-600 line-clamp-2">{item.duplicate_title}</p>
                </div>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed italic bg-slate-50 p-2.5 rounded-xl border border-slate-100">
                AI Detection Rationale: {item.reason}
              </p>

              <div className="flex items-center justify-end gap-2 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleReview(item.id, 'DISMISSED')}
                  isLoading={actionLoading === item.id}
                >
                  Dismiss (Keep Both Separate)
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => handleReview(item.id, 'CONFIRMED_MERGED')}
                  isLoading={actionLoading === item.id}
                  icon={<Copy className="w-3.5 h-3.5" />}
                >
                  Confirm Merge Duplicate
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

