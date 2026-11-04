const rawApiUrl = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL) as string | undefined;
const envApiUrl = rawApiUrl?.trim();
const API_BASE = envApiUrl ? `${envApiUrl.replace(/\/$/, '')}/api/v1` : '/api/v1';

export function resolveBackendUrl(path: string): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('blob:') || path.startsWith('data:')) {
    return path;
  }
  const baseUrl = envApiUrl ? envApiUrl.replace(/\/$/, '') : '';
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${baseUrl}${cleanPath}`;
}

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = 'ApiError';
  }
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = localStorage.getItem('civicfix_token');
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };

  // Only add Content-Type: application/json if body is not FormData
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `Request failed with status ${response.status}`;
    let data;
    try {
      data = await response.json();
      if (data && data.detail) {
        errorDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // not JSON
    }

    if (response.status === 401) {
      // Token expired or invalid
      localStorage.removeItem('civicfix_token');
      localStorage.removeItem('civicfix_user');
      if (!window.location.pathname.includes('/login')) {
        // window.location.href = '/login';
      }
    }

    throw new ApiError(response.status, errorDetail, data);
  }

  // Handle empty or text responses
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }
  return response.text() as unknown as T;
}

