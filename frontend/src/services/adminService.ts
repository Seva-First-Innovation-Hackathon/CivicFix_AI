import { apiRequest } from './api';
import { 
  AnalyticsOverview, Complaint, Department, WorkOrder, 
  PotentialDuplicate, User, NotificationItem 
} from '../types';

export const adminService = {
  async getDashboardMetrics(): Promise<AnalyticsOverview> {
    return apiRequest<AnalyticsOverview>('/admin/dashboard');
  },

  async listComplaints(params?: {
    page?: number;
    page_size?: number;
    category?: string;
    status?: string;
    priority?: string;
    department_id?: string;
    search?: string;
  }): Promise<{ total: number; page: number; page_size: number; complaints: Complaint[] }> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.append('page', String(params.page));
    if (params?.page_size) searchParams.append('page_size', String(params.page_size));
    if (params?.category) searchParams.append('category', params.category);
    if (params?.status) searchParams.append('status', params.status);
    if (params?.priority) searchParams.append('priority', params.priority);
    if (params?.department_id) searchParams.append('department_id', params.department_id);
    if (params?.search) searchParams.append('search', params.search);

    const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return apiRequest(`/admin/complaints${query}`);
  },

  async getComplaint(id: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}`);
  },

  async updateComplaintStatus(id: string, status: string, reason?: string, notes?: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, reason, notes }),
    });
  },

  async verifyComplaint(id: string, priority: string, notes?: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}/verify`, {
      method: 'POST',
      body: JSON.stringify({ priority, verification_notes: notes }),
    });
  },

  async requestMoreInfo(id: string, information: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}/request-info`, {
      method: 'POST',
      body: JSON.stringify({ information }),
    });
  },

  async rejectComplaint(id: string, reason: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  async flagInvestigation(id: string, reason: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}/flag-investigation`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  async reviewEvidence(id: string, isApproved: boolean, notes: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}/review-evidence`, {
      method: 'POST',
      body: JSON.stringify({ is_approved: isApproved, notes }),
    });
  },

  async addInternalNote(id: string, content: string): Promise<any> {
    return apiRequest(`/admin/complaints/${id}/internal-note`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  },

  async acceptWorkOrder(workOrderId: string): Promise<WorkOrder> {
    return apiRequest<WorkOrder>(`/admin/work-orders/${workOrderId}/accept`, {
      method: 'POST',
    });
  },

  async submitWorkOrderEvidence(workOrderId: string, completionNotes: string, materialsUsed?: string): Promise<WorkOrder> {
    return apiRequest<WorkOrder>(`/admin/work-orders/${workOrderId}/submit-evidence`, {
      method: 'POST',
      body: JSON.stringify({ completion_notes: completionNotes, materials_used: materialsUsed }),
    });
  },

  async assignComplaint(id: string, departmentId: string, priority?: string, notes?: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}/assign`, {
      method: 'POST',
      body: JSON.stringify({ department_id: departmentId, priority, notes }),
    });
  },

  async reviewAiAssessment(id: string, overrideReason: string, category?: string, priority?: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}/review-ai`, {
      method: 'POST',
      body: JSON.stringify({ override_reason: overrideReason, category, priority }),
    });
  },

  async submitResolution(id: string, resolutionNotes: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/admin/complaints/${id}/resolution`, {
      method: 'POST',
      body: JSON.stringify({ resolution_notes: resolutionNotes }),
    });
  },

  async getMapComplaints(params?: { category?: string; status?: string; priority?: string }): Promise<{
    complaints: Array<{
      id: string;
      reference_number: string;
      title: string;
      category: string;
      status: string;
      priority: string;
      latitude: number;
      longitude: number;
      address?: string;
      created_at: string;
      has_attachments: boolean;
      first_image?: string;
    }>;
  }> {
    const searchParams = new URLSearchParams();
    if (params?.category) searchParams.append('category', params.category);
    if (params?.status) searchParams.append('status', params.status);
    if (params?.priority) searchParams.append('priority', params.priority);

    const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return apiRequest(`/admin/map/complaints${query}`);
  },

  async getDepartments(): Promise<Department[]> {
    return apiRequest<Department[]>('/admin/departments');
  },

  async createDepartment(data: { name: string; code: string; description?: string }): Promise<Department> {
    return apiRequest<Department>('/admin/departments', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async getWorkOrders(status?: string): Promise<WorkOrder[]> {
    const query = status ? `?status=${status}` : '';
    return apiRequest<WorkOrder[]>(`/admin/work-orders${query}`);
  },

  async createWorkOrder(data: {
    complaint_id: string;
    department_id: string;
    crew_id: string;
    title: string;
    instructions: string;
  }): Promise<WorkOrder> {
    return apiRequest<WorkOrder>('/admin/work-orders', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async updateWorkOrderStatus(workOrderId: string, status: string, note: string, blockerReason?: string): Promise<WorkOrder> {
    return apiRequest<WorkOrder>(`/admin/work-orders/${workOrderId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, note, blocker_reason: blockerReason }),
    });
  },

  async getPotentialDuplicates(): Promise<PotentialDuplicate[]> {
    return apiRequest<PotentialDuplicate[]>('/admin/duplicates');
  },

  async reviewDuplicate(duplicateId: string, status: 'CONFIRMED_MERGED' | 'DISMISSED', reviewNotes?: string): Promise<any> {
    return apiRequest(`/admin/duplicates/${duplicateId}/review`, {
      method: 'POST',
      body: JSON.stringify({ status, review_notes: reviewNotes }),
    });
  },

  async listUsers(role?: string): Promise<User[]> {
    const query = role ? `?role=${role}` : '';
    return apiRequest<User[]>(`/admin/users${query}`);
  },

  async createStaffUser(data: {
    email: string;
    password: string;
    full_name: string;
    phone_number?: string;
    role: 'MUNICIPAL_MEMBER' | 'FIELD_CREW';
    department_id: string;
    designation?: string;
    vehicle_number?: string;
  }): Promise<User> {
    return apiRequest<User>('/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async deactivateUser(userId: string): Promise<any> {
    return apiRequest(`/admin/users/${userId}/deactivate`, {
      method: 'POST',
    });
  },

  async getAuditLogs(): Promise<any[]> {
    return apiRequest('/admin/audit-logs');
  },

  getExportCsvUrl(): string {
    return '/api/v1/admin/analytics/export-csv';
  },
};

