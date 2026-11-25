import { describe, it, expect, beforeEach, vi } from 'vitest';
import fs from 'fs';
import path from 'path';
import {
  apiRequest,
  ApiError,
  TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  USER_KEY,
  resetRefreshStateForTesting,
} from '../services/api';
import { authService } from '../services/authService';

describe('Authentication Token Refresh & Expired Session Handling', () => {
  beforeEach(() => {
    localStorage.clear();
    resetRefreshStateForTesting();
    vi.restoreAllMocks();
  });

  it('rotates refresh token once on 401 and retries original request with new access token', async () => {
    localStorage.setItem(TOKEN_KEY, 'expired-access-token');
    localStorage.setItem(REFRESH_TOKEN_KEY, 'valid-refresh-1');
    localStorage.setItem(USER_KEY, JSON.stringify({ id: 'u1', email: 'c@example.com' }));

    const fetchMock = vi
      .fn()
      // 1. Initial call fails 401
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Token expired' }), {
          status: 401,
          headers: { 'content-type': 'application/json' },
        })
      )
      // 2. Refresh succeeds with rotated tokens
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: 'fresh-access-2',
            refresh_token: 'rotated-refresh-2',
            token_type: 'bearer',
            user_id: 'u1',
            email: 'c@example.com',
            full_name: 'Citizen',
            role: 'CITIZEN',
          }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        )
      )
      // 3. Single retry succeeds
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ total: 1, complaints: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      );

    globalThis.fetch = fetchMock as any;

    const result = await apiRequest('/complaints/my');
    expect(result).toEqual({ total: 1, complaints: [] });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(localStorage.getItem(TOKEN_KEY)).toBe('fresh-access-2');
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('rotated-refresh-2');

    // Verify retry sent updated Bearer header
    const retryHeaders = fetchMock.mock.calls[2][1].headers as Record<string, string>;
    expect(retryHeaders.Authorization).toBe('Bearer fresh-access-2');
  });

  it('shares a single refresh request across concurrent 401 calls', async () => {
    localStorage.setItem(TOKEN_KEY, 'expired-token');
    localStorage.setItem(REFRESH_TOKEN_KEY, 'shared-refresh-1');

    let refreshCount = 0;

    globalThis.fetch = vi.fn(async (url: string, init?: RequestInit) => {
      const authHeader = (init?.headers as Record<string, string>)?.Authorization;
      if (url.endsWith('/auth/refresh')) {
        refreshCount += 1;
        await new Promise((r) => setTimeout(r, 15));
        return new Response(
          JSON.stringify({
            access_token: 'new-shared-access',
            refresh_token: 'new-shared-refresh',
          }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        );
      }

      if (authHeader === 'Bearer expired-token') {
        return new Response(JSON.stringify({ detail: 'Expired' }), {
          status: 401,
          headers: { 'content-type': 'application/json' },
        });
      }

      return new Response(JSON.stringify({ endpoint: url }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }) as any;

    const results = await Promise.all([
      apiRequest('/complaints/my'),
      apiRequest('/notifications'),
      apiRequest('/auth/me'),
    ]);

    expect(refreshCount).toBe(1);
    expect(results).toHaveLength(3);
    expect(localStorage.getItem(TOKEN_KEY)).toBe('new-shared-access');
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('new-shared-refresh');
  });

  it('clears storage and avoids infinite retries when refresh fails', async () => {
    localStorage.setItem(TOKEN_KEY, 'expired-access');
    localStorage.setItem(REFRESH_TOKEN_KEY, 'revoked-refresh');
    localStorage.setItem(USER_KEY, JSON.stringify({ id: 'u1' }));

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Expired' }), {
          status: 401,
          headers: { 'content-type': 'application/json' },
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Refresh token revoked' }), {
          status: 401,
          headers: { 'content-type': 'application/json' },
        })
      );

    globalThis.fetch = fetchMock as any;

    await expect(apiRequest('/complaints/my')).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(USER_KEY)).toBeNull();
  });

  it('never retries infinitely if the retried request also returns 401', async () => {
    localStorage.setItem(TOKEN_KEY, 'expired-access');
    localStorage.setItem(REFRESH_TOKEN_KEY, 'valid-refresh');

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Expired' }), { status: 401, headers: { 'content-type': 'application/json' } }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: 'fresh-access', refresh_token: 'fresh-refresh' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Still unauthorized' }), { status: 401, headers: { 'content-type': 'application/json' } }));

    globalThis.fetch = fetchMock as any;

    await expect(apiRequest('/complaints/my')).rejects.toThrow('Still unauthorized');
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('preserves login error messages without attempting token refresh', async () => {
    localStorage.setItem(REFRESH_TOKEN_KEY, 'stale-refresh');
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Invalid email or password' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      })
    );
    globalThis.fetch = fetchMock as any;

    await expect(authService.login({ email: 'a@b.com', password: 'bad' })).rejects.toThrow(
      'Invalid email or password'
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('stale-refresh');
  });

  it('sends refresh_token to /auth/logout and clears storage', async () => {
    localStorage.setItem(TOKEN_KEY, 'tok-1');
    localStorage.setItem(REFRESH_TOKEN_KEY, 'rt-1');
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ message: 'Successfully logged out' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );
    globalThis.fetch = fetchMock as any;

    await authService.logout();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1].body).toContain('rt-1');
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
  });

  it('verifies PWA maskable icon asset exists as valid PNG', () => {
    const iconPath = path.resolve(__dirname, '../../public/icons/icon-512-maskable.png');
    expect(fs.existsSync(iconPath)).toBe(true);
    const bytes = fs.readFileSync(iconPath);
    // PNG magic signature: 89 50 4E 47
    expect(Array.from(bytes.slice(0, 4))).toEqual([0x89, 0x50, 0x4e, 0x47]);
  });
});
