import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { 
  ArrowLeft, MapPin, Clock, Calendar, CheckCircle2, AlertTriangle, 
  Sparkles, ShieldCheck, XCircle, Star, MessageSquare 
} from 'lucide-react';
import { complaintsService } from '../../services/complaintsService';
import { resolveBackendUrl } from '../../services/api';
import { Complaint, StatusHistory } from '../../types';
import { StatusBadge, PriorityBadge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { MapViewer } from '../../components/common/MapViewer';
import { useToast } from '../../context/ToastContext';

export const ComplaintDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [complaint, setComplaint] = useState<Complaint | null>(null);
  const [timeline, setTimeline] = useState<StatusHistory[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  
  // Verification Modal State
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);
  const [showReopenModal, setShowReopenModal] = useState<boolean>(false);
  const [showCancelModal, setShowCancelModal] = useState<boolean>(false);
  const [cancelReason, setCancelReason] = useState<string>('');
  const [clarificationText, setClarificationText] = useState<string>('');
  const [newComment, setNewComment] = useState<string>('');
  const [rating, setRating] = useState<number>(5);
  const [feedback, setFeedback] = useState<string>('');
  const [reopenReason, setReopenReason] = useState<string>('');
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  const { success, error: toastError } = useToast();

  const loadData = () => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      complaintsService.getComplaintById(id),
      complaintsService.getComplaintTimeline(id)
    ])
      .then(([comp, tl]) => {
        setComplaint(comp);
        setTimeline(tl);
      })
      .catch((err) => {
        toastError('Failed to load complaint', err.message);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, [id]);

  const handleConfirmResolution = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      const updated = await complaintsService.confirmResolution(id, {
        is_satisfied: true,
        feedback_rating: rating,
        feedback_notes: feedback,
      });
      setComplaint(updated);
      setShowConfirmModal(false);
      success('Resolution Confirmed', 'Thank you for verifying this repair!');
      loadData();
    } catch (err: any) {
      toastError('Confirmation Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReopenComplaint = async () => {
    if (!id) return;
    if (!reopenReason.trim() || reopenReason.trim().length < 5) {
      toastError('Validation Error', 'Please provide a clear reason why the issue remains.');
      return;
    }
    setActionLoading(true);
    try {
      const updated = await complaintsService.reopenComplaint(id, {
        reopen_reason: reopenReason,
        feedback_notes: feedback,
      });
      setComplaint(updated);
      setShowReopenModal(false);
      success('Complaint Reopened', 'The department and field crew have been notified for re-inspection.');
      loadData();
    } catch (err: any) {
      toastError('Reopening Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelComplaint = async () => {
    if (!id) return;
    if (!cancelReason.trim() || cancelReason.trim().length < 5) {
      toastError('Validation Error', 'Please provide a documented reason for cancellation.');
      return;
    }
    setActionLoading(true);
    try {
      const updated = await complaintsService.cancelComplaint(id, cancelReason);
      setComplaint(updated);
      setShowCancelModal(false);
      success('Complaint Cancelled', 'Your complaint has been cancelled.');
      loadData();
    } catch (err: any) {
      toastError('Cancellation Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleClarifyComplaint = async () => {
    if (!id) return;
    if (!clarificationText.trim() || clarificationText.trim().length < 5) {
      toastError('Validation Error', 'Please provide the requested information.');
      return;
    }
    setActionLoading(true);
    try {
      const updated = await complaintsService.clarifyComplaint(id, clarificationText);
      setComplaint(updated);
      setClarificationText('');
      success('Clarification Sent', 'Information submitted. Ticket returned to municipal review queue.');
      loadData();
    } catch (err: any) {
      toastError('Submission Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddComment = async () => {
    if (!id || !newComment.trim()) return;
    setActionLoading(true);
    try {
      await complaintsService.addComment(id, newComment);
      setNewComment('');
      success('Comment Posted', 'Your message has been added to the ticket history.');
      loadData();
    } catch (err: any) {
      toastError('Failed to Post', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center text-xs text-slate-400">
        Loading complaint dossier...
      </div>
    );
  }

  if (!complaint) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center space-y-4">
        <h2 className="text-xl font-bold text-slate-800">Complaint Not Found</h2>
        <p className="text-xs text-slate-500">The requested record does not exist or access is restricted.</p>
        <Link to="/citizen" className="inline-block px-4 py-2 bg-brand-600 text-white rounded-xl text-xs font-semibold">
          Return to Dashboard
        </Link>
      </div>
    );
  }

  const isAwaitingVerification = complaint.status === 'AWAITING_CITIZEN_CONFIRMATION';

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Top Breadcrumb */}
      <div>
        <Link
          to="/citizen/complaints"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition mb-3"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to My Complaints</span>
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono font-bold text-brand-700">#{complaint.reference_number}</span>
              <StatusBadge status={complaint.status} />
              <PriorityBadge priority={complaint.priority} />
            </div>
            <h1 className="text-2xl font-extrabold text-slate-900 mt-1">{complaint.title}</h1>
          </div>
          <div className="flex items-center gap-3">
            {complaint.sla_deadline && (
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 bg-slate-100 px-3 py-1.5 rounded-xl self-start sm:self-auto">
                <Clock className="w-3.5 h-3.5 text-brand-600" />
                <span>SLA Target: {new Date(complaint.sla_deadline).toLocaleString()}</span>
              </div>
            )}
            {['SUBMITTED', 'UNDER_REVIEW', 'AWAITING_CITIZEN_INFORMATION', 'VERIFIED'].includes(complaint.status) && (
              <Button
                variant="outline"
                size="sm"
                className="text-rose-600 border-rose-200 hover:bg-rose-50"
                onClick={() => setShowCancelModal(true)}
              >
                Cancel Ticket
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* CLARIFICATION REQUIRED BANNER */}
      {(complaint.status === 'AWAITING_CITIZEN_INFORMATION' || complaint.status === 'NEEDS_MORE_INFORMATION') && (
        <div className="bg-amber-50 border-2 border-amber-300 p-6 rounded-3xl shadow-sm space-y-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500 text-white flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-amber-950">
                Action Required: Additional Information Requested
              </h3>
              <p className="text-xs text-amber-900 leading-relaxed mt-0.5">
                Municipal staff have reviewed your submission and requested additional clarification before work can proceed.
              </p>
              {complaint.clarification_requested && (
                <div className="p-3 bg-white/80 rounded-xl border border-amber-200 mt-2 text-xs font-medium text-amber-950">
                  Staff Question: "{complaint.clarification_requested}"
                </div>
              )}
            </div>
          </div>

          <div className="space-y-2 pt-2">
            <textarea
              rows={3}
              value={clarificationText}
              onChange={(e) => setClarificationText(e.target.value)}
              placeholder="Provide exact landmarks, additional description, or address clarification..."
              className="w-full p-3 bg-white border border-amber-300 rounded-xl text-xs focus:ring-2 focus:ring-amber-500 focus:outline-none"
            />
            <Button
              variant="primary"
              size="sm"
              className="bg-amber-600 hover:bg-amber-700"
              isLoading={actionLoading}
              onClick={handleClarifyComplaint}
            >
              Submit Requested Information
            </Button>
          </div>
        </div>
      )}

      {/* TWO-STAGE CITIZEN VERIFICATION BANNER */}
      {isAwaitingVerification && (
        <div className="bg-gradient-to-br from-emerald-50 via-teal-50 to-white border-2 border-emerald-300 p-6 rounded-3xl shadow-sm space-y-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-600 text-white flex items-center justify-center flex-shrink-0">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-emerald-950">
                Action Required: Official Repair Completed — Please Verify
              </h3>
              <p className="text-xs text-emerald-800 leading-relaxed mt-0.5">
                The municipal field team has submitted their repair notes. Inspect the after-repair notes and confirm whether the hazard is satisfactorily resolved.
              </p>
            </div>
          </div>

          {complaint.resolution_submissions && complaint.resolution_submissions.length > 0 && (
            <div className="p-4 bg-white rounded-2xl border border-emerald-200 text-xs space-y-2">
              <span className="font-bold text-slate-800 uppercase tracking-wider text-[10px] block">
                Field Crew Resolution Notes:
              </span>
              <p className="text-slate-700 leading-relaxed italic">
                "{complaint.resolution_submissions[0].resolution_notes}"
              </p>
              <span className="text-[10px] text-slate-400 block">
                Submitted on {new Date(complaint.resolution_submissions[0].submitted_at).toLocaleString()}
              </span>
            </div>
          )}

          <div className="flex flex-wrap gap-3 pt-2">
            <Button
              variant="primary"
              size="md"
              className="bg-emerald-600 hover:bg-emerald-700 shadow-sm"
              onClick={() => setShowConfirmModal(true)}
              icon={<CheckCircle2 className="w-4 h-4" />}
            >
              Confirm Resolution (Mark Fixed)
            </Button>
            <Button
              variant="outline"
              size="md"
              className="text-rose-700 border-rose-300 hover:bg-rose-50"
              onClick={() => setShowReopenModal(true)}
              icon={<XCircle className="w-4 h-4 text-rose-600" />}
            >
              Issue Still Exists (Reopen)
            </Button>
          </div>
        </div>
      )}

      {/* Main Grid: Details + AI Assessment + Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left: Issue Description & Evidence */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Report Details</h3>
            <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-line">{complaint.description}</p>
            
            <div className="pt-3 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div>
                <span className="text-slate-400 block text-[11px]">Category:</span>
                <span className="font-semibold text-slate-800">{complaint.category} {complaint.subcategory ? `• ${complaint.subcategory}` : ''}</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">Assigned Department:</span>
                <span className="font-semibold text-slate-800">{complaint.department_name || 'General Municipal Queue'}</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">Location Coordinates:</span>
                <span className="font-mono text-slate-700">{complaint.latitude.toFixed(5)}, {complaint.longitude.toFixed(5)}</span>
              </div>
              {complaint.address && (
                <div>
                  <span className="text-slate-400 block text-[11px]">Address:</span>
                  <span className="text-slate-800">{complaint.address}</span>
                </div>
              )}
            </div>

            {/* Interactive Location Map */}
            <div className="pt-3 border-t border-slate-100">
              <span className="text-slate-400 block text-[11px] font-semibold uppercase tracking-wider mb-2">
                Incident Location Map
              </span>
              <MapViewer
                height="240px"
                complaints={[{
                  id: complaint.id,
                  reference_number: complaint.reference_number,
                  title: complaint.title,
                  category: complaint.category,
                  status: complaint.status,
                  priority: complaint.priority,
                  latitude: complaint.latitude,
                  longitude: complaint.longitude,
                  address: complaint.address,
                  first_image: complaint.attachments?.[0]?.file_path,
                }]}
                center={[complaint.latitude, complaint.longitude]}
                zoom={15}
              />
            </div>
          </div>

          {/* Photographic Evidence */}
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Photographic Evidence</h3>
            {complaint.attachments && complaint.attachments.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {complaint.attachments.map((att) => (
                  <div key={att.id} className="border border-slate-200 rounded-2xl overflow-hidden bg-slate-50">
                    <img
                      src={resolveBackendUrl(att.file_path)}
                      alt="Complaint attachment"
                      className="w-full h-48 object-cover hover:scale-105 transition duration-300"
                    />
                    <div className="p-2.5 flex justify-between items-center text-[10px] text-slate-500">
                      <span className="font-semibold uppercase">{att.attachment_type} Evidence</span>
                      <span>{(att.file_size / (1024 * 1024)).toFixed(2)} MB</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 bg-slate-50 rounded-2xl text-center text-xs text-slate-400">
                No photographic evidence was attached to this complaint.
              </div>
            )}
          </div>
        </div>

        {/* Right Sidebar: AI Assessment + Timeline */}
        <div className="space-y-6">
          {/* AI Assessment Card */}
          {complaint.ai_analysis && (
            <div className="bg-gradient-to-br from-ai-50/70 to-white p-5 rounded-3xl border border-ai-200 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold text-ai-700">
                  <Sparkles className="w-4 h-4 text-ai-600" />
                  AI Triage Assessment
                </span>
                <span className="text-[10px] font-mono text-ai-600 bg-ai-100/80 px-2 py-0.5 rounded-md">
                  {Math.round(complaint.ai_analysis.confidence_score * 100)}% Conf.
                </span>
              </div>

              <p className="text-xs text-slate-700 leading-relaxed">
                {complaint.ai_analysis.summary_explanation}
              </p>

              <div className="pt-2 border-t border-ai-100 flex items-center justify-between text-[11px]">
                <span className="text-slate-500">Safety Hazard Flag:</span>
                <span className={`font-semibold ${complaint.ai_analysis.safety_hazard_detected ? 'text-rose-600' : 'text-slate-700'}`}>
                  {complaint.ai_analysis.safety_hazard_detected ? 'Immediate Hazard' : 'Routine'}
                </span>
              </div>
            </div>
          )}

          {/* Immutable Timeline */}
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Status History</h3>
            <div className="space-y-4 relative before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
              {timeline.map((item, idx) => (
                <div key={item.id} className="relative pl-6 space-y-0.5 text-xs">
                  <div className="absolute left-0 top-1 w-4 h-4 rounded-full bg-brand-600 border-2 border-white shadow-xs" />
                  <div className="font-bold text-slate-800">{item.to_status.replace(/_/g, ' ')}</div>
                  {item.change_reason && <p className="text-slate-500 text-[11px]">{item.change_reason}</p>}
                  <span className="text-[10px] text-slate-400 block">
                    {new Date(item.created_at).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* CONFIRM RESOLUTION MODAL */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">Confirm Satisfactory Resolution</h4>
                <p className="text-xs text-slate-500">Rate your experience and close this complaint.</p>
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-semibold text-slate-700">Resolution Quality Rating</label>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setRating(star)}
                    className="p-1 text-slate-300 hover:text-amber-400 transition"
                  >
                    <Star
                      className={`w-6 h-6 ${star <= rating ? 'text-amber-400 fill-amber-400' : ''}`}
                    />
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700">Citizen Feedback (Optional)</label>
              <textarea
                rows={3}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Share any comments on the speed and quality of the field repair..."
                className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowConfirmModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                className="bg-emerald-600 hover:bg-emerald-700"
                isLoading={actionLoading}
                onClick={handleConfirmResolution}
              >
                Approve & Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* REOPEN COMPLAINT MODAL */}
      {showReopenModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">Report Incomplete Repair</h4>
                <p className="text-xs text-slate-500">Explain why this issue still exists.</p>
              </div>
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700">Contest Justification *</label>
              <textarea
                required
                rows={4}
                value={reopenReason}
                onChange={(e) => setReopenReason(e.target.value)}
                placeholder="Explain why the repair is incomplete (e.g. 'Pothole patch broke within 2 hours of rain', 'Only 2 out of 5 streetlights were replaced')..."
                className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-rose-500 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowReopenModal(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                isLoading={actionLoading}
                onClick={handleReopenComplaint}
              >
                Contest & Reopen Ticket
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* CANCEL COMPLAINT MODAL */}
      {showCancelModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center">
                <XCircle className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">Cancel Civic Complaint</h4>
                <p className="text-xs text-slate-500">Provide a reason for withdrawal.</p>
              </div>
            </div>

            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-700">Cancellation Reason *</label>
              <textarea
                required
                rows={3}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Issue resolved by community resident, reported wrong location, no longer hazardous..."
                className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-rose-500 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowCancelModal(false)}>
                Keep Active
              </Button>
              <Button
                variant="danger"
                size="sm"
                isLoading={actionLoading}
                onClick={handleCancelComplaint}
              >
                Confirm Cancellation
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

