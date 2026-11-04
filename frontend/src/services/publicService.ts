import { apiRequest } from './api';
import { PublicImpactData, NotificationItem } from '../types';

export const publicService = {
  async getImpactDashboard(): Promise<PublicImpactData> {
    return apiRequest<PublicImpactData>('/public/impact');
  },
};

export const notificationService = {
  async getNotifications(): Promise<NotificationItem[]> {
    return apiRequest<NotificationItem[]>('/notifications');
  },

  async markAsRead(id: string): Promise<NotificationItem> {
    return apiRequest<NotificationItem>(`/notifications/${id}/read`, {
      method: 'PATCH',
    });
  },

  async markAllAsRead(): Promise<void> {
    await apiRequest('/notifications/read-all', {
      method: 'POST',
    });
  },
};

