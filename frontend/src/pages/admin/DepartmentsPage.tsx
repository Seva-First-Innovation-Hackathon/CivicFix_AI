import React, { useEffect, useState } from 'react';
import { Building2, Plus, Users, Wrench, FileText } from 'lucide-react';
import { adminService } from '../../services/adminService';
import { Department } from '../../types';
import { Button } from '../../components/common/Button';
import { useToast } from '../../context/ToastContext';

export const DepartmentsPage: React.FC = () => {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [name, setName] = useState<string>('');
  const [code, setCode] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [addLoading, setAddLoading] = useState<boolean>(false);

  const { success, error: toastError } = useToast();

  const loadDepartments = () => {
    setLoading(true);
    adminService.getDepartments()
      .then(setDepartments)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadDepartments();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !code.trim()) return;

    setAddLoading(true);
    try {
      await adminService.createDepartment({
        name,
        code: code.toUpperCase(),
        description: description || undefined,
      });
      success('Department Created', `${name} is now active.`);
      setShowAddModal(false);
      setName('');
      setCode('');
      setDescription('');
      loadDepartments();
    } catch (err: any) {
      toastError('Creation Failed', err.message);
    } finally {
      setAddLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-brand-600">Municipal Structure</span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Department Management</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Configure municipal departments, service boundaries, and field crew assignments.
          </p>
        </div>
        <Button
          variant="primary"
          size="md"
          onClick={() => setShowAddModal(true)}
          icon={<Plus className="w-4 h-4" />}
        >
          Add New Department
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {loading ? (
          <div className="col-span-full p-12 bg-white rounded-3xl border border-slate-200 text-center text-xs text-slate-400">
            Loading departments...
          </div>
        ) : (
          departments.map((dept) => (
            <div key={dept.id} className="bg-white p-6 rounded-3xl border border-slate-200 shadow-xs space-y-4">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-[10px] font-mono font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded">
                    {dept.code}
                  </span>
                  <h3 className="text-base font-bold text-slate-900 mt-1">{dept.name}</h3>
                </div>
                <div className="w-8 h-8 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center">
                  <Building2 className="w-4 h-4" />
                </div>
              </div>

              <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">
                {dept.description || 'General public civil infrastructure maintenance.'}
              </p>

              <div className="pt-3 border-t border-slate-100 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="p-2 bg-slate-50 rounded-xl">
                  <span className="text-[10px] text-slate-400 block">Members</span>
                  <span className="font-bold text-slate-800">{dept.member_count}</span>
                </div>
                <div className="p-2 bg-slate-50 rounded-xl">
                  <span className="text-[10px] text-slate-400 block">Crews</span>
                  <span className="font-bold text-slate-800">{dept.crew_count}</span>
                </div>
                <div className="p-2 bg-slate-50 rounded-xl">
                  <span className="text-[10px] text-slate-400 block">Open Issues</span>
                  <span className="font-bold text-brand-700">{dept.open_complaints_count}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <h4 className="text-base font-bold text-slate-900">Add Municipal Department</h4>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Department Name *</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Drainage & Flood Management"
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Department Code * (Unique)</label>
                <input
                  type="text"
                  required
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="e.g. DRAINAGE"
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs font-mono uppercase focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Description</label>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe operational responsibilities..."
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" size="sm" type="button" onClick={() => setShowAddModal(false)}>
                  Cancel
                </Button>
                <Button variant="primary" size="sm" type="submit" isLoading={addLoading}>
                  Create Department
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

