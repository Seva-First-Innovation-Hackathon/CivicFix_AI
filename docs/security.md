# CivicFix AI — Security Architecture & Access Control Specification

This document details the security principles, cryptographic implementations, authorization models, and defense-in-depth measures implemented in CivicFix AI.

---

## 1. Threat Model & Security Posture

CivicFix AI is designed for public municipal operations. It handles sensitive citizen data (geolocation, physical address, photographs) and administrative operations (crew dispatch, municipal resource allocation). 

Key threats mitigated:
1. **Horizontal Privilege Escalation / Insecure Direct Object References (IDOR)**: Preventing Citizen A from viewing, editing, confirming, or reopening Citizen B's complaint.
2. **Vertical Privilege Escalation**: Preventing citizens or field staff from accessing administrative controls, overriding AI, or reassigning departments.
3. **Admin Account Hijacking / Duplication**: Strictly prohibiting unauthenticated administrative registration or the provisioning of multiple Government Admin accounts.
4. **Malicious File Ingestion**: Preventing remote code execution (RCE) and path traversal through user-uploaded complaint attachments.
5. **Data Tampering & Accountability Avoidance**: Ensuring an immutable audit trail for every triage override, status transition, and resolution confirmation.

---

## 2. Authentication Architecture

### 2.1 Password Hashing with Argon2id
All user passwords are encrypted using **Argon2id** (via `argon2-cffi`), the winner of the Password Hashing Competition (PHC) and the recommended standard by OWASP:

- **Type**: Argon2id (hybrid version combining Argon2d resistance to GPU cracking and Argon2i resistance to side-channel timing attacks).
- **Parameters**:
  - Time Cost ($t$): 2 iterations
  - Memory Cost ($m$): $65536 \text{ KiB}$ (64 MB)
  - Parallelism ($p$): 4 threads
- **Implementation**: Handled transparently by `app/core/security.py` via `PasswordHasher()`.
- Legacy or weaker algorithms (MD5, SHA1, plain SHA256) are strictly barred.

### 2.2 JWT Authentication & Token Lifecycle
Authentication uses signed JSON Web Tokens (JWT) adhering to RFC 7519:

- **Algorithm**: HMAC-SHA256 (`HS256`) with a cryptographically secure 256-bit secret key.
- **Access Tokens**:
  - Expiry: **15 minutes** (`ACCESS_TOKEN_EXPIRE_MINUTES = 15`)
  - Payload claims:
    ```json
    {
      "sub": "3f9c6d12-45e8-4672-8820-21a4fa0a8b9e",
      "email": "arjun.citizen@example.com",
      "role": "CITIZEN",
      "department_id": null,
      "exp": 1729267200
    }
    ```
- **Refresh Tokens**:
  - Expiry: **7 days** (`REFRESH_TOKEN_EXPIRE_DAYS = 7`)
  - Usage: Securely exchanged via `/api/v1/auth/refresh` without prompting the user to re-enter credentials.
- **Storage**: Tokens are sent in the `Authorization: Bearer <token>` header. Frontend state clears tokens on logout or 401 Unauthorized responses.

---

## 3. Strict Role-Based Access Control (RBAC)

The application enforces four clearly differentiated roles:

| Role | Permitted Actions | Prohibited Actions |
| :--- | :--- | :--- |
| **`CITIZEN`** | Register account; submit complaints; upload evidence; view personal complaints; view public impact dashboard; confirm satisfactory resolution; reopen incomplete resolution; submit feedback. | Cannot view other citizens' complaints; cannot access municipal portal; cannot reassign crew; cannot override AI assessments. |
| **`MUNICIPAL_MEMBER`** | Sign in via municipal portal; review departmental complaints; review AI assessments; assign field crews; log notes; view operational metrics. | Cannot register publicly; cannot access Government Admin settings; cannot modify platform configuration; cannot create admin accounts. |
| **`FIELD_CREW`** | Sign in via municipal portal; view assigned work orders; update task statuses (`IN_PROGRESS`, `BLOCKED`); upload completion photos and material logs. | Cannot browse citizen records; cannot view unassigned tickets; cannot alter department settings; cannot close complaints without citizen verification. |
| **`GOVERNMENT_ADMIN`** | Super-administrator of the municipal instance; manage departments; provision staff & crews; override AI triage; audit logs; manage system settings. | Exactly **one** instance permitted; cannot create a second Government Admin. |

### Backend Dependency Injection Enforcement
Every protected route declares role guards via FastAPI dependency injection:

