import React from 'react';
import { ComplaintStatus, PriorityLevel } from '../../types';

interface StatusBadgeProps {
  status: ComplaintStatus | string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  const getStatusStyles = (st: string) => {
    switch (st) {
      case 'SUBMITTED':
      case 'AI_ANALYSIS_PENDING':
        return 'bg-purple-50 text-purple-700 border-purple-200';
      case 'UNDER_REVIEW':
      case 'PRIORITIZED':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'ASSIGNED':
      case 'IN_PROGRESS':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'RESOLUTION_SUBMITTED':
      case 'AWAITING_CITIZEN_CONFIRMATION':
        return 'bg-emerald-50 text-emerald-800 border-emerald-300 animate-pulse';
      case 'RESOLVED':
        return 'bg-emerald-100 text-emerald-800 border-emerald-200';
      case 'REOPENED':
        return 'bg-rose-100 text-rose-800 border-rose-200';
      case 'CANCELLED':
      case 'REJECTED_WITH_REASON':
        return 'bg-slate-100 text-slate-600 border-slate-200';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const formatStatus = (st: string) => {
    return st.replace(/_/g, ' ');
  };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getStatusStyles(
        status
      )} ${className}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 opacity-75"></span>
      {formatStatus(status)}
    </span>
  );
};

interface PriorityBadgeProps {
  priority: PriorityLevel | string;
  className?: string;
}

export const PriorityBadge: React.FC<PriorityBadgeProps> = ({ priority, className = '' }) => {
  const getPriorityStyles = (p: string) => {
    switch (p) {
      case 'P1':
        return 'bg-rose-100 text-rose-800 border-rose-300 font-bold';
      case 'P2':
        return 'bg-orange-100 text-orange-800 border-orange-300';
      case 'P3':
        return 'bg-blue-100 text-blue-800 border-blue-300';
      case 'P4':
        return 'bg-slate-100 text-slate-700 border-slate-300';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const getPriorityLabel = (p: string) => {
    switch (p) {
      case 'P1':
        return 'P1 • Critical';
      case 'P2':
        return 'P2 • High';
      case 'P3':
        return 'P3 • Normal';
      case 'P4':
        return 'P4 • Low';
      default:
        return p;
    }
  };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium border ${getPriorityStyles(
        priority
      )} ${className}`}
    >
      {getPriorityLabel(priority)}
    </span>
  );
};

