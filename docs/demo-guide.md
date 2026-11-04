# CivicFix AI — Complete 18-Step Live Demonstration Guide

This guide provides a comprehensive, reproducible script for evaluating and demonstrating the **CivicFix AI** platform across all four roles and every phase of the civic complaint lifecycle.

---

## Pre-requisites & Test Accounts

Start the application using either Docker or local mode (see [docs/deployment.md](file:///c:/Users/kinja/OneDrive/Desktop/Civicfix-AI/docs/deployment.md)).

### Seeded Credentials

| Role | Username / Email | Password | Primary Mission |
| :--- | :--- | :--- | :--- |
| **Government Admin** | `admin@civicfix.gov` | `CivicFixAdmin2026!` | Super-admin, oversight, departments, users, audit logs |
| **Municipal Member** | `sharma.officer@civicfix.gov` | `OfficerPass2026!` | Triage review, override AI, dispatch work orders |
| **Field Crew** | `patel.crew@civicfix.gov` | `CrewPass2026!` | Field mobile interface, status updates, submit repair evidence |
| **Citizen (Arjun)** | `arjun.citizen@example.com` | `CitizenPass2026!` | Submitting complaints, tracking, Two-Stage Verification |
| **Citizen (Priya)** | `priya.citizen@example.com` | `CitizenPass2026!` | Proving Anti-IDOR protections and duplicate reporting |

---

## The 18-Step Verification Walkthrough

### Step 1: System Bootstrapping & Single-Admin Invariant
1. Open terminal in the project directory.
2. Run the bootstrap CLI command:
   ```bash
   python backend/bootstrap.py --email admin@civicfix.gov --password "CivicFixAdmin2026!" --name "Chief Municipal Administrator"
   ```
3. Run the exact same command a second time:
   - **Expected Result**: System immediately terminates with security alert:
     `[SECURITY ERROR] An administrator account already exists. Enforcing Single-Admin Invariant: Creation of a second administrator is strictly forbidden.`

### Step 2: Seed Core Municipal Infrastructure
1. Execute `python backend/seed.py`.
2. Inspect the output confirming the initialization of 6 municipal departments (Roads, Sanitation, Electrical, Water, Footpaths, Parks), staff members, field crews, and active complaints.

### Step 3: Public Website & Multi-Language Switching
1. Navigate to `http://localhost:5173/` in your browser.
2. Observe the CivicFix AI hero section, mission statement ("Report. Resolve. Rebuild Trust."), and real-time civic statistics.
3. In the top navigation bar, toggle the language selector from **English** to **Telugu (తెలుగు)** and **Hindi (हिंदी)**:
   - Notice immediate translation of navigation items, hero titles, badges, and interface controls.
4. Visit the **How It Works**, **Civic Issue Categories**, and **About** pages to inspect transparency descriptions.

### Step 4: Citizen Registration with Anti-Privilege Escalation
1. Click **Citizen Portal** -> **Create Account** (`/register`).
2. Fill out name, email, phone number, and password.
3. Submit the registration form:
   - Notice that citizens can ONLY register as role `CITIZEN`.
   - Security verification: Inspect backend code or network payload to confirm that passing `role: "GOVERNMENT_ADMIN"` is blocked with `400 Bad Request`.

### Step 5: Complaint Submission via 4-Step Wizard
1. Sign in as Citizen Arjun (`arjun.citizen@example.com` / `CitizenPass2026!`).
2. Click **Report Issue** (`/report`).
3. Follow the 4-step guided wizard:
   - **Step 1 (Category & Details)**: Enter Title: `"Deep pothole damaging car axles near Clock Tower"`, Description: `"A large, hazardous crater has formed in the center lane of the road. Multiple vehicles have suffered tire blowouts."`
   - **Step 2 (Location)**: Click **"Use My Current Location"** (prompts browser GPS) or click directly on the interactive Leaflet map to drop a pin. Address auto-fills.
   - **Step 3 (Evidence)**: Drag and drop a photo attachment (sample pothole image).
   - **Step 4 (Review & Submit)**: Confirm details and click **Submit Complaint**.
4. The system issues a unique tracking ID (e.g., `CF-2026-0005`).

### Step 6: AI Automated Triage Pipeline Inspection
1. Immediately upon submission, the backend AI triage engine processes the complaint:
   - **NLP Text Classification**: Accurately categorizes the complaint under `POTHOLE`.
   - **Computer Vision Damage Assessment**: Calculates physical damage severity (e.g., `8.2/10`).
   - **Priority Policy**: Evaluates severity against public safety thresholds to assign priority `P1` or `P2`.
   - **Dynamic SLA Calculation**: Calculates deadline (e.g., 24 hours for P1, 48 hours for P2).
   - **Explainability Justification**: Generates transparent rationale displayed in the citizen and admin views.
2. In the Citizen Portal, view the newly submitted ticket details (`/complaints/{id}`) to observe the live AI badge and SLA countdown.

### Step 7: Real-Time Spatial Duplicate Detection Simulation
1. Log out and sign in as Citizen Priya (`priya.citizen@example.com`).
2. Go to **Report Issue** and report another pothole complaint with coordinates placed within 50 meters of Arjun's submission.
3. On submission, the spatial engine calculates the Haversine / PostGIS distance:
   - Distance detected: $< 100\text{ meters}$.
   - The ticket is automatically linked into `potential_duplicates` and flagged for municipal review, avoiding wasted crew dispatches.

### Step 8: IDOR & Horizontal Privilege Escalation Security Test
1. While logged in as Priya, attempt to directly navigate to Arjun's complaint:
   - Enter `http://localhost:5173/complaints/{arjun_complaint_id}`.
2. **Expected Result**: 
   - Backend responds with `403 Forbidden` (`"Access forbidden: You cannot view or modify complaints submitted by other citizens."`).
   - Frontend safely catches the error and displays an unauthorized access banner.
3. Automated test `test_idor_protection_citizen_complaint_access` confirms this programmatically.

### Step 9: Municipal Command Center Overview
1. Sign in to the Municipal Portal (`/staff/login`) as Government Admin (`admin@civicfix.gov` / `CivicFixAdmin2026!`).
2. View the **Executive Dashboard** (`/admin`):
   - Real-time metrics computed directly from database queries (Total complaints, Active work orders, Resolved, SLA compliance rate).
   - Interactive OpenStreetMap displaying all municipal complaints color-coded by priority (`P1 = Red`, `P2 = Amber`, `P3 = Blue`, `P4 = Green`).
3. Click on **Live Map** (`/admin/map`) to filter markers by department and category.

### Step 10: Municipal Officer AI Review & Department Assignment
1. Sign in as Municipal Officer Sharma (`sharma.officer@civicfix.gov` / `OfficerPass2026!`).
2. Navigate to **Complaints** (`/admin/complaints`) and open Arjun's pothole complaint.
3. Review the AI assessment panel:
   - Notice the AI's suggested department (`Roads & Bridges`) and priority (`P1`).
   - Click **Review AI Assessment**: Officers have the authority to confirm or override the priority with a recorded audit justification (e.g., `"Upgraded due to school zone proximity"`).
4. Assign the complaint to the **Roads & Bridges** department.

### Step 11: Field Crew Assignment & Work Order Generation
1. In the same complaint view, click **Create Work Order**.
2. Select **Crew Patel** from the available field units.
3. Set scheduled date and enter specific crew instructions: `"Seal with hot-mix asphalt and compact thoroughly. Place safety cones during operation."`
4. Submit: Complaint status transitions to `CREW_ASSIGNED` and a unique work order number is issued (`WO-2026-0002`).

### Step 12: Field Crew Mobile/Task Interface
1. Sign in through the staff portal as Field Crew Patel (`patel.crew@civicfix.gov` / `CrewPass2026!`).
2. Patel is immediately routed to the **Crew Tasks** mobile-friendly screen (`/admin/crew-tasks`).
3. Only tasks assigned to Patel's crew are visible (Crew isolation enforced).
4. Click **Start Work**:
   - Status updates to `IN_PROGRESS`.
   - Started timestamp is captured.

### Step 13: Progress Logging & Blocker Reporting
1. In the work order card, click **Add Field Update**.
2. Select status `IN_PROGRESS` and enter notes: `"Arrived on site. Excavated loose asphalt and drying the crater."`
3. Optional: Simulate a blocker by selecting `BLOCKED` with notes: `"Traffic diversion required; waiting for traffic police assistance."`

### Step 14: Stage 1 Resolution Submission
1. In Crew Patel's task view, click **Submit Resolution**.
2. Complete the resolution submission modal:
   - Resolution Notes: `"Excavated cavity, filled with 3 cubic meters of hot-mix bituminous concrete, leveled and rolled with vibrating roller. Road surface restored."`
   - Materials Used: `["3 bags asphalt binder", "2 tons hot-mix aggregate"]`.
   - After-Repair Photo: Upload photo evidence of the repaired road surface.
3. Submit the form:
   - Complaint status transitions to **`AWAITING_CITIZEN_CONFIRMATION`**.
   - Note: The ticket is NOT closed yet. Government staff cannot unilaterally mark complaints resolved.

### Step 15: Citizen In-App Notification Delivery
1. Log out of the staff portal.
2. Sign in as Citizen Arjun (`arjun.citizen@example.com`).
3. Observe the **Notifications Bell** in the top navigation bar with an active unread badge.
4. Click the bell:
   - Alert: `"Work Completed on Your Complaint CF-2026-0005. Please inspect the repair evidence and confirm or reopen the ticket."`

### Step 16: Stage 2 Citizen Two-Stage Verification (Scenario A: Confirmation)
1. Open complaint details for `CF-2026-0005`.
2. Notice the prominent **Two-Stage Verification Banner**:
   - Displays the field crew's completion notes.
   - Shows the original before-photo side-by-side with the crew's after-repair evidence photo.
3. Click **"Confirm Satisfactory Resolution"**:
   - Select 5-star rating.
   - Enter citizen comment: `"Excellent work! Road is smooth and safe to drive again. Thank you!"`
4. Submit confirmation:
   - Complaint status transitions to **`RESOLVED`**.
   - Citizen trust score increments.
   - Full timeline reflects citizen verification.

### Step 17: Stage 2 Citizen Dispute (Scenario B: Reopen Ticket)
*(To demonstrate dispute handling on a secondary ticket)*
1. As Citizen Priya, inspect a complaint placed into `AWAITING_CITIZEN_CONFIRMATION`.
2. Click **"Contest / Reopen Complaint"**.
3. Enter contest reason: `"The pothole was only filled with loose gravel which washed away after rain. Issue persists."`
4. Submit:
   - Status transitions to **`REOPENED`**.
   - Work order is flagged as requiring rework.
   - Department officers receive an escalation notification with Priya's contest explanation.

### Step 18: Public Impact Dashboard & Audit Trail Verification
1. Navigate to the **Public Impact Dashboard** (`/impact`):
   - Review municipal transparency metrics: Total Issues Reported, Resolution Rate, Average Turnaround Time, Ward-by-ward breakdown.
   - Privacy verification: Confirm that individual names, private emails, and phone numbers are completely stripped.
2. Sign in as Government Admin (`admin@civicfix.gov`) and open **Audit Logs** (`/admin/audit-logs`):
   - Verify that every action taken across the demonstration (login, complaint creation, AI override, work order dispatch, resolution submission, citizen confirmation, ticket reopening) appears in the immutable log table with actor ID, IP address, timestamp, and metadata payload.
   - Click **Export CSV** to download a verifiable municipal audit report.

