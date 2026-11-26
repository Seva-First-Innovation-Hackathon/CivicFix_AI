#!/usr/bin/env python3
"""
Secure Single Government Admin Provisioning CLI for CivicFix AI.
Enforces the Single-Admin Invariant: Refuses creation if an admin already exists.
Requires credentials explicitly via CLI arguments or environment variables (no hardcoded defaults).
"""
import argparse
import os
import sys
from pathlib import Path
from pydantic import EmailStr, TypeAdapter, ValidationError

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.security import get_password_hash
import app.db.session as db_session
from app.models.entities import User, NotificationPreference
from app.models.enums import UserRole

_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_WEAK_PASSWORDS = {
    "changeme",
    "password",
    "password123",
    "12345678",
    "admin123",
    "admin1234",
    "qwerty123",
}


def _validate_bootstrap_inputs(email: str, password: str, full_name: str) -> tuple[str, str, str]:
    clean_email = (email or "").strip().lower()
    if not clean_email:
        raise ValueError("Administrator email must be provided via --email or INITIAL_ADMIN_EMAIL.")
    try:
        clean_email = str(_EMAIL_ADAPTER.validate_python(clean_email)).lower()
    except ValidationError as exc:
        raise ValueError("Administrator email must be a valid email address.") from exc

    clean_name = (full_name or "").strip()
    if len(clean_name) < 2 or len(clean_name) > 100:
        raise ValueError("Administrator full name must be between 2 and 100 characters.")

    raw_pwd = password or ""
    if not raw_pwd.strip() or len(raw_pwd) < 8 or len(raw_pwd) > 100:
        raise ValueError(
            "Administrator password must be between 8 and 100 characters and supplied via "
            "--password or INITIAL_ADMIN_PASSWORD (static default passwords are disabled)."
        )
    if raw_pwd.strip().lower() in _WEAK_PASSWORDS:
        raise ValueError("Administrator password is too weak; choose a strong unique secret.")

    return clean_email, raw_pwd, clean_name


def bootstrap_admin(email: str = "", password: str = "", full_name: str = "Municipal Commissioner", phone: str | None = None):
    db = db_session.SessionLocal()
    try:
        # 1. Check whether the municipality already has a valid Government Admin BEFORE requiring initial credentials
        existing_admin = db.query(User).filter(User.role == UserRole.GOVERNMENT_ADMIN.value).first()
        if existing_admin:
            if not existing_admin.is_active:
                raise RuntimeError(
                    "A Government Admin account exists in the database but is deactivated; "
                    "cannot guarantee an active administrator under the Single-Admin Invariant."
                )
            print("[SECURITY INFO] A Government Admin account already exists in this municipality:")
            print(f"  Existing Admin: {existing_admin.email} (ID: {existing_admin.id})")
            print("  Enforcing Single-Admin Invariant: Existing administrator preserved.")
            return existing_admin

        # 2. No Government Admin exists — strictly require & validate explicit credentials
        clean_email, raw_pwd, clean_name = _validate_bootstrap_inputs(email, password, full_name)

        # 3. Reject email collisions with existing non-admin accounts (fail closed)
        user_with_email = db.query(User).filter(User.email == clean_email).first()
        if user_with_email:
            raise ValueError(
                f"Cannot provision Government Admin: account with email '{clean_email}' "
                f"already exists with role '{user_with_email.role}'."
            )

        admin = User(
            email=clean_email,
            full_name=clean_name,
            phone_number=phone,
            hashed_password=get_password_hash(raw_pwd),
            role=UserRole.GOVERNMENT_ADMIN.value,
            is_active=True,
            is_verified=True,
        )
        db.add(admin)
        db.flush()

        db.add(NotificationPreference(
            user_id=admin.id,
            in_app_enabled=True,
            email_enabled=True,
            sms_enabled=True,
        ))
        db.commit()
        db.refresh(admin)

        print("==================================================================")
        print("  CIVICFIX AI — GOVERNMENT ADMIN ACCOUNT PROVISIONED SUCCESSFULLY ")
        print("==================================================================")
        print(f"  Email:      {admin.email}")
        print(f"  Full Name:  {admin.full_name}")
        print(f"  Role:       {admin.role}")
        print(f"  User ID:    {admin.id}")
        print("  Security:   Argon2id hash stored. Single-admin lock active.")
        print("==================================================================")
        return admin
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap Single Municipal Government Admin")
    parser.add_argument("--email", default=os.getenv("INITIAL_ADMIN_EMAIL", ""), help="Admin email")
    parser.add_argument("--password", default=os.getenv("INITIAL_ADMIN_PASSWORD", ""), help="Admin password")
    parser.add_argument("--name", default=os.getenv("INITIAL_ADMIN_NAME", "Municipal Commissioner"), help="Admin full name")
    parser.add_argument("--phone", default=os.getenv("INITIAL_ADMIN_PHONE"), help="Admin phone")

    args = parser.parse_args()
    try:
        bootstrap_admin(email=args.email, password=args.password, full_name=args.name, phone=args.phone)
    except Exception as exc:
        print(f"[BOOTSTRAP ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
