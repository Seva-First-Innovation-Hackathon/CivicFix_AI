#!/usr/bin/env python3
"""
Secure Single Government Admin Provisioning CLI for CivicFix AI.
Enforces the Single-Admin Invariant: Refuses creation if an admin already exists.
Reads credentials from arguments or environment variables.
"""
import sys
import os
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.session import SessionLocal, Base, engine
from app.models.entities import User, NotificationPreference
from app.models.enums import UserRole
from app.core.security import get_password_hash
from app.core.config import settings

def bootstrap_admin(email: str, password: str, full_name: str, phone: str = None):
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if ANY Government Admin already exists
        existing_admin = db.query(User).filter(User.role == UserRole.GOVERNMENT_ADMIN.value).first()
        if existing_admin:
            print(f"[SECURITY INFO] A Government Admin account already exists in this municipality:")
            print(f"  Existing Admin: {existing_admin.email} (ID: {existing_admin.id})")
            print(f"  Enforcing Single-Admin Invariant: Existing administrator preserved.")
            return existing_admin

        # Check if the requested email is in use by another role
        user_with_email = db.query(User).filter(User.email == email.lower()).first()
        if user_with_email:
            print(f"[ERROR] An account with email '{email}' already exists with role '{user_with_email.role}'.")
            return user_with_email

        if not password or len(password) < 8:
            raise ValueError("Administrator password must be at least 8 characters long.")

        # Create single admin account
        admin = User(
            email=email.lower().strip(),
            full_name=full_name.strip(),
            phone_number=phone,
            hashed_password=get_password_hash(password),
            role=UserRole.GOVERNMENT_ADMIN.value,
            is_active=True,
            is_verified=True
        )
        db.add(admin)
        db.flush()

        notif_pref = NotificationPreference(
            user_id=admin.id,
            in_app_enabled=True,
            email_enabled=True,
            sms_enabled=True
        )
        db.add(notif_pref)

        db.commit()
        db.refresh(admin)

        print("==================================================================")
        print("  CIVICFIX AI — GOVERNMENT ADMIN ACCOUNT PROVISIONED SUCCESSFULLY ")
        print("==================================================================")
        print(f"  Email:      {admin.email}")
        print(f"  Full Name:  {admin.full_name}")
        print(f"  Role:       {admin.role}")
        print(f"  User ID:    {admin.id}")
        print("  Security:   Argon2id password hash stored. Single-admin lock active.")
        print("==================================================================")

    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap Single Municipal Government Admin")
    parser.add_argument("--email", default=os.getenv("INITIAL_ADMIN_EMAIL", "admin@civicfix.gov"), help="Admin email")
    parser.add_argument("--password", default=os.getenv("INITIAL_ADMIN_PASSWORD", "AdminSecure2026!"), help="Admin password")
    parser.add_argument("--name", default=os.getenv("INITIAL_ADMIN_NAME", "Municipal Commissioner"), help="Admin full name")
    parser.add_argument("--phone", default=os.getenv("INITIAL_ADMIN_PHONE", "+91 98765 43210"), help="Admin phone")
    
    args = parser.parse_args()
    bootstrap_admin(email=args.email, password=args.password, full_name=args.name, phone=args.phone)

