# CivicFix AI — Real SMTP Email Delivery Specification

This document details the SMTP email notification architecture, supported lifecycle events, templates, error isolation, and production setup for CivicFix AI.

---

## 1. Architecture Overview

CivicFix AI uses asynchronous non-blocking SMTP delivery powered by `aiosmtplib` and FastAPI `BackgroundTasks`:

```mermaid
graph TD
    User["Citizen or Municipal Staff"] --> API["FastAPI Route Handler"]
    API --> DB[("Database Commit")]
    API --> BG["Enqueue BackgroundTask (FastAPI)"]
    API -->|HTTP 200/201 (Instant Response)| User
    BG --> EmailService["EmailService (app/services/email/service.py)"]
    EmailService -->|Check is_configured()| Decision{"EMAIL_ENABLED & SMTP_HOST"}
    Decision -->|Unconfigured| SimLog["Log Simulation (No Network Error)"]
    Decision -->|Configured| SMTPClient["aiosmtplib.SMTP Client"]
    SMTPClient -->|STARTTLS / SSL| SMTPServer["Mail Server / Relay (Mailpit, SES, SendGrid)"]
    SMTPClient -->|Timeout / Conn Error| Retry["Bounded Retry (2 Attempts, 1s backoff)"]
```

### Key Design Principles:
1. **Zero Route Latency**: Email sending runs as an asynchronous background task. HTTP response times for citizens submitting complaints or staff marking tickets are unaffected by SMTP socket latency.
2. **Failure Isolation**: An SMTP network outage, invalid recipient address, or authentication failure **never crashes or rolls back** database transactions. Failures are caught and logged as warnings.
3. **Multipart MIME**: Every notification sends both an accessible plain-text fallback and a responsive, branded HTML email.
4. **Deep-Link Security**: All templates generate explicit links to `${PUBLIC_APP_URL}/complaints/${id}` for instant single-click tracking.

---

## 2. Notification Triggers & Templates

CivicFix AI sends emails across the full civic remediation lifecycle:

| Lifecycle Event | Function in `EmailService` | Target Recipient | Context Included |
| :--- | :--- | :--- | :--- |
| **1. Complaint Submitted** | `send_submission_acknowledgment` | Citizen | Reference number (`CF-YYYY-NNNN-RRR`), category, title, tracking link |
| **2. Status Transition** | `send_status_update` | Citizen | Old status, new status, transition notes, tracking link |
| **3. Stage 1 Verification** | `send_resolution_awaiting_verification` | Citizen | Field crew completion summary, call to action to inspect repair photos |
| **4. Stage 2 Result** | `send_resolution_confirmed_or_reopened` | Citizen & Staff | Citizen satisfaction outcome (`Confirmed & Closed` or `Contested & Reopened`) |

---

## 3. Configuration & Environment Variables

Configure these settings in your `.env` file:

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `EMAIL_ENABLED` | Master switch for email delivery | `false` (default in dev) |
| `SMTP_HOST` | Hostname of SMTP relay | `smtp.example.com` or `localhost` |
| `SMTP_PORT` | Port for SMTP relay | `587` (STARTTLS) or `465` (SSL) |
| `SMTP_USERNAME` | SMTP authentication username | `notifications@city.gov` |
| `SMTP_PASSWORD` | SMTP authentication password | Secret application password |
| `SMTP_USE_TLS` | Enable STARTTLS (standard for port 587) | `true` |
| `SMTP_USE_SSL` | Enable direct SSL (standard for port 465) | `false` |
| `SMTP_FROM_EMAIL` | Sender email address | `no-reply@city.gov` |
| `SMTP_FROM_NAME` | Sender display name | `CivicFix AI Alerts` |
| `PUBLIC_APP_URL` | Public frontend URL for email deep links | `http://localhost:5173` |
| `SMTP_TIMEOUT_SECONDS` | Network timeout per SMTP socket attempt | `15.0` |

> [!WARNING]
> **Mutually Exclusive TLS/SSL**: Do not set both `SMTP_USE_TLS=true` and `SMTP_USE_SSL=true`. The configuration validator will raise a validation error on startup.

---

## 4. Development Simulation & Testing

### 4.1 Safe Local Default (No SMTP Server Needed)
When `EMAIL_ENABLED=false` (the repository default), the service logs:
```
[EMAIL SIMULATED] EMAIL_ENABLED=False. Email to <citizen@example.org> not transmitted over network. Subject: '[CivicFix AI] Complaint Received: #CF-2026-0001-123'
```
No connection attempts are made, preventing hangs or test delays.

### 4.2 Local Testing with Mailpit / MailHog
To inspect rendered HTML emails in a local browser during development:
1. Run Mailpit via Docker:
   ```bash
   docker run -d --name mailpit -p 1025:1025 -p 8025:8025 axllent/mailpit
   ```
2. Set `.env`:
   ```bash
   EMAIL_ENABLED=true
   SMTP_HOST=localhost
   SMTP_PORT=1025
   SMTP_USE_TLS=false
   SMTP_USE_SSL=false
   ```
3. Open `http://localhost:8025` in your browser to view incoming formatted messages in real time.

