# CivicFix AI — REST API Reference Documentation

Base URL: `/api/v1`  
Interactive OpenAPI Swagger Docs: `http://localhost:8000/api/docs`

## 1. Authentication Endpoints (`/api/v1/auth`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/auth/register` | Public | Citizen self-registration. Role is strictly locked to `CITIZEN`. |
| POST | `/auth/login` | Public | Authenticate with email and password. Returns JWT access and refresh tokens. |
| POST | `/auth/refresh` | Public | Refresh expired access token using valid refresh token. |
| GET | `/auth/me` | Authenticated | Retrieve current user profile and role-specific context. |
| POST | `/auth/logout` | Authenticated | Terminate session and record audit event. |

## 2. Citizen Complaint Endpoints (`/api/v1/complaints`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/complaints` | Citizen | Submit a new complaint. Triggers AI triage and SLA assignment. |
| GET | `/complaints/my` | Citizen | List complaints submitted exclusively by current citizen (Anti-IDOR). |
| GET | `/complaints/{id}` | Owner / Staff | View complaint details. Strict ownership check for citizens. |
| GET | `/complaints/{id}/timeline` | Owner / Staff | View immutable status transition history. |
| POST | `/complaints/{id}/attachments` | Owner / Staff | Upload photographic evidence with MIME and size verification. |
| POST | `/complaints/{id}/confirm-resolution` | Owner | Stage 2: Citizen approves official repair and marks `RESOLVED`. |
| POST | `/complaints/{id}/reopen` | Owner | Stage 2: Citizen contests repair and marks `REOPENED` with justification. |

## 3. Municipal Administration Endpoints (`/api/v1/admin`)

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/admin/dashboard` | Staff / Admin | Real-time operational metrics calculated directly from database. |
| GET | `/admin/complaints` | Staff / Admin | Filterable, paginated register of all complaints. |
| GET | `/admin/complaints/{id}` | Staff / Admin | Complete municipal dossier with AI findings and attachments. |
| PATCH | `/admin/complaints/{id}` | Staff / Admin | Update status with recorded justification. |
| POST | `/admin/complaints/{id}/assign` | Staff / Admin | Assign to department and set confirmed priority. |
| POST | `/admin/complaints/{id}/review-ai` | Staff / Admin | Override AI recommendation with mandatory recorded reason. |
| POST | `/admin/complaints/{id}/resolution` | Crew / Staff | Stage 1: Submit completion notes and transition to `AWAITING_CITIZEN_CONFIRMATION`. |
| GET | `/admin/map/complaints` | Staff / Admin | Geospatial complaint markers with priority styling for Leaflet. |
| GET | `/admin/departments` | Staff / Admin | List all municipal departments and active ticket counts. |
| POST | `/admin/departments` | Gov Admin | Create a new municipal department. |
| GET | `/admin/work-orders` | Staff / Crew | List work orders (crews see assigned work orders). |
| POST | `/admin/work-orders` | Staff / Admin | Dispatch work order to field crew. |
| PATCH | `/admin/work-orders/{id}/status` | Crew / Staff | Update work order status (ASSIGNED -> IN_PROGRESS -> COMPLETED). |
| GET | `/admin/duplicates` | Staff / Admin | Review AI-detected spatial duplicate candidates. |
| POST | `/admin/duplicates/{id}/review` | Staff / Admin | Confirm merge or dismiss duplicate flag. |
| GET | `/admin/users` | Gov Admin | List all user accounts. |
| POST | `/admin/users` | Gov Admin | Provision Municipal Member or Field Crew (refuses 2nd Gov Admin). |
| POST | `/admin/users/{id}/deactivate` | Gov Admin | Deactivate user account. |
| GET | `/admin/audit-logs` | Gov Admin | View system audit trail. |
| GET | `/admin/analytics/export-csv` | Staff / Admin | Download CSV dataset of complaints. |

## 4. Notifications & Public Impact

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/notifications` | Authenticated | List in-app notifications for current user. |
| PATCH | `/notifications/{id}/read` | Authenticated | Mark notification as read. |
| POST | `/notifications/read-all` | Authenticated | Mark all notifications as read. |
| GET | `/public/impact` | Public | Real-time aggregate statistics without exposing citizen PII. |
| GET | `/health` | Public | System and database connectivity probe. |

