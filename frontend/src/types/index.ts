export type UserRole = 'CITIZEN' | 'GOVERNMENT_ADMIN' | 'MUNICIPAL_MEMBER' | 'FIELD_CREW';

export type ComplaintCategory = 
  | 'ROADS'
  | 'STREETLIGHTS'
  | 'GARBAGE'
  | 'DRAINAGE'
  | 'WATER_SUPPLY'
  | 'FOOTPATHS'
  | 'TREES_HAZARDS'
  | 'SANITATION'
  | 'OTHER';

export type PriorityLevel = 'P1' | 'P2' | 'P3' | 'P4';

export type ComplaintStatus =
  | 'SUBMITTED'
  | 'AI_ANALYSIS_PENDING'
  | 'UNDER_REVIEW'
  | 'AWAITING_CITIZEN_INFORMATION'
  | 'NEEDS_MORE_INFORMATION'
  | 'VERIFIED'
  | 'PRIORITIZED'
  | 'ASSIGNED'
  | 'IN_PROGRESS'
  | 'WORK_COMPLETED_PENDING_REVIEW'
  | 'RESOLUTION_SUBMITTED'
  | 'AWAITING_CITIZEN_CONFIRMATION'
  | 'RESOLVED'
  | 'REOPENED'
  | 'REJECTED'
  | 'REJECTED_WITH_REASON'
  | 'CANCELLED'
  | 'FLAGGED_FOR_INVESTIGATION'
  | 'FLAGGED_FOR_REVIEW';

export type WorkOrderStatus = 'ASSIGNED' | 'ACCEPTED' | 'IN_PROGRESS' | 'BLOCKED' | 'WORK_COMPLETED_PENDING_REVIEW' | 'COMPLETED';

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone_number?: string;
  role: UserRole;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  citizen_profile?: {
    preferred_language: string;
    address?: string;
  };
  department_membership?: {
    department_id: string;
    department_name?: string;
    designation: string;
    can_assign: boolean;
    can_verify: boolean;
  };
  crew_profile?: {
    department_id: string;
    department_name?: string;
    vehicle_number?: string;
    contact_number?: string;
    active_task_count: number;
  };
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface Attachment {
  id: string;
  file_name: string;
  file_path: string;
  file_size: number;
  mime_type: string;
  attachment_type: string;
  is_internal?: boolean;
  description?: string;
  uploaded_by_id: string;
  created_at: string;
}

export interface ComplaintComment {
  id: string;
  complaint_id: string;
  user_id: string;
  user_name?: string;
  user_role?: string;
  content: string;
  is_internal: boolean;
  comment_type: string;
  created_at: string;
}

export interface AIAnalysis {
  id: string;
  provider: string;
  model_name: string;
  suggested_category: ComplaintCategory;
  suggested_subcategory?: string;
  suggested_priority: PriorityLevel;
  confidence_score: number;
  safety_hazard_detected: boolean;
  urgency_level: string;
  summary_explanation: string;
  visual_findings?: string;
  duplicate_checked: boolean;
  is_overridden: boolean;
  override_reason?: string;
  created_at: string;
}

export interface StatusHistory {
  id: string;
  from_status?: string;
  to_status: string;
  changed_by_id?: string;
  changed_by_name?: string;
  change_reason?: string;
  notes?: string;
  created_at: string;
}

export interface WorkOrder {
  id: string;
  complaint_id: string;
  complaint_reference?: string;
  complaint_title?: string;
  complaint_address?: string;
  complaint_latitude?: number;
  complaint_longitude?: number;
  complaint_priority?: string;
  department_id: string;
  department_name?: string;
  crew_id: string;
  crew_name?: string;
  title: string;
  instructions: string;
  status: WorkOrderStatus;
  blocker_reason?: string;
  scheduled_date?: string;
  completion_date?: string;
  created_at: string;
  updated_at: string;
}

export interface ResolutionSubmission {
  id: string;
  resolution_notes: string;
  submitted_by_id: string;
  submitted_by_name?: string;
  submitted_at: string;
}

export interface ResolutionVerification {
  id: string;
  is_satisfied: boolean;
  feedback_rating?: number;
  feedback_notes?: string;
  reopen_reason?: string;
  verified_at: string;
}

export interface Complaint {
  id: string;
  reference_number: string;
  citizen_id: string;
  citizen_name?: string;
  title: string;
  description: string;
  category: ComplaintCategory;
  subcategory?: string;
  latitude: number;
  longitude: number;
  address?: string;
  landmark?: string;
  status: ComplaintStatus;
  priority: PriorityLevel;
  department_id?: string;
  department_name?: string;
  assigned_crew_id?: string;
  assigned_crew_name?: string;
  is_disputed: boolean;
  sla_deadline?: string;
  cancellation_reason?: string;
  rejection_reason?: string;
  investigation_notes?: string;
  clarification_requested?: string;
  created_at: string;
  updated_at: string;
  attachments: Attachment[];
  ai_analysis?: AIAnalysis;
  status_history: StatusHistory[];
  work_orders: WorkOrder[];
  resolution_submissions: ResolutionSubmission[];
  resolution_verifications: ResolutionVerification[];
  comments?: ComplaintComment[];
}

export interface Department {
  id: string;
  name: string;
  code: string;
  description?: string;
  contact_email?: string;
  contact_phone?: string;
  is_active: boolean;
  created_at: string;
  member_count: number;
  crew_count: number;
  open_complaints_count: number;
}

export interface NotificationItem {
  id: string;
  user_id: string;
  title: string;
  message: string;
  notification_type: string;
  complaint_id?: string;
  is_read: boolean;
  created_at: string;
}

export interface PotentialDuplicate {
  id: string;
  primary_complaint_id: string;
  primary_reference?: string;
  primary_title?: string;
  duplicate_complaint_id: string;
  duplicate_reference?: string;
  duplicate_title?: string;
  similarity_score: number;
  distance_meters: number;
  reason: string;
  status: string;
  created_at: string;
}

export interface AnalyticsOverview {
  metrics: {
    total_complaints: number;
    active_complaints: number;
    pending_review: number;
    in_progress: number;
    awaiting_citizen_confirmation: number;
    resolved_complaints: number;
    reopened_complaints: number;
    high_priority_unresolved: number;
    overdue_complaints: number;
    average_resolution_hours: number;
    citizen_satisfaction_rate: number;
  };
  by_category: Array<{ category: string; count: number; percentage: number }>;
  by_priority: Array<{ priority: string; count: number; percentage: number }>;
  by_department: Array<{ department_name: string; count: number; resolved_count: number }>;
  trends: Array<{ date: string; submitted: number; resolved: number }>;
}

export interface PublicImpactData {
  total_complaints_reported: number;
  complaints_resolved: number;
  complaints_in_progress: number;
  resolution_success_rate: number;
  average_resolution_hours: number;
  top_categories: Array<{ category: string; count: number }>;
  is_demonstration_mode: boolean;
}

