import React, { useEffect, useState } from 'react';
import { Users, UserPlus, ShieldAlert, CheckCircle2, XCircle, Building2, Truck } from 'lucide-react';
import { adminService } from '../../services/adminService';
import { User, Department } from '../../types';
import { Button } from '../../components/common/Button';
import { useToast } from '../../context/ToastContext';

export const UsersManagementPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [roleFilter, setRoleFilter] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);

  // New staff modal
  const [showModal, setShowModal] = useState<boolean>(false);
  const [fullName, setFullName] = useState<string>('');
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [role, setRole] = useState<'MUNICIPAL_MEMBER' | 'FIELD_CREW'>('MUNICIPAL_MEMBER');
  const [departmentId, setDepartmentId] = useState<string>('');
  const [designation, setDesignation] = useState<string>('Assistant Engineer');
  const [vehicleNumber, setVehicleNumber] = useState<string>('');
  const [createLoading, setCreateLoading] = useState<boolean>(false);

  const { success, error: toastError } = useToast();

  const loadData = () => {
    setLoading(true);
    Promise.all([
      adminService.listUsers(roleFilter || undefined),
      adminService.getDepartments()
    ])
      .then(([userData, deptData]) => {
        setUsers(userData);
        setDepartments(deptData);
        if (deptData.length > 0 && !departmentId) {
          setDepartmentId(deptData[0].id);
        }
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, [roleFilter]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !fullName.trim() || !password.trim() || !departmentId) {
      toastError('Validation', 'Please fill in all mandatory fields.');
      return;
    }

    setCreateLoading(true);
    try {
      await adminService.createStaffUser({
        full_name: fullName,
        email,
        password,
        role,
        department_id: departmentId,
        designation: role === 'MUNICIPAL_MEMBER' ? designation : undefined,
        vehicle_number: role === 'FIELD_CREW' ? vehicleNumber : undefined,
      });

      success('Account Provisioned', `${fullName} added to ${role.replace('_', ' ')}.`);
      setShowModal(false);
      setFullName('');
      setEmail('');
      setPassword('');
      setVehicleNumber('');
      loadData();
    } catch (err: any) {
      toastError('Creation Failed', err.message);
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDeactivate = async (userId: string, emailStr: string) => {
    if (!window.confirm(`Deactivate access for ${emailStr}?`)) return;
    try {
      await adminService.deactivateUser(userId);
      success('User Deactivated', `Access revoked for ${emailStr}`);
      loadData();
    } catch (err: any) {
      toastError('Deactivation Failed', err.message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-ai-600">Access Governance</span>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Staff & Field Crew Administration</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Government Admin portal to provision authorized municipal staff and field crews.
          </p>
        </div>
        <Button
          variant="primary"
          size="md"
          onClick={() => setShowModal(true)}
          icon={<UserPlus className="w-4 h-4" />}
        >
          Provision Staff Account
        </Button>
      </div>

      {/* Role Filter */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-slate-500">Filter Role:</span>
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="px-3 py-1.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-700"
          >
            <option value="">All Account Types</option>
            <option value="GOVERNMENT_ADMIN">Government Admin</option>
            <option value="MUNICIPAL_MEMBER">Municipal Members</option>
            <option value="FIELD_CREW">Field Crews</option>
            <option value="CITIZEN">Citizens</option>
          </select>
        </div>
        <span className="text-xs text-slate-400 font-mono">{users.length} accounts total</span>
      </div>

      {/* Users Table */}
      <div className="bg-white rounded-3xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold">
              <tr>
                <th className="px-5 py-3">User & Email</th>
                <th className="px-5 py-3">Role</th>
                <th className="px-5 py-3">Department Context</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Created</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-slate-400">
                    Loading accounts...
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-5 py-3.5">
                      <span className="font-bold text-slate-900 block">{u.full_name}</span>
                      <span className="text-[11px] text-slate-500 font-mono block">{u.email}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                        u.role === 'GOVERNMENT_ADMIN'
                          ? 'bg-purple-100 text-purple-800 border border-purple-200'
                          : u.role === 'MUNICIPAL_MEMBER'
                          ? 'bg-blue-100 text-blue-800'
                          : u.role === 'FIELD_CREW'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-slate-100 text-slate-700'
                      }`}>
                        {u.role.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-600">
                      {u.department_membership?.designation || u.crew_profile?.vehicle_number || 'General Citizen'}
                    </td>
                    <td className="px-5 py-3.5">
                      {u.is_active ? (
                        <span className="inline-flex items-center gap-1 text-emerald-600 font-semibold text-[11px]">
                          <CheckCircle2 className="w-3.5 h-3.5" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-rose-600 font-semibold text-[11px]">
                          <XCircle className="w-3.5 h-3.5" /> Deactivated
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-slate-400 font-mono text-[11px]">
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {u.role !== 'GOVERNMENT_ADMIN' && u.is_active && (
                        <button
                          onClick={() => handleDeactivate(u.id, u.email)}
                          className="px-2.5 py-1 text-[11px] font-semibold text-rose-600 hover:text-rose-800 hover:bg-rose-50 rounded-lg transition"
                        >
                          Deactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* PROVISION STAFF MODAL */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <h4 className="text-base font-bold text-slate-900">Provision Municipal Staff Account</h4>
            <p className="text-xs text-slate-500">
              Created directly by Government Admin. Public self-registration for staff is forbidden.
            </p>

            <form onSubmit={handleCreateUser} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Full Name *</label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. Suresh Verma"
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Official Municipal Email *</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="suresh@civicfix.gov"
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Temporary Password * (min. 8 chars)</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Staff Role *</label>
                  <select
                    value={role}
                    onChange={(e) => setRole(e.target.value as any)}
                    className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800"
                  >
                    <option value="MUNICIPAL_MEMBER">Municipal Member</option>
                    <option value="FIELD_CREW">Field Crew</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Department *</label>
                  <select
                    value={departmentId}
                    onChange={(e) => setDepartmentId(e.target.value)}
                    className="w-full p-2.5 border border-slate-300 rounded-xl text-xs bg-white text-slate-800"
                  >
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              {role === 'MUNICIPAL_MEMBER' ? (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Designation</label>
                  <input
                    type="text"
                    value={designation}
                    onChange={(e) => setDesignation(e.target.value)}
                    placeholder="e.g. Executive Engineer"
                    className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              ) : (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Vehicle / Unit Identifier</label>
                  <input
                    type="text"
                    value={vehicleNumber}
                    onChange={(e) => setVehicleNumber(e.target.value)}
                    placeholder="e.g. TS-09-EA-1122"
                    className="w-full p-2.5 border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              )}

              <div className="flex justify-end gap-2 pt-3">
                <Button variant="outline" size="sm" type="button" onClick={() => setShowModal(false)}>
                  Cancel
                </Button>
                <Button variant="primary" size="sm" type="submit" isLoading={createLoading}>
                  Create Staff Account
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

