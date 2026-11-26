const rawApiUrl = (
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  (typeof process !== 'undefined' && (process.env as any)?.BACKEND_URL ? (process.env as any).BACKEND_URL : undefined)
) as string | undefined;
const envApiUrl = rawApiUrl?.trim();
export const API_BASE = envApiUrl ? `${envApiUrl.replace(/\/$/, '')}/api/v1` : '/api/v1';

export const TOKEN_KEY = 'civicfix_token';
export const REFRESH_TOKEN_KEY = 'civicfix_refresh_token';
export const USER_KEY = 'civicfix_user';

const PUBLIC_AUTH_ROUTES = ['/login', '/staff/login', '/register'];
const NON_REFRESHABLE_ENDPOINTS = ['/auth/login', '/auth/register', '/auth/refresh'];

let activeRefreshPromise: Promise<string | null> | null = null;

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

export function clearAuthStorage(): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function dispatchAuthEvent(name: string, detail?: any): void {
  if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }
}

export function redirectToLoginIfNeeded(): void {
  if (typeof window === 'undefined') return;
  const pathname = window.location?.pathname || '/';
  if (PUBLIC_AUTH_ROUTES.some((route) => pathname.startsWith(route))) {
    return;
  }
  const target = pathname.startsWith('/admin') ? '/staff/login' : '/login';
  if (pathname !== target && typeof window.location?.assign === 'function') {
    try {
      window.location.assign(target);
    } catch {
      // Ignore navigation errors in non-browser test runners (e.g., jsdom)
    }
  }
}

/**
 * Performs a single-flight shared refresh request so concurrent 401 responses
 * do not trigger simultaneous refresh token rotation races.
 */
export async function performTokenRefresh(): Promise<string | null> {
  if (typeof localStorage === 'undefined') return null;
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) {
    return null;
  }

  if (!activeRefreshPromise) {
    activeRefreshPromise = (async () => {
      try {
        const resp = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });

        if (!resp.ok) {
          clearAuthStorage();
          dispatchAuthEvent('civicfix:auth-expired');
          return null;
        }

        const data = await resp.json();
        if (!data?.access_token) {
          clearAuthStorage();
          dispatchAuthEvent('civicfix:auth-expired');
          return null;
        }

        localStorage.setItem(TOKEN_KEY, data.access_token);
        if (data.refresh_token) {
          localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
        }
        dispatchAuthEvent('civicfix:token-refreshed', { token: data.access_token });
        return data.access_token as string;
      } catch {
        clearAuthStorage();
        dispatchAuthEvent('civicfix:auth-expired');
        return null;
      } finally {
        activeRefreshPromise = null;
      }
    })();
  }

  return activeRefreshPromise;
}

export function resetRefreshStateForTesting(): void {
  activeRefreshPromise = null;
}

async function executeFetch(endpoint: string, options: RequestInit, tokenOverride?: string | null): Promise<Response> {
  const token = tokenOverride !== undefined ? tokenOverride : localStorage.getItem(TOKEN_KEY);
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };

  if (options.body !== undefined && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  } else {
    delete headers['Authorization'];
  }

  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  return fetch(url, {
    ...options,
    headers,
  });
}

async function parseErrorResponse(response: Response): Promise<{ errorDetail: string; data: any }> {
  let errorDetail = `Request failed with status ${response.status}`;
  let data;
  try {
    data = await response.json();
    if (data && data.detail) {
      errorDetail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    }
  } catch {
    // non-JSON response
  }
  return { errorDetail, data };
}

async function authorizedFetchResponse(
  endpoint: string,
  options: RequestInit = {},
  _hasRetried = false
): Promise<Response> {
  const response = await executeFetch(endpoint, options);

  if (!response.ok) {
    const { errorDetail, data } = await parseErrorResponse(response);
    const isNonRefreshable = NON_REFRESHABLE_ENDPOINTS.some((prefix) => endpoint.startsWith(prefix));

    if (response.status === 401 && !isNonRefreshable) {
      if (!_hasRetried) {
        const refreshedToken = await performTokenRefresh();
        if (refreshedToken) {
          return authorizedFetchResponse(endpoint, options, true);
        }
      }
      clearAuthStorage();
      dispatchAuthEvent('civicfix:auth-expired');
      redirectToLoginIfNeeded();
    }

    throw new ApiError(response.status, errorDetail, data);
  }

  return response;
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {},
  _hasRetried = false
): Promise<T> {
  const response = await authorizedFetchResponse(endpoint, options, _hasRetried);

  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }
  return response.text() as unknown as T;
}

export async function fetchAuthorizedBlob(
  endpoint: string,
  options: RequestInit = {},
  _hasRetried = false
): Promise<Blob> {
  const response = await authorizedFetchResponse(endpoint, options, _hasRetried);
  return response.blob();
}
