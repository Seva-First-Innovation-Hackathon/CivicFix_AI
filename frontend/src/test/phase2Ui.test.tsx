import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { LiveIssueMapPage } from '../pages/admin/LiveIssueMapPage';
import { AdminComplaintDetailPage } from '../pages/admin/AdminComplaintDetailPage';
import { ToastProvider } from '../context/ToastContext';
import { adminService } from '../services/adminService';
import { complaintsService } from '../services/complaintsService';

describe('Phase 2 Frontend UI — Hotspots, AI Mismatches, Overdue SLA, & Evidence Comparison', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem('civicfix_access_token', 'test-token');
  });

  it('fetches and renders real hotspot clusters and updates on filter changes', async () => {
    const mapSpy = vi.spyOn(adminService, 'getMapComplaints').mockResolvedValue({
      complaints: [
        {
          id: 'c1',
          reference_number: 'CF-2026-0001',
          title: 'Road crater near plaza',
          category: 'ROADS',
          status: 'UNDER_REVIEW',
          priority: 'P1',
          latitude: 17.441,
          longitude: 78.491,
          created_at: '2026-11-25T10:00:00Z',
          has_attachments: false,
        },
      ],
    });
    const hotspotSpy = vi.spyOn(adminService, 'getMapHotspots').mockResolvedValue({
      hotspots: [
        {
          bucket_lat: 17.441,
          bucket_lon: 78.491,
          complaint_count: 3,
          open_count: 2,
          p1_count: 1,
          overdue_count: 1,
          dominant_category: 'ROADS',
          intensity: 1.0,
          radius_meters: 600,
        },
      ],
      total_complaints_matched: 3,
      grid_size_meters: 500,
      aggregation_method: 'bounded_coordinate_grid',
      is_demonstration_mode: false,
    });

    render(
      <MemoryRouter>
        <LiveIssueMapPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mapSpy).toHaveBeenCalledTimes(1);
      expect(hotspotSpy).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(/1 Pins • 1 Hotspots/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Filter Category'), { target: { value: 'DRAINAGE' } });
    fireEvent.change(screen.getByLabelText('Hotspot Grid Size'), { target: { value: '1000' } });

    await waitFor(() => {
      expect(hotspotSpy).toHaveBeenCalledWith(
        expect.objectContaining({ category: 'DRAINAGE', grid_size_meters: 1000 })
      );
    });
  });

  it('displays AI processing status, cross-modal disagreement, SLA overdue state, and before/after comparison', async () => {
    vi.spyOn(adminService, 'getComplaint').mockResolvedValue({
      id: 'c-100',
      reference_number: 'CF-2026-X100',
      citizen_id: 'cit-1',
      title: 'Exposed transformer junction',
      description: 'Damaged electrical pole panel in rain.',
      category: 'STREETLIGHTS',
      latitude: 17.44,
      longitude: 78.49,
      status: 'WORK_COMPLETED_PENDING_REVIEW',
      priority: 'P1',
      is_disputed: false,
      sla_deadline: '2026-11-24T10:00:00Z',
      is_overdue: true,
      hours_overdue: 12.5,
      ai_processing_status: 'COMPLETED',
      created_at: '2026-11-23T10:00:00Z',
      updated_at: '2026-11-25T10:00:00Z',
      attachments: [],
      status_history: [],
      work_orders: [],
      resolution_submissions: [],
      resolution_verifications: [],
      ai_analysis: {
        id: 'ai-1',
        provider: 'mock',
        model_name: 'civicfix-deterministic-nlp-v1',
        suggested_category: 'STREETLIGHTS',
        suggested_priority: 'P1',
        confidence_score: 0.88,
        safety_hazard_detected: true,
        urgency_level: 'CRITICAL',
        summary_explanation: 'Critical streetlight electrical hazard.',
        cross_modal_mismatch: true,
        cross_modal_explanation: 'Text indicates STREETLIGHTS while image suggests GARBAGE.',
        routing_tier: 'MEDIUM_CONFIDENCE',
        recommended_action: 'REQUIRE_VERIFICATION',
        duplicate_checked: true,
        is_overridden: false,
        created_at: '2026-11-23T10:01:00Z',
      },
      resolution_comparisons: [
        {
          id: 'cmp-1',
          complaint_id: 'c-100',
          before_attachment_id: 'att-1',
          after_attachment_id: 'att-2',
          provider: 'mock',
          model_name: 'civicfix-deterministic-nlp-v1',
          changes_detected: true,
          visual_differences_json: JSON.stringify(['Normalized pixel delta: 42.1/255']),
          summary: 'Visible structural changes observed across repair evidence.',
          uncertainty_notes: 'Municipal staff inspection is mandatory.',
          requires_human_review: true,
          created_at: '2026-11-25T10:00:00Z',
        },
      ],
    });
    vi.spyOn(adminService, 'getDepartments').mockResolvedValue([]);
    vi.spyOn(adminService, 'listUsers').mockResolvedValue([]);
    vi.spyOn(complaintsService, 'getComments').mockResolvedValue([]);

    render(
      <ToastProvider>
        <MemoryRouter initialEntries={['/admin/complaints/c-100']}>
          <Routes>
            <Route path="/admin/complaints/:id" element={<AdminComplaintDetailPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/#CF-2026-X100/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/OVERDUE \(12\.5h\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Image\/Text Category Disagreement Flagged for Review/i)).toBeInTheDocument();
    expect(screen.getByText(/Visible structural changes observed/i)).toBeInTheDocument();
    expect(screen.getByText(/Municipal staff inspection is mandatory/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Re-run AI Analysis/i })).toBeInTheDocument();
  });
});
