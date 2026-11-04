import { apiRequest } from './api';
import { AuthResponse, User } from '../types';

export const authService = {
  async register(data: {
    email: string;
    password: string;
    full_name: string;
    phone_number?: string;
    preferred_language?: string;
  }): Promise<AuthResponse> {
    return apiRequest<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async login(credentials: { email: string; password: string }): Promise<AuthResponse> {
    return apiRequest<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });
  },

  async getCurrentUser(): Promise<User> {
    return apiRequest<User>('/auth/me');
  },

  async logout(): Promise<void> {
    try {
      await apiRequest('/auth/logout', { method: 'POST' });
    } finally {
      localStorage.removeItem('civicfix_token');
      localStorage.removeItem('civicfix_refresh_token');
      localStorage.removeItem('civicfix_user');
    }
  },
};

