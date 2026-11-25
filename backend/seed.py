#!/usr/bin/env python3
"""
CivicFix AI — Explicit Opt-In Demonstration Data Seeder.

Security guarantees:
- Strictly disabled in production (`ENVIRONMENT=production`).
- Strictly opt-in in development (`ALLOW_DEMO_SEEDING=true` or `--demo-seed`).
- Never embeds or prints static passwords; reads supplied passwords from environment variables
  or generates fresh ephemeral random passwords per invocation.
"""
import argparse
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import secrets
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.init_db import ensure_default_departments
from app.db.session import SessionLocal
from app.models.entities import (
    User, CitizenProfile, MunicipalDepartment, DepartmentMembership, CrewProfile,
    Complaint, AIAnalysis, WorkOrder, ResolutionSubmission, ResolutionVerification
)
from app.models.enums import (
    UserRole, ComplaintCategory, PriorityLevel, ComplaintStatus, WorkOrderStatus
)


def _resolve_demo_password(env_name: str) -> str:
    val = os.getenv(env_name, "").strip()
    if len(val) >= 8:
        return val
    # Ephemeral non-static fallback for isolated local dev demos when env var is omitted
    return secrets.token_urlsafe(14)


def seed_demo_data(explicit_opt_in: bool = False):
    env_name = settings.ENVIRONMENT.lower()
    opt_in = explicit_opt_in or os.getenv("ALLOW_DEMO_SEEDING", "").lower() == "true"

    if env_name == "production":
        print("[SEED] Refusing demo seeding in ENVIRONMENT=production.")
        return

    if not opt_in:
        print("[SEED] Demo seeding skipped (opt-in required: set ALLOW_DEMO_SEEDING=true or pass --demo-seed).")
        return

    db = SessionLocal()
    try:
        print("[SEED] Checking existing demo data...")
        ensure_default_departments(db)

        # 0. Single Government Admin (opt-in demo dev only if none exists)
        admin_user = db.query(User).filter(User.role == UserRole.GOVERNMENT_ADMIN.value).first()
        if not admin_user:
            admin_user = User(
                email=os.getenv("INITIAL_ADMIN_EMAIL", "admin@civicfix.gov"),
                full_name=os.getenv("INITIAL_ADMIN_NAME", "Municipal Commissioner"),
                phone_number="+91 98765 43210",
                hashed_password=get_password_hash(_resolve_demo_password("INITIAL_ADMIN_PASSWORD")),
                role=UserRole.GOVERNMENT_ADMIN.value,
                is_active=True,
                is_verified=True,
            )
            db.add(admin_user)
            db.flush()

        # 1. Load Departments
        depts = {d.code: d for d in db.query(MunicipalDepartment).all()}

        # 2. Municipal Staff Member
        staff_user = db.query(User).filter(User.email == "officer.sharma@civicfix.gov").first()
        if not staff_user:
            staff_user = User(
                email="officer.sharma@civicfix.gov",
                full_name="Rajesh Sharma (Roads Officer)",
                phone_number="+91 98450 11223",
                hashed_password=get_password_hash(_resolve_demo_password("DEMO_STAFF_PASSWORD")),
                role=UserRole.MUNICIPAL_MEMBER.value,
                is_active=True,
                is_verified=True,
            )
            db.add(staff_user)
            db.flush()

            db.add(DepartmentMembership(
                user_id=staff_user.id,
                department_id=depts["ROADS"].id,
                designation="Senior Assistant Engineer",
                can_assign=True,
                can_verify=True,
            ))

        # 3. Field Crew
        crew_user = db.query(User).filter(User.email == "crew.patel@civicfix.gov").first()
        if not crew_user:
            crew_user = User(
                email="crew.patel@civicfix.gov",
                full_name="Vikas Patel (Rapid Road Crew)",
                phone_number="+91 98110 33445",
                hashed_password=get_password_hash(_resolve_demo_password("DEMO_CREW_PASSWORD")),
                role=UserRole.FIELD_CREW.value,
                is_active=True,
                is_verified=True,
            )
            db.add(crew_user)
            db.flush()

            db.add(CrewProfile(
                user_id=crew_user.id,
                department_id=depts["ROADS"].id,
                vehicle_number="TS-09-EA-4521",
                contact_number="+91 98110 33445",
                active_task_count=1,
            ))

        # 4. Citizens
        citizen1 = db.query(User).filter(User.email == "citizen.arjun@example.com").first()
        if not citizen1:
            citizen1 = User(
                email="citizen.arjun@example.com",
                full_name="Arjun Reddy",
                phone_number="+91 99001 55667",
                hashed_password=get_password_hash(_resolve_demo_password("DEMO_CITIZEN_PASSWORD")),
                role=UserRole.CITIZEN.value,
                is_active=True,
                is_verified=True,
            )
            db.add(citizen1)
            db.flush()
            db.add(CitizenProfile(user_id=citizen1.id, preferred_language="te", address="H.No 4-22, Jubilee Enclave"))

        citizen2 = db.query(User).filter(User.email == "citizen.priya@example.com").first()
        if not citizen2:
            citizen2 = User(
                email="citizen.priya@example.com",
                full_name="Priya Nair",
                phone_number="+91 99002 66778",
                hashed_password=get_password_hash(_resolve_demo_password("DEMO_CITIZEN_PASSWORD")),
                role=UserRole.CITIZEN.value,
                is_active=True,
                is_verified=True,
            )
            db.add(citizen2)
            db.flush()
            db.add(CitizenProfile(user_id=citizen2.id, preferred_language="en", address="Apt 203, Green Meadows"))

        # 5. Complaints (synthetic demo scenarios only when complaint table is empty)
        if db.query(Complaint).count() == 0:
            now = datetime.now(timezone.utc)

            c1 = Complaint(
                reference_number="CF-2026-0001-DEMO",
                citizen_id=citizen1.id,
                title="Massive Pothole on Inner Ring Road junction causing vehicular skidding",
                description="A 3-foot wide, 8-inch deep crater has developed near the flyover pillar 42.",
                category=ComplaintCategory.ROADS.value,
                subcategory="Road Surface Damage & Potholes",
                latitude=17.4399,
                longitude=78.4983,
                address="Near Pillar 42, Inner Ring Road, Secunderabad",
                landmark="Opposite Metro Pillar 42",
                status=ComplaintStatus.IN_PROGRESS.value,
                priority=PriorityLevel.P1.value,
                department_id=depts["ROADS"].id,
                assigned_crew_id=crew_user.id,
                ai_processing_status="COMPLETED",
                sla_deadline=now + timedelta(hours=8),
                created_at=now - timedelta(hours=4),
            )
            db.add(c1)
            db.flush()
            db.add(AIAnalysis(
                complaint_id=c1.id,
                provider="mock",
                model_name="civicfix-deterministic-nlp-v1",
                suggested_category=ComplaintCategory.ROADS.value,
                suggested_subcategory="Road Surface Damage & Potholes",
                suggested_priority=PriorityLevel.P1.value,
                confidence_score=0.96,
                safety_hazard_detected=True,
                urgency_level="CRITICAL",
                summary_explanation="Critical safety hazard detected on active vehicular corridor.",
                visual_findings='{"damage_detected": true, "depth_estimate": "20cm", "surface": "Asphalt"}',
                duplicate_checked=True,
                created_at=c1.created_at,
            ))
            db.add(WorkOrder(
                complaint_id=c1.id,
                department_id=depts["ROADS"].id,
                crew_id=crew_user.id,
                title="Emergency Hot-Mix Bitumen Patching - Inner Ring Road",
                instructions="Deploy rapid repair team with hot-mix bitumen.",
                status=WorkOrderStatus.IN_PROGRESS.value,
                scheduled_date=now - timedelta(hours=2),
            ))

            c2 = Complaint(
                reference_number="CF-2026-0002-DEMO",
                citizen_id=citizen1.id,
                title="Continuous row of 5 streetlights dark on 8th Cross Road",
                description="Streetlights dark behind community park for three nights.",
                category=ComplaintCategory.STREETLIGHTS.value,
                subcategory="Non-functional Luminaire / Broken Pole",
                latitude=17.4435,
                longitude=78.4870,
                address="8th Cross Road, Jubilee Enclave",
                landmark="Behind Community Garden",
                status=ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value,
                priority=PriorityLevel.P2.value,
                department_id=depts["LIGHTING"].id,
                ai_processing_status="COMPLETED",
                sla_deadline=now + timedelta(hours=18),
                created_at=now - timedelta(days=1, hours=6),
            )
            db.add(c2)
            db.flush()
            db.add(AIAnalysis(
                complaint_id=c2.id,
                provider="mock",
                model_name="civicfix-deterministic-nlp-v1",
                suggested_category=ComplaintCategory.STREETLIGHTS.value,
                suggested_subcategory="Non-functional Luminaire / Broken Pole",
                suggested_priority=PriorityLevel.P2.value,
                confidence_score=0.91,
                safety_hazard_detected=False,
                urgency_level="HIGH",
                summary_explanation="Cluster luminaire failure in pedestrian residential sector.",
                duplicate_checked=True,
                created_at=c2.created_at,
            ))
            db.add(ResolutionSubmission(
                complaint_id=c2.id,
                submitted_by_id=staff_user.id,
                resolution_notes="Replaced blown MCB and installed 5 new 70W LED luminaires.",
                submitted_at=now - timedelta(hours=3),
            ))

            c3 = Complaint(
                reference_number="CF-2026-0003-DEMO",
                citizen_id=citizen2.id,
                title="Garbage bin overflowing and spilling onto sidewalk",
                description="Community dumper bin has not been cleared for 4 days.",
                category=ComplaintCategory.GARBAGE.value,
                subcategory="Waste Accumulation & Illegal Dumping",
                latitude=17.4280,
                longitude=78.4550,
                address="Near Lane 3, Green Meadows",
                landmark="Beside City Public School",
                status=ComplaintStatus.RESOLVED.value,
                priority=PriorityLevel.P3.value,
                department_id=depts["SANITATION"].id,
                ai_processing_status="COMPLETED",
                sla_deadline=now - timedelta(hours=10),
                created_at=now - timedelta(days=3),
            )
            db.add(c3)
            db.flush()
            db.add(AIAnalysis(
                complaint_id=c3.id,
                provider="mock",
                model_name="civicfix-deterministic-nlp-v1",
                suggested_category=ComplaintCategory.GARBAGE.value,
                suggested_subcategory="Waste Accumulation & Illegal Dumping",
                suggested_priority=PriorityLevel.P3.value,
                confidence_score=0.88,
                safety_hazard_detected=False,
                urgency_level="MEDIUM",
                summary_explanation="Solid waste accumulation requiring compactor truck dispatch.",
                duplicate_checked=True,
                created_at=c3.created_at,
            ))
            db.add(ResolutionVerification(
                complaint_id=c3.id,
                citizen_id=citizen2.id,
                is_satisfied=True,
                feedback_rating=5,
                feedback_notes="Sanitation crew cleaned the area thoroughly.",
                verified_at=now - timedelta(hours=12),
            ))

        db.commit()
        print("[SEED] Demonstration dataset initialized (credentials redacted from logs).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Opt-in local demo seeder for CivicFix AI")
    parser.add_argument("--demo-seed", action="store_true", help="Explicitly opt into seeding local demo accounts")
    args = parser.parse_args()
    seed_demo_data(explicit_opt_in=args.demo_seed)
