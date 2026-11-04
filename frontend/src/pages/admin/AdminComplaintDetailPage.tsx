import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { 
  ArrowLeft, Sparkles, Building2, Wrench, CheckCircle2, 
  Clock, ShieldAlert, AlertTriangle, Eye, Send, Check, UserCheck,
  HelpCircle, XCircle, FileText, Lock, MessageSquare, RotateCcw,
  AlertOctagon, User as UserIcon
} from 'lucide-react';
import { adminService } from '../../services/adminService';
import { complaintsService } from '../../services/complaintsService';
import { resolveBackendUrl } from '../../services/api';
import { Complaint, Department, User, ComplaintComment } from '../../types';
import { StatusBadge, PriorityBadge } from '../../components/common/Badge';
import { Button } from '../../components/common/Button';
import { MapViewer } from '../../components/common/MapViewer';
import { useToast } from '../../context/ToastContext';

export const AdminComplaintDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [complaint, setComplaint] = useState<Complaint | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [crews, setCrews] = useState<User[]>([]);
  const [comments, setComments] = useState<ComplaintComment[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Modals & Action States
  const [showVerifyModal, setShowVerifyModal] = useState<boolean>(false);
  const [verifyPriority, setVerifyPriority] = useState<string>('P3');
  const [verifyNotes, setVerifyNotes] = useState<string>('');

  const [showRequestInfoModal, setShowRequestInfoModal] = useState<boolean>(false);
  const [requestInfoText, setRequestInfoText] = useState<string>('');

  const [showRejectModal, setShowRejectModal] = useState<boolean>(false);
  const [rejectReason, setRejectReason] = useState<string>('');

  const [showFlagModal, setShowFlagModal] = useState<boolean>(false);
  const [flagReason, setFlagReason] = useState<string>('');

  const [showReviewEvidenceModal, setShowReviewEvidenceModal] = useState<boolean>(false);
  const [reviewIsApproved, setReviewIsApproved] = useState<boolean>(true);
  const [reviewNotes, setReviewNotes] = useState<string>('');

  const [showOverrideModal, setShowOverrideModal] = useState<boolean>(false);
  const [overrideReason, setOverrideReason] = useState<string>('');
  const [overrideCategory, setOverrideCategory] = useState<string>('');
  const [overridePriority, setOverridePriority] = useState<string>('');

  // Internal Note form
  const [internalNoteContent, setInternalNoteContent] = useState<string>('');
  const [noteLoading, setNoteLoading] = useState<boolean>(false);

  // Assignment & Work order
  const [selectedDeptId, setSelectedDeptId] = useState<string>('');
  const [selectedPriority, setSelectedPriority] = useState<string>('');
  const [assignLoading, setAssignLoading] = useState<boolean>(false);
  const [selectedCrewId, setSelectedCrewId] = useState<string>('');
  const [workOrderTitle, setWorkOrderTitle] = useState<string>('');
  const [workOrderInstructions, setWorkOrderInstructions] = useState<string>('');
  const [dispatchLoading, setDispatchLoading] = useState<boolean>(false);

  // Generic action loading
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  const { success, error: toastError } = useToast();

  const loadData = () => {
    if (!id) return;
    setLoading(true);
    Promise.all([
      adminService.getComplaint(id),
      adminService.getDepartments(),
      adminService.listUsers('FIELD_CREW'),
      complaintsService.getComments(id).catch(() => [])
    ])
      .then(([comp, depts, crewUsers, comms]) => {
        setComplaint(comp);
        setDepartments(depts);
        setCrews(crewUsers);
        setComments(comms || []);
        setSelectedDeptId(comp.department_id || (depts[0]?.id || ''));
        setSelectedPriority(comp.priority);
        setVerifyPriority(comp.priority);
        setWorkOrderTitle(`Remediation: ${comp.title}`);
        setWorkOrderInstructions(`Deploy crew to inspect site at ${comp.address || 'coordinates'}. Repair defect to municipal standard.`);
      })
      .catch((err) => toastError('Error', err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, [id]);

  // Auth token for evidence rendering
  const token = localStorage.getItem('token') || '';

  // 1. Verify Complaint & Set Priority
  const handleVerifyComplaint = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      const updated = await adminService.verifyComplaint(id, verifyPriority, verifyNotes || undefined);
      setComplaint(updated);
      setShowVerifyModal(false);
      setVerifyNotes('');
      success('Complaint Verified', `Status updated to VERIFIED with priority ${verifyPriority}.`);
      loadData();
    } catch (err: any) {
      toastError('Verification Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 2. Request Citizen Clarification
  const handleRequestInfo = async () => {
    if (!id || !requestInfoText.trim()) {
      toastError('Validation', 'Please describe the clarification required from the citizen.');
      return;
    }
    setActionLoading(true);
    try {
      const updated = await adminService.requestMoreInfo(id, requestInfoText);
      setComplaint(updated);
      setShowRequestInfoModal(false);
      setRequestInfoText('');
      success('Clarification Requested', 'Status updated to AWAITING_CITIZEN_INFORMATION. Resident notified.');
      loadData();
    } catch (err: any) {
      toastError('Request Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 3. Reject Complaint
  const handleRejectComplaint = async () => {
    if (!id || !rejectReason.trim()) {
      toastError('Validation', 'A documented rejection reason is mandatory.');
      return;
    }
    setActionLoading(true);
    try {
      const updated = await adminService.rejectComplaint(id, rejectReason);
      setComplaint(updated);
      setShowRejectModal(false);
      setRejectReason('');
      success('Complaint Rejected', 'Complaint marked as REJECTED with reason recorded.');
      loadData();
    } catch (err: any) {
      toastError('Rejection Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 4. Flag for Investigation
  const handleFlagInvestigation = async () => {
    if (!id || !flagReason.trim()) {
      toastError('Validation', 'A documented investigation reason is mandatory.');
      return;
    }
    setActionLoading(true);
    try {
      const updated = await adminService.flagInvestigation(id, flagReason);
      setComplaint(updated);
      setShowFlagModal(false);
      setFlagReason('');
      success('Flagged for Investigation', 'Security/compliance team alerted. Status updated.');
      loadData();
    } catch (err: any) {
      toastError('Action Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 5. Review Crew Evidence (Approve / Return for Rework)
  const handleReviewEvidence = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      const updated = await adminService.reviewEvidence(id, reviewIsApproved, reviewNotes);
      setComplaint(updated);
      setShowReviewEvidenceModal(false);
      setReviewNotes('');
      if (reviewIsApproved) {
        success('Evidence Approved', 'Status moved to AWAITING_CITIZEN_CONFIRMATION for resident sign-off.');
      } else {
        success('Returned for Rework', 'Complaint returned to IN_PROGRESS. Field crew notified.');
      }
      loadData();
    } catch (err: any) {
      toastError('Evidence Review Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 6. Add Internal Staff Note
  const handleAddInternalNote = async () => {
    if (!id || !internalNoteContent.trim()) return;
    setNoteLoading(true);
    try {
      await adminService.addInternalNote(id, internalNoteContent);
      setInternalNoteContent('');
      success('Note Added', 'Internal staff note recorded securely.');
      const comms = await complaintsService.getComments(id);
      setComments(comms);
    } catch (err: any) {
      toastError('Failed to add note', err.message);
    } finally {
      setNoteLoading(false);
    }
  };

  // 7. Override AI Assessment
  const handleOverrideAI = async () => {
    if (!id || !overrideReason.trim()) {
      toastError('Validation', 'A recorded override reason is mandatory.');
      return;
    }
    setActionLoading(true);
    try {
      const updated = await adminService.reviewAiAssessment(
        id,
        overrideReason,
        overrideCategory || undefined,
        overridePriority || undefined
      );
      setComplaint(updated);
      setShowOverrideModal(false);
      setOverrideReason('');
      success('AI Assessment Overridden', 'Audit record generated successfully.');
    } catch (err: any) {
      toastError('Override Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // 8. Assign Department
  const handleAssignDepartment = async () => {
    if (!id || !selectedDeptId) return;
    setAssignLoading(true);
    try {
      const updated = await adminService.assignComplaint(id, selectedDeptId, selectedPriority);
      setComplaint(updated);
      success('Department Assigned', 'Complaint assigned and priority set.');
    } catch (err: any) {
      toastError('Assignment Failed', err.message);
    } finally {
      setAssignLoading(false);
    }
  };

  // 9. Dispatch Work Order
  const handleDispatchWorkOrder = async () => {
    if (!id || !selectedCrewId || !workOrderInstructions.trim()) {
      toastError('Validation', 'Please select a crew and provide instructions.');
      return;
    }
    setDispatchLoading(true);
    try {
      await adminService.createWorkOrder({
        complaint_id: id,
        department_id: selectedDeptId || complaint?.department_id || departments[0]?.id,
        crew_id: selectedCrewId,
        title: workOrderTitle,
        instructions: workOrderInstructions,
      });
      success('Work Order Dispatched', 'Field crew assigned and ticket set to IN_PROGRESS.');
      loadData();
    } catch (err: any) {
      toastError('Dispatch Failed', err.message);
    } finally {
      setDispatchLoading(false);
    }
  };

  if (loading || !complaint) {
    return <div className="p-12 text-center text-xs text-slate-400">Loading complaint details...</div>;
  }

  const isTriagePhase = ['SUBMITTED', 'AI_ANALYSIS_PENDING', 'UNDER_REVIEW', 'AWAITING_CITIZEN_INFORMATION', 'REOPENED'].includes(complaint.status);
  const isPendingReview = complaint.status === 'WORK_COMPLETED_PENDING_REVIEW';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          to="/admin/complaints"
          className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 transition mb-3"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Complaints Register</span>
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
          {complaint.sla_deadline && (
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 bg-white border border-slate-200 px-3 py-1.5 rounded-xl shadow-xs self-start sm:self-auto">
              <Clock className="w-3.5 h-3.5 text-brand-600" />
              <span>SLA Target: {new Date(complaint.sla_deadline).toLocaleString()}</span>
            </div>
          )}
        </div>
      </div>

      {/* STATUS-SPECIFIC NOTICES & BANNERS */}
      {isPendingReview && (
        <div className="p-5 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-xs">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-sm font-bold">Field Repairs Completed — Evidence Review Required</h4>
              <p className="text-xs text-amber-700 mt-0.5">
                The assigned field crew has submitted remediation evidence. Review the photographs and notes below before sign-off.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="text-rose-700 border-rose-300 hover:bg-rose-100/50"
              onClick={() => {
                setReviewIsApproved(false);
                setShowReviewEvidenceModal(true);
              }}
              icon={<RotateCcw className="w-3.5 h-3.5" />}
            >
              Return for Rework
            </Button>
            <Button
              size="sm"
              variant="primary"
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
              onClick={() => {
                setReviewIsApproved(true);
                setShowReviewEvidenceModal(true);
              }}
              icon={<CheckCircle2 className="w-3.5 h-3.5" />}
            >
              Approve Resolution
            </Button>
          </div>
        </div>
      )}

      {complaint.status === 'AWAITING_CITIZEN_INFORMATION' && (
        <div className="p-4 rounded-2xl bg-sky-50 border border-sky-200 text-sky-900 flex items-start gap-3">
          <HelpCircle className="w-5 h-5 text-sky-600 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-bold block">Awaiting Citizen Clarification:</span>
            <p className="text-sky-800 mt-0.5">{complaint.clarification_requested || 'Specific details requested from the resident.'}</p>
          </div>
        </div>
      )}

      {complaint.status === 'FLAGGED_FOR_INVESTIGATION' && (
        <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-900 flex items-start gap-3">
          <AlertOctagon className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-bold block">Flagged for Formal Investigation:</span>
            <p className="text-rose-800 mt-0.5">{complaint.investigation_notes || 'Marked suspicious, safety risk, or disputed boundary.'}</p>
          </div>
        </div>
      )}

      {complaint.status === 'REJECTED' && (
        <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-900 flex items-start gap-3">
          <XCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-bold block">Complaint Rejected:</span>
            <p className="text-rose-800 mt-0.5">{complaint.rejection_reason || 'Rejected by municipal authority.'}</p>
          </div>
        </div>
      )}

      {complaint.status === 'CANCELLED' && (
        <div className="p-4 rounded-2xl bg-slate-100 border border-slate-300 text-slate-800 flex items-start gap-3">
          <XCircle className="w-5 h-5 text-slate-500 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-bold block">Cancelled by Citizen:</span>
            <p className="text-slate-600 mt-0.5">{complaint.cancellation_reason || 'No specific reason recorded.'}</p>
          </div>
        </div>
      )}

      {/* MUNICIPAL ACTION BAR */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-700">
          <ShieldAlert className="w-4 h-4 text-brand-600" />
          <span>Municipal Authority Actions:</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isTriagePhase && (
            <Button
              size="sm"
              variant="primary"
              onClick={() => setShowVerifyModal(true)}
              icon={<CheckCircle2 className="w-3.5 h-3.5" />}
            >
              Verify & Set Priority
            </Button>
          )}

          {complaint.status !== 'RESOLVED' && complaint.status !== 'CANCELLED' && complaint.status !== 'REJECTED' && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowRequestInfoModal(true)}
                icon={<HelpCircle className="w-3.5 h-3.5" />}
              >
                Request Citizen Clarification
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-amber-700 border-amber-300 hover:bg-amber-50"
                onClick={() => setShowFlagModal(true)}
                icon={<AlertOctagon className="w-3.5 h-3.5" />}
              >
                Flag for Investigation
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-rose-700 border-rose-300 hover:bg-rose-50"
                onClick={() => setShowRejectModal(true)}
                icon={<XCircle className="w-3.5 h-3.5" />}
              >
                Reject
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column (2 spans): Details + AI + Operational Routing + Notes */}
        <div className="lg:col-span-2 space-y-6">
          {/* Issue Summary Card */}
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Report Details</h3>
            <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-line">{complaint.description}</p>
            <div className="pt-3 border-t border-slate-100 grid grid-cols-2 gap-3 text-xs">
              <div>
                <span className="text-slate-400 block text-[11px]">Category:</span>
                <span className="font-semibold text-slate-800">{complaint.category}</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[11px]">Location Coordinates:</span>
                <span className="font-mono text-slate-700">{complaint.latitude.toFixed(5)}, {complaint.longitude.toFixed(5)}</span>
              </div>
              {complaint.address && (
                <div className="col-span-2">
                  <span className="text-slate-400 block text-[11px]">Address:</span>
                  <span className="text-slate-800">{complaint.address} {complaint.landmark ? `(Near ${complaint.landmark})` : ''}</span>
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

          {/* AI Intelligence Assessment Panel */}
          {complaint.ai_analysis && (
            <div className="bg-gradient-to-br from-ai-50/60 to-white p-6 rounded-3xl border border-ai-200 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-ai-600 text-white flex items-center justify-center">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">AI Triage Intelligence</h3>
                    <p className="text-[10px] text-ai-700 font-mono">
                      Model: {complaint.ai_analysis.model_name} • {Math.round(complaint.ai_analysis.confidence_score * 100)}% Confidence
                    </p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowOverrideModal(true)}
                  className="text-ai-700 border-ai-300 hover:bg-ai-50"
                >
                  Override Assessment
                </Button>
              </div>

              <div className="p-3.5 bg-white/90 rounded-2xl border border-ai-100 text-xs text-slate-700 leading-relaxed">
                {complaint.ai_analysis.summary_explanation}
              </div>

              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="p-2.5 bg-white rounded-xl border border-ai-100">
                  <span className="text-[10px] text-slate-400 block uppercase font-semibold">Suggested Priority</span>
                  <span className="font-bold text-slate-900">{complaint.ai_analysis.suggested_priority}</span>
                </div>
                <div className="p-2.5 bg-white rounded-xl border border-ai-100">
                  <span className="text-[10px] text-slate-400 block uppercase font-semibold">Urgency Level</span>
                  <span className="font-bold text-slate-900">{complaint.ai_analysis.urgency_level}</span>
                </div>
                <div className="p-2.5 bg-white rounded-xl border border-ai-100">
                  <span className="text-[10px] text-slate-400 block uppercase font-semibold">Safety Hazard</span>
                  <span className={`font-bold ${complaint.ai_analysis.safety_hazard_detected ? 'text-rose-600' : 'text-slate-800'}`}>
                    {complaint.ai_analysis.safety_hazard_detected ? 'Detected' : 'None'}
                  </span>
                </div>
              </div>

              {complaint.ai_analysis.is_overridden && (
                <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-900">
                  <strong>Administrative Override Applied:</strong> {complaint.ai_analysis.override_reason}
                </div>
              )}
            </div>
          )}

          {/* Operational Action 1: Department & Priority Assignment */}
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
              <Building2 className="w-4 h-4 text-brand-600" />
              Department Routing & Priority Assignment
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Assigned Department</label>
                <select
                  value={selectedDeptId}
                  onChange={(e) => setSelectedDeptId(e.target.value)}
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800 focus:ring-2 focus:ring-brand-500"
                >
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Confirmed Priority</label>
                <select
                  value={selectedPriority}
                  onChange={(e) => setSelectedPriority(e.target.value)}
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800 focus:ring-2 focus:ring-brand-500"
                >
                  <option value="P1">P1 • Critical (12h SLA)</option>
                  <option value="P2">P2 • High (24h SLA)</option>
                  <option value="P3">P3 • Normal (72h SLA)</option>
                  <option value="P4">P4 • Low (168h SLA)</option>
                </select>
              </div>
            </div>

            <Button
              variant="primary"
              size="sm"
              isLoading={assignLoading}
              onClick={handleAssignDepartment}
              icon={<Send className="w-3.5 h-3.5" />}
            >
              Update Department Assignment
            </Button>
          </div>

          {/* Operational Action 2: Field Crew Work Order Dispatch */}
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
              <Wrench className="w-4 h-4 text-brand-600" />
              Dispatch Work Order to Field Crew
            </h3>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Select Field Crew</label>
                <select
                  value={selectedCrewId}
                  onChange={(e) => setSelectedCrewId(e.target.value)}
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800 focus:ring-2 focus:ring-brand-500"
                >
                  <option value="">-- Choose Field Crew --</option>
                  {crews.map((cr) => (
                    <option key={cr.id} value={cr.id}>
                      {cr.full_name} ({cr.crew_profile?.vehicle_number || 'Mobile Unit'})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Work Order Instructions</label>
                <textarea
                  rows={3}
                  value={workOrderInstructions}
                  onChange={(e) => setWorkOrderInstructions(e.target.value)}
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <Button
                variant="secondary"
                size="sm"
                isLoading={dispatchLoading}
                onClick={handleDispatchWorkOrder}
                icon={<Wrench className="w-3.5 h-3.5" />}
              >
                Dispatch Work Order (Set In Progress)
              </Button>
            </div>
          </div>

          {/* Internal Staff Notes & Communication Log */}
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
              <Lock className="w-4 h-4 text-brand-600" />
              Internal Staff Notes & Case Log
            </h3>
            <p className="text-xs text-slate-500">
              Staff notes are private and strictly hidden from citizens. Use this section to log internal investigations, contractor notes, and inter-departmental communications.
            </p>

            <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
              {comments.length === 0 ? (
                <div className="p-4 bg-slate-50 rounded-xl text-center text-xs text-slate-400">
                  No internal notes or comments recorded yet.
                </div>
              ) : (
                comments.map((cm) => (
                  <div
                    key={cm.id}
                    className={`p-3.5 rounded-2xl text-xs border ${
                      cm.is_internal
                        ? 'bg-amber-50/70 border-amber-200 text-amber-950'
                        : 'bg-slate-50 border-slate-200 text-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-1.5 font-bold">
                        {cm.is_internal ? (
                          <>
                            <Lock className="w-3 h-3 text-amber-700" />
                            <span className="text-[11px] text-amber-800">Staff Note • {cm.user_name || cm.user_role || 'Staff'}</span>
                          </>
                        ) : (
                          <>
                            <UserIcon className="w-3 h-3 text-brand-600" />
                            <span className="text-[11px] text-brand-800">Citizen • {cm.user_name || 'Resident'}</span>
                          </>
                        )}
                      </div>
                      <span className="text-[10px] text-slate-400">
                        {new Date(cm.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="whitespace-pre-line leading-relaxed">{cm.content}</p>
                  </div>
                ))
              )}
            </div>

            <div className="pt-2 border-t border-slate-100 flex gap-2">
              <input
                type="text"
                value={internalNoteContent}
                onChange={(e) => setInternalNoteContent(e.target.value)}
                placeholder="Write private internal staff note..."
                className="flex-1 p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleAddInternalNote();
                  }
                }}
              />
              <Button
                variant="primary"
                size="sm"
                isLoading={noteLoading}
                onClick={handleAddInternalNote}
                icon={<Lock className="w-3.5 h-3.5" />}
              >
                Save Private Note
              </Button>
            </div>
          </div>
        </div>

        {/* Right Column: Evidence & Timeline */}
        <div className="space-y-6">
          {/* Photographic Evidence */}
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Attached Evidence</h3>
            {complaint.attachments && complaint.attachments.length > 0 ? (
              <div className="space-y-3">
                {complaint.attachments.map((att) => {
                  const secureUrl = att.id && token 
                    ? resolveBackendUrl(`/api/v1/evidence/${att.id}?token=${token}`)
                    : resolveBackendUrl(att.file_path);
                  return (
                    <div key={att.id} className="border border-slate-200 rounded-2xl overflow-hidden bg-slate-50">
                      <img 
                        src={secureUrl} 
                        alt="Evidence" 
                        onError={(e) => {
                          e.currentTarget.src = resolveBackendUrl(att.file_path);
                        }}
                        className="w-full h-44 object-cover" 
                      />
                      <div className="p-2 text-[10px] text-slate-500 flex justify-between items-center">
                        <span className={`font-semibold px-2 py-0.5 rounded-full ${
                          att.attachment_type === 'RESOLUTION' ? 'bg-emerald-100 text-emerald-800' :
                          att.attachment_type === 'BEFORE' ? 'bg-slate-200 text-slate-800' :
                          'bg-brand-100 text-brand-800'
                        }`}>
                          {att.attachment_type}
                        </span>
                        <span>{(att.file_size / (1024 * 1024)).toFixed(2)} MB</span>
                      </div>
                      {att.description && (
                        <div className="px-2 pb-2 text-[11px] text-slate-600">
                          {att.description}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-slate-400 text-center py-6">No photographs attached.</p>
            )}
          </div>

          {/* Immutable Timeline */}
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Audit & Status History</h3>
            <div className="space-y-4 relative before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
              {complaint.status_history?.map((h) => (
                <div key={h.id} className="relative pl-6 space-y-0.5 text-xs">
                  <div className="absolute left-0 top-1 w-4 h-4 rounded-full bg-brand-600 border-2 border-white shadow-xs" />
                  <div className="font-bold text-slate-800">{h.to_status.replace(/_/g, ' ')}</div>
                  {h.change_reason && <p className="text-slate-500 text-[11px]">{h.change_reason}</p>}
                  <span className="text-[10px] text-slate-400 block">{new Date(h.created_at).toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* MODAL 1: VERIFY & SET PRIORITY */}
      {showVerifyModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">Verify Complaint</h4>
                <p className="text-xs text-slate-500">Confirm legitimacy and assign verified SLA priority.</p>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Confirmed Priority *</label>
                <select
                  value={verifyPriority}
                  onChange={(e) => setVerifyPriority(e.target.value)}
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800"
                >
                  <option value="P1">P1 • Critical Hazard (12h SLA)</option>
                  <option value="P2">P2 • High Urgency (24h SLA)</option>
                  <option value="P3">P3 • Normal (72h SLA)</option>
                  <option value="P4">P4 • Low Maintenance (168h SLA)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Verification Notes</label>
                <textarea
                  rows={3}
                  value={verifyNotes}
                  onChange={(e) => setVerifyNotes(e.target.value)}
                  placeholder="e.g. Field inspection confirmed 4-foot cave-in. Marked P1 due to school zone proximity."
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowVerifyModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                className="bg-emerald-600 hover:bg-emerald-700"
                isLoading={actionLoading}
                onClick={handleVerifyComplaint}
              >
                Confirm Verification
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: REQUEST MORE CITIZEN INFO */}
      {showRequestInfoModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-sky-50 text-sky-600 flex items-center justify-center">
                <HelpCircle className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">Request Citizen Information</h4>
                <p className="text-xs text-slate-500">Ask the citizen to clarify details before work proceeds.</p>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Questions / Clarification Needed *</label>
              <textarea
                required
                rows={4}
                value={requestInfoText}
                onChange={(e) => setRequestInfoText(e.target.value)}
                placeholder="e.g. Could you confirm which side of the cross-street has the open pipe? A photo of the nearest house number would assist our crew."
                className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowRequestInfoModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                className="bg-sky-600 hover:bg-sky-700 text-white"
                isLoading={actionLoading}
                onClick={handleRequestInfo}
              >
                Send Request to Citizen
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: REJECT COMPLAINT */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center">
                <XCircle className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">Reject Complaint</h4>
                <p className="text-xs text-slate-500">Document why this report cannot be resolved by the municipality.</p>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Mandatory Rejection Reason *</label>
              <textarea
                required
                rows={4}
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="e.g. Issue located inside private gated society, outside municipal jurisdiction. Transferred to residential association."
                className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-rose-500"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowRejectModal(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                isLoading={actionLoading}
                onClick={handleRejectComplaint}
              >
                Reject Complaint
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 4: FLAG FOR INVESTIGATION */}
      {showFlagModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center">
                <AlertOctagon className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">Flag for Investigation</h4>
                <p className="text-xs text-slate-500">Halt standard dispatch for security, legal, or fraud inquiry.</p>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Investigation Justification *</label>
              <textarea
                required
                rows={4}
                value={flagReason}
                onChange={(e) => setFlagReason(e.target.value)}
                placeholder="e.g. Serial vandalism detected at this transformer box; forwarded to municipal security division for CCTV review."
                className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-amber-500"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowFlagModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                className="bg-amber-600 hover:bg-amber-700 text-white"
                isLoading={actionLoading}
                onClick={handleFlagInvestigation}
              >
                Flag for Investigation
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 5: REVIEW EVIDENCE */}
      {showReviewEvidenceModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center ${reviewIsApproved ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                {reviewIsApproved ? <CheckCircle2 className="w-6 h-6" /> : <RotateCcw className="w-6 h-6" />}
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">
                  {reviewIsApproved ? 'Approve Field Repair Evidence' : 'Return Work for Rework'}
                </h4>
                <p className="text-xs text-slate-500">
                  {reviewIsApproved 
                    ? 'Moves ticket to citizen confirmation phase.' 
                    : 'Sends ticket back to field crew with rework instructions.'}
                </p>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Review Notes & Directives</label>
              <textarea
                rows={4}
                value={reviewNotes}
                onChange={(e) => setReviewNotes(e.target.value)}
                placeholder={reviewIsApproved ? 'e.g. Photographic evidence verified; road resurfacing meets code.' : 'e.g. Patch is uneven; asphalt debris needs to be cleared from pedestrian pathway.'}
                className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowReviewEvidenceModal(false)}>
                Cancel
              </Button>
              <Button
                variant={reviewIsApproved ? 'primary' : 'danger'}
                size="sm"
                className={reviewIsApproved ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : undefined}
                isLoading={actionLoading}
                onClick={handleReviewEvidence}
              >
                {reviewIsApproved ? 'Approve & Notify Citizen' : 'Confirm Return for Rework'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 6: OVERRIDE AI */}
      {showOverrideModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-ai-50 text-ai-600 flex items-center justify-center">
                <Sparkles className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-bold text-slate-900">Override AI Assessment</h4>
                <p className="text-xs text-slate-500">Recorded with an immutable administrative audit log.</p>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">New Category</label>
                <select
                  value={overrideCategory}
                  onChange={(e) => setOverrideCategory(e.target.value)}
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800"
                >
                  <option value="">(Keep Current: {complaint.category})</option>
                  <option value="ROADS">ROADS</option>
                  <option value="STREETLIGHTS">STREETLIGHTS</option>
                  <option value="GARBAGE">GARBAGE</option>
                  <option value="DRAINAGE">DRAINAGE</option>
                  <option value="WATER_SUPPLY">WATER_SUPPLY</option>
                  <option value="FOOTPATHS">FOOTPATHS</option>
                  <option value="TREES_HAZARDS">TREES_HAZARDS</option>
                  <option value="SANITATION">SANITATION</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">New Priority</label>
                <select
                  value={overridePriority}
                  onChange={(e) => setOverridePriority(e.target.value)}
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800"
                >
                  <option value="">(Keep Current: {complaint.priority})</option>
                  <option value="P1">P1 Critical (12h)</option>
                  <option value="P2">P2 High (24h)</option>
                  <option value="P3">P3 Normal (72h)</option>
                  <option value="P4">P4 Low (168h)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Mandatory Override Reason *</label>
                <textarea
                  required
                  rows={3}
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder="Explain why the automated classification is being corrected..."
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-ai-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowOverrideModal(false)}>
                Cancel
              </Button>
              <Button
                variant="ai"
                size="sm"
                isLoading={actionLoading}
                onClick={handleOverrideAI}
              >
                Save Override Audit
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
