# CivicFix AI — System Architecture Document

## 1. System Overview

**CivicFix AI** ("Report. Resolve. Rebuild Trust.") is an intelligent municipal complaint tracking, AI prioritization, dispatch, and citizen verification platform designed for local urban governments and smart municipalities.

```
+-----------------------------------------------------------------------------------+
|                                  CLIENT LAYER                                     |
|  +---------------------------+  +--------------------------+  +----------------+  |
|  |       Citizen Portal      |  | Municipal Command Portal |  |  Public Site   |  |
|  | (Report, Timeline, Verify)|  | (Triage, Dispatch, Map)  |  | (Impact Data)  |  |
|  +---------------------------+  +--------------------------+  +----------------+  |
+----------------------------------------+------------------------------------------+
                                         | HTTPS / REST JSON
                                         v
+-----------------------------------------------------------------------------------+
|                                 FASTAPI BACKEND                                   |
|  +---------------------+  +----------------------+  +---------------------------+ |
|  | Auth & RBAC Guards  |  | Complaint Lifecycle  |  |  Municipal Administration | |
|  | (Argon2id, JWT, IDOR)|  | (Submissions, SLA)   |  |  (Departments, WorkOrders)| |
|  +---------------------+  +----------------------+  +---------------------------+ |
|                                        |                                          |
|                +-----------------------+-----------------------+                  |
|                |                                               |                  |
|                v                                               v                  |
|  +---------------------------+                   +------------------------------+ |
|  |    AI Service Subsystem   |                   |    Storage Service Adapter   | |
|  | - NLP Text Categorization |                   | - Local Disk / S3 Object     | |
|  | - Computer Vision Damage  |                   | - Strict MIME & Size Checks  | |
|  | - Priority P1-P4 Inference|                   | - Isolated Evidence Paths    | |
|  | - Haversine Deduplication |                   +------------------------------+ |
|  | - Department Routing Engine|                                                   |
|  +---------------------------+                                                    |
+----------------------------------------+------------------------------------------+
                                         | SQLAlchemy 2.0 ORM
                                         v
+-----------------------------------------------------------------------------------+
|                                DATABASE PERSISTENCE                               |
|  PostgreSQL 16 + PostGIS Spatial Engine (SQLite with Haversine math for dev)     |
|  - 18 Normalized Tables                                                           |
|  - Single Government Admin Invariant Enforcement                                  |
|  - Immutable Status Transitions & Audit Logs                                      |
+-----------------------------------------------------------------------------------+
```

## 2. Core Architectural Pillars

### A. Strict Role Isolation & Zero-Trust Access Control (RBAC)
Four separate roles are enforced on the backend:
1. **CITIZEN**: Register, submit reports, track own complaints, verify completed repairs, contest incomplete repairs. Strict IDOR protection guarantees Citizen A can never access Citizen B's complaint dossier.
2. **GOVERNMENT_ADMIN**: Exactly one administrator per municipality, provisioned via a secure bootstrap CLI. Enforces single-admin lock in database transactions.
3. **MUNICIPAL_MEMBER**: Department-scoped staff members who review AI triage, correct classifications, assign work orders, and track SLAs. Created only by the Government Admin.
4. **FIELD_CREW**: Authorized mobile crew members who receive work orders, update task statuses (ASSIGNED -> IN_PROGRESS -> COMPLETED), report blockers, and submit after-repair photographs.

### B. Replaceable AI Service Architecture
The AI subsystem exposes a typed `BaseAIProvider` interface:
- `analyze_text`: Categorization, subcategory, urgency, safety risk extraction.
- `analyze_image`: Surface deformity detection, damage severity evaluation, inconclusive image tagging.
- `transcribe_audio`: Speech-to-text supporting English, Telugu, and Hindi.
- `recommend_priority`: Evaluates safety impact, infrastructure criticality, and assigns P1 to P4 with formal explainability.
- `detect_duplicates`: Combines Haversine spatial proximity (100m radius), category matching, and word token similarity to prevent duplicate crew dispatches without deleting submissions.

### C. Two-Stage Verification Workflow
Resolutions are never marked `RESOLVED` on the field crew's word alone:
1. **Stage 1 (Municipal Submission)**: Crew submits completion details and after-repair photo. Ticket moves to `AWAITING_CITIZEN_CONFIRMATION`.
2. **Stage 2 (Citizen Verification)**: Reporting citizen reviews evidence and confirms resolution (marks `RESOLVED` with 1-5 rating) or contests the repair (marks `REOPENED` with justification).