```python
# app/core/dependencies.py

async def require_role(required_roles: list[UserRole]):
    def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Requires role in {[r.value for r in required_roles]}"
            )
        return current_user
    return role_checker
```

---

## 4. The Single-Admin Invariant

To prevent unauthorized takeover and shadow administrative accounts, CivicFix AI enforces a **Single-Admin Invariant**:

1. **No Public Admin Registration**: The `/api/v1/auth/register` endpoint rejects any registration payload requesting non-`CITIZEN` roles with an immediate `400 Bad Request`.
2. **Secure CLI Provisioning**: The initial Government Admin must be provisioned using `backend/bootstrap.py`:
   ```bash
   python backend/bootstrap.py --email admin@civicfix.gov --password "SecureAdminPass123!" --name "Chief Municipal Administrator"
   ```
3. **Idempotent Invariant Check**: If an administrator already exists in the database, `bootstrap.py` immediately exits with exit code `1`:
   ```
   [SECURITY ERROR] An administrator account already exists.
   Enforcing Single-Admin Invariant: Creation of a second administrator is strictly forbidden.
   ```
4. **API-Level Barrier**: The staff creation endpoint `/api/v1/admin/users` validates:
   ```python
   if user_in.role == UserRole.GOVERNMENT_ADMIN:
       raise HTTPException(
           status_code=status.HTTP_400_BAD_REQUEST,
           detail="Creation of a second Government Admin is prohibited. Only one admin allowed."
       )
   ```

---

## 5. Anti-IDOR (Insecure Direct Object Reference) Protection

To prevent horizontal data leaks, every API route accessing a complaint verifies resource ownership against `current_user`:

```python
# app/api/v1/complaints.py

@router.get("/{complaint_id}")
async def get_complaint(
    complaint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
        
    # Anti-IDOR Enforcement:
    if current_user.role == UserRole.CITIZEN and complaint.citizen_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: You cannot view or modify complaints submitted by other citizens."
        )
    return complaint
```

This check is verified through automated tests (`test_idor_protection_citizen_complaint_access`), confirming that attempts by Citizen B to inspect or verify Citizen A's ticket are blocked with `403 Forbidden`.

---

## 6. Secure Object Storage & Upload Sanitization

To protect against malicious file uploads and directory traversal attacks:

1. **MIME Validation**: Allowed extensions and MIME headers are strictly limited to `image/jpeg`, `image/png`, and `image/webp`. Executable files (`.exe`, `.sh`, `.php`, `.js`) and HTML files are rejected.
2. **Size Enforcement**: Enforces a strict **10 MB limit** per attachment.
3. **Filename Sanitization & Path Traversal Prevention**:
   ```python
   # Original client filenames are stripped using secure_filename()
   safe_name = secure_filename(file.filename)
   # Stored on disk under a unique UUID prefix:
   stored_name = f"{uuid.uuid4()}_{safe_name}"
   ```
4. **Isolated Storage**: Files are stored in dedicated directories (`uploads/complaints/`, `uploads/resolutions/`) outside the source tree.

---

## 7. Two-Stage Resolution Verification Security

To prevent municipal departments from fraudulently closing civic tickets without physical repair:

1. **Stage 1**: Field crew uploads completion notes and after-repair photos (`/api/v1/admin/complaints/{id}/resolve`). Status transitions to `AWAITING_CITIZEN_CONFIRMATION`.
2. **Stage 2**: ONLY the citizen who filed the original complaint can confirm or reopen the ticket:
   - Calling `/api/v1/complaints/{id}/confirm` transitions ticket to `RESOLVED` and captures citizen satisfaction ratings.
   - Calling `/api/v1/complaints/{id}/reopen` transitions ticket to `REOPENED` with a mandatory dispute justification note, notifying municipal officers.
3. Staff and administrators cannot bypass citizen verification for complaint closure.

---

## 8. Immutable Audit Trail

Every state-altering event is captured in the `audit_logs` table:
- **Recorded Fields**: `id`, `user_id`, `action`, `resource_type`, `resource_id`, `ip_address`, `details`, `created_at`.
- **Logged Actions**: `AUTH_LOGIN`, `CREATE_COMPLAINT`, `AI_OVERRIDE`, `ASSIGN_DEPARTMENT`, `DISPATCH_CREW`, `SUBMIT_RESOLUTION`, `CONFIRM_RESOLUTION`, `REOPEN_COMPLAINT`.
- **Integrity**: Audit logs are insert-only; no API or UI interface supports updating or deleting audit entries.

