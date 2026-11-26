import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AdminComplaintDetailPage } from '../pages/admin/AdminComplaintDetailPage';
import { ComplaintDetailsPage } from '../pages/citizen/ComplaintDetailsPage';
import { ReportIssuePage } from '../pages/citizen/ReportIssuePage';
import { CivicFixMap } from '../components/common/CivicFixMap';
import { ToastProvider } from '../context/ToastContext';
import { adminService } from '../services/adminService';
import { complaintsService } from '../services/complaintsService';
import { Complaint } from '../types';

const makeComplaint = (overrides: Partial<Complaint> = {}): Complaint => ({
  id: 'c-200',
  reference_number: 'CF-2026-0200',
  citizen_id: 'cit-1',
  title: 'Damaged stormwater grate',
  description: 'Broken iron storm grate along busy school walkway.',
  category: 'DRAINAGE',
  latitude: 17.44,
  longitude: 78.49,
  status: 'UNDER_REVIEW',
  priority: 'P1',
  is_disputed: false,
  created_at: '2026-11-25T10:00:00Z',
  updated_at: '2026-11-25T10:00:00Z',
  attachments: [],
  status_history: [],
  work_orders: [],
  resolution_submissions: [],
  resolution_verifications: [],
  ...overrides,
});

describe('Phase 2.8.1 Security & Lifecycle Audit UI Regression Tests', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    if (!URL.createObjectURL) {
      Object.defineProperty(URL, 'createObjectURL', {
        writable: true,
        value: vi.fn(() => 'blob:http://localhost/mock-object-url'),
      });
    }
    if (!URL.revokeObjectURL) {
      Object.defineProperty(URL, 'revokeObjectURL', {
        writable: true,
        value: vi.fn(),
      });
    }
  });

  it('uses scoped /admin/crews via listFieldCrews instead of admin-only /admin/users on AdminComplaintDetailPage', async () => {
    vi.spyOn(adminService, 'getComplaint').mockResolvedValue(makeComplaint());
    vi.spyOn(adminService, 'getDepartments').mockResolvedValue([]);
    const crewsSpy = vi.spyOn(adminService, 'listFieldCrews').mockResolvedValue([]);
    const usersSpy = vi.spyOn(adminService, 'listUsers').mockResolvedValue([]);
    vi.spyOn(complaintsService, 'getComments').mockResolvedValue([]);

    render(
      <ToastProvider>
        <MemoryRouter initialEntries={['/admin/complaints/c-200']}>
          <Routes>
            <Route path="/admin/complaints/:id" element={<AdminComplaintDetailPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/#CF-2026-0200/i)).toBeInTheDocument();
    });

    expect(crewsSpy).toHaveBeenCalledTimes(1);
    expect(usersSpy).not.toHaveBeenCalled();
  });

  it('fetches citizen evidence via Authorization Bearer header and Blob URL (zero ?token= in URL) and revokes on unmount', async () => {
    localStorage.setItem('civicfix_token', 'citizen-jwt-123');

    const createObjSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:civicfix/evidence-99');
    const revokeObjSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['fake-image-bytes'], { type: 'image/jpeg' }), {
        status: 200,
        headers: { 'Content-Type': 'image/jpeg' },
      })
    );

    vi.spyOn(complaintsService, 'getComplaintById').mockResolvedValue(
      makeComplaint({
        attachments: [
          {
            id: 'att-99',
            file_path: '/uploads/complaints/grate.jpg',
            file_name: 'grate.jpg',
            file_size: 204800,
            mime_type: 'image/jpeg',
            attachment_type: 'CITIZEN_ORIGINAL',
            uploaded_by_id: 'cit-1',
            created_at: '2026-11-25T10:00:00Z',
          },
        ],
      })
    );
    vi.spyOn(complaintsService, 'getComplaintTimeline').mockResolvedValue([]);

    const { unmount } = render(
      <ToastProvider>
        <MemoryRouter initialEntries={['/citizen/complaints/c-200']}>
          <Routes>
            <Route path="/citizen/complaints/:id" element={<ComplaintDetailsPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    );

    const img = await screen.findByAltText('Complaint attachment');
    expect(img).toHaveAttribute('src', 'blob:civicfix/evidence-99');
    expect(img.getAttribute('src')).not.toContain('?token=');
    expect(img.getAttribute('src')).not.toContain('citizen-jwt-123');
    expect(img.getAttribute('src')).not.toContain('/uploads/');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [reqUrl, reqInit] = fetchSpy.mock.calls[0];
    expect(String(reqUrl)).toContain('/api/v1/evidence/att-99');
    expect(String(reqUrl)).not.toContain('token=');
    expect((reqInit?.headers as Record<string, string>)?.Authorization).toBe('Bearer citizen-jwt-123');
    expect(createObjSpy).toHaveBeenCalledTimes(1);

    unmount();
    expect(revokeObjSpy).toHaveBeenCalledWith('blob:civicfix/evidence-99');
  });

  it('loads map popup evidence previews through authenticated Blob fetch using first_attachment_id and handles unauthorized state safely', async () => {
    localStorage.setItem('civicfix_token', 'staff-jwt-456');
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:civicfix/map-thumb-1');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Not authorized' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const { container } = render(
      <MemoryRouter>
        <CivicFixMap
          mode="viewer"
          complaints={[
            {
              id: 'comp-map-1',
              reference_number: 'CF-2026-MAP1',
              title: 'Flooded underpass',
              category: 'DRAINAGE',
              status: 'UNDER_REVIEW',
              priority: 'P1',
              latitude: 17.442,
              longitude: 78.491,
              first_attachment_id: 'att-map-1',
            },
          ]}
        />
      </MemoryRouter>
    );

    const marker = container.querySelector('.leaflet-marker-icon');
    expect(marker).not.toBeNull();
    fireEvent.click(marker!);

    await waitFor(() => {
      expect(screen.getByText(/Not authorized to view this evidence/i)).toBeInTheDocument();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [reqUrl, reqInit] = fetchSpy.mock.calls[0];
    expect(String(reqUrl)).toContain('/api/v1/evidence/att-map-1');
    expect(String(reqUrl)).not.toContain('token=');
    expect((reqInit?.headers as Record<string, string>)?.Authorization).toBe('Bearer staff-jwt-456');
    expect(container.innerHTML).not.toContain('/uploads/');
    expect(container.innerHTML).not.toContain('staff-jwt-456');
  });

  it('surfaces explicit warning instead of unqualified success when photo attachment upload fails on ReportIssuePage', async () => {
    vi.spyOn(complaintsService, 'createComplaint').mockResolvedValue(
      makeComplaint({
        id: 'c-new',
        reference_number: 'CF-2026-9988',
        title: 'Collapsed curb drain',
        status: 'SUBMITTED',
      })
    );
    const uploadSpy = vi
      .spyOn(complaintsService, 'uploadAttachment')
      .mockRejectedValue(new Error('Storage backend unavailable'));

    const { container } = render(
      <ToastProvider>
        <MemoryRouter>
          <ReportIssuePage />
        </MemoryRouter>
      </ToastProvider>
    );

    fireEvent.change(screen.getByPlaceholderText(/Deep pothole/i), {
      target: { value: 'Collapsed curb drain on Main St' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Explain the defect/i), {
      target: { value: 'Stormwater curb drain has collapsed leaving an open cavity.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Continue/i }));

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).not.toBeNull();
    const file = new File(['mock-image-bytes'], 'drain.jpg', { type: 'image/jpeg' });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /Continue/i }));

    fireEvent.click(screen.getByRole('button', { name: /Continue/i }));

    const consentCheckbox = screen.getByRole('checkbox');
    fireEvent.click(consentCheckbox);
    fireEvent.click(screen.getByRole('button', { name: /Submit Report/i }));

    await waitFor(() => {
      expect(screen.getByText(/Photographic evidence could not be uploaded/i)).toBeInTheDocument();
    });

    expect(uploadSpy).toHaveBeenCalledWith('c-new', file, 'ORIGINAL');
    expect(screen.getAllByText(/Storage backend unavailable/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/Complaint Saved — Photo Upload Failed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Complaint Submitted Successfully/i)).not.toBeInTheDocument();
  });
});
