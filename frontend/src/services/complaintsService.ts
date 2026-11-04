import { apiRequest } from './api';
import { Complaint, Attachment, StatusHistory, ComplaintComment } from '../types';

export interface CreateComplaintInput {
  title: string;
  description: string;
  category: string;
  subcategory?: string;
  latitude: number;
  longitude: number;
  address?: string;
  landmark?: string;
}

export const complaintsService = {
  async createComplaint(data: CreateComplaintInput): Promise<Complaint> {
    return apiRequest<Complaint>('/complaints', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async getMyComplaints(params?: { page?: number; page_size?: number; status_filter?: string }): Promise<{
    total: number;
    page: number;
    page_size: number;
    complaints: Complaint[];
  }> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.append('page', String(params.page));
    if (params?.page_size) searchParams.append('page_size', String(params.page_size));
    if (params?.status_filter) searchParams.append('status_filter', params.status_filter);

    const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return apiRequest(`/complaints/my${query}`);
  },

  async getComplaintById(id: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/complaints/${id}`);
  },

  async getComplaintTimeline(id: string): Promise<StatusHistory[]> {
    return apiRequest<StatusHistory[]>(`/complaints/${id}/timeline`);
  },

  async uploadAttachment(complaintId: string, file: File, type: string = 'CITIZEN_ORIGINAL', description?: string): Promise<Attachment> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('attachment_type', type);
    if (description) formData.append('description', description);

    return apiRequest<Attachment>(`/complaints/${complaintId}/attachments`, {
      method: 'POST',
      body: formData,
    });
  },

  async cancelComplaint(complaintId: string, reason: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/complaints/${complaintId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  async clarifyComplaint(complaintId: string, information: string): Promise<Complaint> {
    return apiRequest<Complaint>(`/complaints/${complaintId}/clarify`, {
      method: 'POST',
      body: JSON.stringify({ information }),
    });
  },

  async getComments(complaintId: string): Promise<ComplaintComment[]> {
    return apiRequest<ComplaintComment[]>(`/complaints/${complaintId}/comments`);
  },

  async addComment(complaintId: string, content: string, is_internal: boolean = false): Promise<ComplaintComment> {
    return apiRequest<ComplaintComment>(`/complaints/${complaintId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ content, is_internal }),
    });
  },

  async confirmResolution(complaintId: string, data: {
    is_satisfied: boolean;
    feedback_rating?: number;
    feedback_notes?: string;
  }): Promise<Complaint> {
    return apiRequest<Complaint>(`/complaints/${complaintId}/confirm-resolution`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async reopenComplaint(complaintId: string, data: {
    reopen_reason: string;
    feedback_notes?: string;
  }): Promise<Complaint> {
    return apiRequest<Complaint>(`/complaints/${complaintId}/reopen`, {
      method: 'POST',
      body: JSON.stringify({
        is_satisfied: false,
        reopen_reason: data.reopen_reason,
        feedback_notes: data.feedback_notes,
      }),
    });
  },
};

