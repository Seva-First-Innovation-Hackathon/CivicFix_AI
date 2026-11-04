import { describe, it, expect } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { StatusBadge, PriorityBadge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { translations } from '../i18n/translations';

describe('Frontend Component Tests', () => {
  it('renders StatusBadge with formatted text', () => {
    render(<StatusBadge status="AWAITING_CITIZEN_CONFIRMATION" />);
    expect(screen.getByText('AWAITING CITIZEN CONFIRMATION')).toBeInTheDocument();
  });

  it('renders PriorityBadge with correct label for P1', () => {
    render(<PriorityBadge priority="P1" />);
    expect(screen.getByText('P1 • Critical')).toBeInTheDocument();
  });

  it('renders PriorityBadge with correct label for P2', () => {
    render(<PriorityBadge priority="P2" />);
    expect(screen.getByText('P2 • High')).toBeInTheDocument();
  });

  it('renders Button component with children and handles disabled state', () => {
    render(<Button disabled>Submit Test</Button>);
    const btn = screen.getByRole('button', { name: /Submit Test/i });
    expect(btn).toBeInTheDocument();
    expect(btn).toBeDisabled();
  });

  it('provides translations for English, Telugu, and Hindi', () => {
    expect(translations.en.brand_name).toBe('CivicFix AI');
    expect(translations.te.brand_name).toBe('సివిక్‌ఫిక్స్ AI');
    expect(translations.hi.brand_name).toBe('सिविकफिक्स AI');
  });
});

