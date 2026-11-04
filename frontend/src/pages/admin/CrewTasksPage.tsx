import React, { useEffect, useState } from 'react';
import { 
  Truck, CheckCircle2, Clock, AlertTriangle, ArrowRight, 
  Camera, Check, ShieldAlert, MapPin, Compass, List, Map as MapIcon,
  Navigation
} from 'lucide-react';
import { adminService } from '../../services/adminService';
import { complaintsService } from '../../services/complaintsService';
import { WorkOrder } from '../../types';
import { Button } from '../../components/common/Button';
import { FileUpload } from '../../components/common/FileUpload';
import { useToast } from '../../context/ToastContext';
import { CivicFixMap } from '../../components/common/CivicFixMap';

export const CrewTasksPage: React.FC = () => {
  const [tasks, setTasks] = useState<WorkOrder[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedTask, setSelectedTask] = useState<WorkOrder | null>(null);
  const [updateStatus, setUpdateStatus] = useState<string>('IN_PROGRESS');
  const [updateNote, setUpdateNote] = useState<string>('');
  const [blockerReason, setBlockerReason] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [acceptLoading, setAcceptLoading] = useState<boolean>(false);
  const [viewMode, setViewMode] = useState<'list' | 'map'>('list');

  const { success, error: toastError } = useToast();

  const loadTasks = () => {
    setLoading(true);
    adminService.getWorkOrders()
      .then(setTasks)
      .catch((err) => toastError('Failed to load tasks', err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadTasks();
  }, []);

  const handleAcceptTask = async (task: WorkOrder) => {
    setAcceptLoading(true);
    try {
      await adminService.acceptWorkOrder(task.id);
      success('Work Order Accepted', `Task #${task.complaint_reference} accepted and marked IN_PROGRESS.`);
      loadTasks();
      if (selectedTask?.id === task.id) {
        setSelectedTask({ ...task, status: 'ACCEPTED' as any });
      }
    } catch (err: any) {
      toastError('Accept Failed', err.message);
    } finally {
      setAcceptLoading(false);
    }
  };

  const handleUpdateTask = async () => {
    if (!selectedTask) return;
    if (!updateNote.trim()) {
      toastError('Validation', 'Please provide a brief progress note.');
      return;
    }

    setActionLoading(true);
    try {
      // 1. If photo was attached, upload it as resolution/progress evidence
      if (selectedFile) {
        await complaintsService.uploadAttachment(
          selectedTask.complaint_id, 
          selectedFile, 
          updateStatus === 'COMPLETED' ? 'RESOLUTION' : 'PROGRESS',
          updateNote
        );
      }

      // 2. If completing, submit resolution evidence moving complaint to WORK_COMPLETED_PENDING_REVIEW
      if (updateStatus === 'COMPLETED') {
        await adminService.submitWorkOrderEvidence(selectedTask.id, updateNote, blockerReason || undefined);
        success('Repairs Submitted', 'Work order completed. Sent to Municipal Staff for evidence review.');
      } else {
        // 3. Otherwise update normal progress or blocker
        await adminService.updateWorkOrderStatus(
          selectedTask.id,
          updateStatus,
          updateNote,
          blockerReason || undefined
        );
        success('Task Updated', `Status updated to ${updateStatus}`);
      }

      setSelectedTask(null);
      setSelectedFile(null);
      setUpdateNote('');
      setBlockerReason('');
      loadTasks();
    } catch (err: any) {
      toastError('Update Failed', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header with Title and View Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-amber-600">Field Operations</span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">My Assigned Field Orders</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Review on-site task details, accept dispatched work orders, update repair progress, and submit completion evidence.
          </p>
        </div>

        {/* View Mode Toggle */}
        <div className="flex items-center p-1 bg-slate-100 rounded-xl border border-slate-200 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => setViewMode('list')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
              viewMode === 'list'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <List className="w-3.5 h-3.5" />
            <span>List View ({tasks.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode('map')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
              viewMode === 'map'
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <MapIcon className="w-3.5 h-3.5 text-brand-400" />
            <span>Field Map (Interactive)</span>
          </button>
        </div>
      </div>

      {viewMode === 'map' ? (
        /* ================= MAP VIEW ================= */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <div className="lg:col-span-7 space-y-3">
            <div className="bg-slate-900 p-3 sm:p-4 rounded-3xl border border-slate-800 shadow-md">
              <div className="flex items-center justify-between pb-3 mb-2 border-b border-slate-800 text-slate-300 text-xs">
                <span className="flex items-center gap-2 font-bold text-white">
                  <MapPin className="w-4 h-4 text-brand-400" />
                  Assigned Crew Task Dispatch Map
                </span>
                <span className="text-[11px] text-slate-400">
                  {tasks.filter((t) => t.complaint_latitude && t.complaint_longitude).length} geocoded locations
                </span>
              </div>

              <CivicFixMap
                mode="crew"
                workOrders={tasks}
                height="560px"
                onSelectWorkOrder={(id) => {
                  const task = tasks.find((t) => t.id === id);
                  if (task) {
                    setSelectedTask(task);
                    setUpdateStatus(task.status === 'ASSIGNED' || task.status === 'ACCEPTED' ? 'IN_PROGRESS' : task.status);
                    setUpdateNote('');
                  }
                }}
              />
            </div>
          </div>

          <div className="lg:col-span-5">
            {selectedTask ? (
              <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4 sticky top-24">
                <div className="flex justify-between items-start">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Selected Work Order</span>
                    <h3 className="text-base font-bold text-slate-900">{selectedTask.title}</h3>
                    <p className="text-xs text-slate-500 mt-0.5">Instructions: {selectedTask.instructions}</p>
                  </div>
                  {selectedTask.status === 'ASSIGNED' && (
                    <Button
                      size="sm"
                      variant="primary"
                      isLoading={acceptLoading}
                      onClick={() => handleAcceptTask(selectedTask)}
                      icon={<Check className="w-3.5 h-3.5" />}
                    >
                      Accept
                    </Button>
                  )}
                </div>

                <div className="p-3 bg-slate-50 rounded-xl text-xs space-y-1.5">
                  <div><strong>Location:</strong> {selectedTask.complaint_address || 'Coordinates'}</div>
                  {selectedTask.complaint_latitude && (
                    <div className="font-mono text-[11px] text-slate-600">
                      GPS: {selectedTask.complaint_latitude.toFixed(5)}, {selectedTask.complaint_longitude?.toFixed(5)}
                    </div>
                  )}

                  {selectedTask.complaint_latitude && selectedTask.complaint_longitude && (
                    <div className="pt-1">
                      <a
                        href={`https://www.google.com/maps/dir/?api=1&destination=${selectedTask.complaint_latitude},${selectedTask.complaint_longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold text-[11px] transition"
                      >
                        <Compass className="w-3.5 h-3.5" />
                        Start GPS Navigation (Google Maps) &rarr;
                      </a>
                    </div>
                  )}
                </div>

                <div className="space-y-3 pt-2">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Update Status</label>
                    <select
                      value={updateStatus}
                      onChange={(e) => setUpdateStatus(e.target.value)}
                      className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800 focus:ring-2 focus:ring-brand-500"
                    >
                      <option value="IN_PROGRESS">In Progress (Crew on site / Ongoing)</option>
                      <option value="BLOCKED">Blocked (Material shortage / Obstruction)</option>
                      <option value="COMPLETED">Completed (Repairs finished — Ready for review)</option>
                    </select>
                  </div>

                  {updateStatus === 'BLOCKED' && (
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">Blocker / Obstacle Reason *</label>
                      <input
                        type="text"
                        value={blockerReason}
                        onChange={(e) => setBlockerReason(e.target.value)}
                        placeholder="e.g. Traffic diversion permit required, high voltage line risk"
                        className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-rose-500"
                      />
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      {updateStatus === 'COMPLETED' ? 'Completion Notes & Remediation Summary *' : 'Progress Note *'}
                    </label>
                    <textarea
                      rows={3}
                      value={updateNote}
                      onChange={(e) => setUpdateNote(e.target.value)}
                      placeholder={
                        updateStatus === 'COMPLETED' 
                          ? 'Describe repair completed, materials utilized, and site clearance...' 
                          : 'Describe current progress, team status, or estimated time...'
                      }
                      className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                    />
                  </div>

                  {/* Evidence Photo Upload */}
                  <FileUpload
                    selectedFile={selectedFile}
                    onFileSelect={setSelectedFile}
                    label={updateStatus === 'COMPLETED' ? 'Attach Completion Evidence Photo (Mandatory for Review)' : 'Attach Progress Photo (Optional)'}
                  />

                  <Button
                    variant="primary"
                    size="md"
                    className="w-full justify-center"
                    isLoading={actionLoading}
                    onClick={handleUpdateTask}
                    icon={<CheckCircle2 className="w-4 h-4" />}
                  >
                    {updateStatus === 'COMPLETED' ? 'Submit Repairs for Municipal Review' : 'Save Field Progress'}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="bg-white p-12 rounded-3xl border border-slate-200 text-center text-xs text-slate-400">
                Click any defect marker on the dark map and hit &quot;Select Task&quot; to inspect details or submit completion photos.
              </div>
            )}
          </div>
        </div>
      ) : (
        /* ================= LIST VIEW ================= */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Left Column: Tasks List */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Active Work Orders</h3>
            {loading ? (
              <div className="p-8 bg-white rounded-2xl border border-slate-200 text-center text-xs text-slate-400">
                Loading field assignments...
              </div>
            ) : tasks.length === 0 ? (
              <div className="p-8 bg-white rounded-2xl border border-slate-200 text-center text-xs text-slate-400">
                No active work orders assigned to your crew.
              </div>
            ) : (
              tasks.map((task) => (
                <div
                  key={task.id}
                  onClick={() => {
                    setSelectedTask(task);
                    setUpdateStatus(task.status === 'ASSIGNED' || task.status === 'ACCEPTED' ? 'IN_PROGRESS' : task.status);
                    setUpdateNote('');
                  }}
                  className={`p-5 rounded-2xl border transition-all cursor-pointer ${
                    selectedTask?.id === task.id
                      ? 'border-brand-500 bg-brand-50/40 shadow-sm ring-2 ring-brand-100'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-xs font-mono font-bold text-brand-700">#{task.complaint_reference}</span>
                    <span className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full ${
                      task.status === 'COMPLETED' ? 'bg-emerald-100 text-emerald-800' :
                      task.status === 'BLOCKED' ? 'bg-rose-100 text-rose-800' :
                      task.status === 'IN_PROGRESS' || task.status === 'ACCEPTED' ? 'bg-amber-100 text-amber-800' :
                      'bg-slate-100 text-slate-700'
                    }`}>
                      {task.status}
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-slate-900">{task.title}</h4>
                  <p className="text-xs text-slate-500 mt-1 line-clamp-2">{task.instructions}</p>
                  
                  <div className="mt-2.5 flex items-center justify-between gap-2 flex-wrap">
                    {task.complaint_address ? (
                      <p className="text-[11px] text-slate-400 flex items-center gap-1">
                        <span>📍</span>
                        <span className="truncate max-w-[200px]">{task.complaint_address}</span>
                      </p>
                    ) : <span />}

                    {task.complaint_latitude && task.complaint_longitude && (
                      <a
                        href={`https://www.google.com/maps/dir/?api=1&destination=${task.complaint_latitude},${task.complaint_longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 px-2 py-1 rounded-md transition"
                      >
                        <Compass className="w-3 h-3" />
                        Navigate GPS
                      </a>
                    )}
                  </div>

                  {task.status === 'ASSIGNED' && (
                    <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
                      <span className="text-[11px] text-amber-600 font-medium">New assignment awaiting confirmation</span>
                      <Button
                        size="sm"
                        variant="primary"
                        isLoading={acceptLoading}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleAcceptTask(task);
                        }}
                        icon={<Check className="w-3.5 h-3.5" />}
                      >
                        Accept Assignment
                      </Button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Right Column: Update Panel */}
          <div>
            {selectedTask ? (
              <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4 sticky top-24">
                <div className="flex justify-between items-start">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Selected Work Order</span>
                    <h3 className="text-base font-bold text-slate-900">{selectedTask.title}</h3>
                    <p className="text-xs text-slate-500 mt-0.5">Instructions: {selectedTask.instructions}</p>
                  </div>
                  {selectedTask.status === 'ASSIGNED' && (
                    <Button
                      size="sm"
                      variant="primary"
                      isLoading={acceptLoading}
                      onClick={() => handleAcceptTask(selectedTask)}
                      icon={<Check className="w-3.5 h-3.5" />}
                    >
                      Accept Work Order
                    </Button>
                  )}
                </div>

                <div className="p-3 bg-slate-50 rounded-xl text-xs space-y-1.5">
                  <div><strong>Location:</strong> {selectedTask.complaint_address || 'Coordinates'}</div>
                  {selectedTask.complaint_latitude && (
                    <div className="font-mono text-[11px] text-slate-600">
                      GPS: {selectedTask.complaint_latitude.toFixed(5)}, {selectedTask.complaint_longitude?.toFixed(5)}
                    </div>
                  )}

                  {selectedTask.complaint_latitude && selectedTask.complaint_longitude && (
                    <div className="pt-1">
                      <a
                        href={`https://www.google.com/maps/dir/?api=1&destination=${selectedTask.complaint_latitude},${selectedTask.complaint_longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold text-[11px] transition"
                      >
                        <Compass className="w-3.5 h-3.5" />
                        Start GPS Navigation (Google Maps) &rarr;
                      </a>
                    </div>
                  )}
                </div>

                <div className="space-y-3 pt-2">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Update Status</label>
                    <select
                      value={updateStatus}
                      onChange={(e) => setUpdateStatus(e.target.value)}
                      className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800 focus:ring-2 focus:ring-brand-500"
                    >
                      <option value="IN_PROGRESS">In Progress (Crew on site / Ongoing)</option>
                      <option value="BLOCKED">Blocked (Material shortage / Obstruction)</option>
                      <option value="COMPLETED">Completed (Repairs finished — Ready for review)</option>
                    </select>
                  </div>

                  {updateStatus === 'BLOCKED' && (
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">Blocker / Obstacle Reason *</label>
                      <input
                        type="text"
                        value={blockerReason}
                        onChange={(e) => setBlockerReason(e.target.value)}
                        placeholder="e.g. Traffic diversion permit required, high voltage line risk"
                        className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-rose-500"
                      />
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      {updateStatus === 'COMPLETED' ? 'Completion Notes & Remediation Summary *' : 'Progress Note *'}
                    </label>
                    <textarea
                      rows={3}
                      value={updateNote}
                      onChange={(e) => setUpdateNote(e.target.value)}
                      placeholder={
                        updateStatus === 'COMPLETED' 
                          ? 'Describe repair completed, materials utilized, and site clearance...' 
                          : 'Describe current progress, team status, or estimated time...'
                      }
                      className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                    />
                  </div>

                  {/* Evidence Photo Upload */}
                  <FileUpload
                    selectedFile={selectedFile}
                    onFileSelect={setSelectedFile}
                    label={updateStatus === 'COMPLETED' ? 'Attach Completion Evidence Photo (Mandatory for Review)' : 'Attach Progress Photo (Optional)'}
                  />

                  <Button
                    variant="primary"
                    size="md"
                    className="w-full justify-center"
                    isLoading={actionLoading}
                    onClick={handleUpdateTask}
                    icon={<CheckCircle2 className="w-4 h-4" />}
                  >
                    {updateStatus === 'COMPLETED' ? 'Submit Repairs for Municipal Review' : 'Save Field Progress'}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="bg-white p-12 rounded-3xl border border-slate-200 text-center text-xs text-slate-400">
                Select a work order from the left to view instructions, update progress, or submit completion photos.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
