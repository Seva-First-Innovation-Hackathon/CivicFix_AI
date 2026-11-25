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

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.entities import User, NotificationPreference
from app.models.enums import UserRole


def bootstrap_admin(email: str, password: str, full_name: str, phone: str | None = None):
    if not email or not email.strip():
        raise ValueError("Administrator email must be provided via --email or INITIAL_ADMIN_EMAIL.")

    db = SessionLocal()
    try:
        # Check if ANY Government Admin already exists
        existing_admin = db.query(User).filter(User.role == UserRole.GOVERNMENT_ADMIN.value).first()
        if existing_admin:
            print("[SECURITY INFO] A Government Admin account already exists in this municipality:")
            print(f"  Existing Admin: {existing_admin.email} (ID: {existing_admin.id})")
            print("  Enforcing Single-Admin Invariant: Existing administrator preserved.")
            return existing_admin

        # Check if the requested email is in use by another role
        user_with_email = db.query(User).filter(User.email == email.lower().strip()).first()
        if user_with_email:
            print(f"[ERROR] An account with email '{email}' already exists with role '{user_with_email.role}'.")
            return user_with_email

        if not password or len(password.strip()) < 8:
            raise ValueError(
                "Administrator password must be at least 8 characters and supplied via "
                "--password or INITIAL_ADMIN_PASSWORD (static default passwords are disabled)."
            )

        admin = User(
            email=email.lower().strip(),
            full_name=full_name.strip(),
            phone_number=phone,
            hashed_password=get_password_hash(password),
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
    except ValueError as exc:
        print(f"[CONFIGURATION ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
