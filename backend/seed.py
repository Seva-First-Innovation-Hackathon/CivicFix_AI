#!/usr/bin/env python3
"""
CivicFix AI — Demonstration Data Seeder.
Populates realistic civic complaints, departments, municipal members, field crews, and citizens.
Clearly flags records as synthetic demo data.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import random

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.session import SessionLocal, Base, engine
from app.models.entities import (
    User, CitizenProfile, MunicipalDepartment, DepartmentMembership, CrewProfile,
    Complaint, ComplaintAttachment, AIAnalysis, ComplaintStatusHistory,
    WorkOrder, ResolutionSubmission, ResolutionVerification, Notification
)
from app.models.enums import (
    UserRole, ComplaintCategory, PriorityLevel, ComplaintStatus,
    WorkOrderStatus, NotificationType
)
from app.core.security import get_password_hash
from app.core.config import settings
import os

def seed_demo_data():
    # In production, demo seeding is disabled by default to protect real data from synthetic pollution
    if settings.ENVIRONMENT.lower() == "production" and os.getenv("ALLOW_DEMO_SEEDING", "").lower() != "true":
        print("[SEED] Production environment detected (ENVIRONMENT=production).")
        print("[SEED] Synthetic demo complaints and citizen accounts will NOT be created automatically.")
        print("[SEED] Preserving production database integrity. (Set ALLOW_DEMO_SEEDING=true to override).")
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        print("[SEED] Checking existing seed data...")

        # 0. Single Government Admin
        admin_user = db.query(User).filter(User.role == UserRole.GOVERNMENT_ADMIN.value).first()
        if not admin_user:
            admin_user = User(
                email="admin@civicfix.gov",
                full_name="Municipal Commissioner",
                phone_number="+91 98765 43210",
                hashed_password=get_password_hash("AdminSecure2026!"),
                role=UserRole.GOVERNMENT_ADMIN.value,
                is_active=True,
                is_verified=True
            )
            db.add(admin_user)
            db.flush()

        # 1. Departments
        dept_data = [
            ("Roads and Public Works", "ROADS", "Road surface, potholes, bridges, and vehicular corridors"),
            ("Street Lighting & Electrical", "LIGHTING", "Illumination luminaires, streetlights, and electrical poles"),
            ("Sanitation & Solid Waste", "SANITATION", "Waste collection, litter removal, and public hygiene"),
            ("Water Supply & Distribution", "WATER", "Drinking water network, pipelines, and valves"),
            ("Drainage & Flood Management", "DRAINAGE", "Stormwater drains, culverts, and monsoon waterlogging"),
            ("Parks & Urban Forestry", "PARKS", "Urban tree cover, parks, and fallen arbor hazards"),
        ]

        depts = {}
        for name, code, desc in dept_data:
            dept = db.query(MunicipalDepartment).filter(MunicipalDepartment.code == code).first()
            if not dept:
                dept = MunicipalDepartment(name=name, code=code, description=desc, is_active=True)
                db.add(dept)
                db.flush()
            depts[code] = dept

        # 2. Municipal Staff Member
        staff_user = db.query(User).filter(User.email == "officer.sharma@civicfix.gov").first()
        if not staff_user:
            staff_user = User(
                email="officer.sharma@civicfix.gov",
                full_name="Rajesh Sharma (Roads Officer)",
                phone_number="+91 98450 11223",
                hashed_password=get_password_hash("StaffSecure2026!"),
                role=UserRole.MUNICIPAL_MEMBER.value,
                is_active=True,
                is_verified=True
            )
            db.add(staff_user)
            db.flush()

            mem = DepartmentMembership(
                user_id=staff_user.id,
                department_id=depts["ROADS"].id,
                designation="Senior Assistant Engineer",
                can_assign=True,
                can_verify=True
            )
            db.add(mem)

        # 3. Field Crew
        crew_user = db.query(User).filter(User.email == "crew.patel@civicfix.gov").first()
        if not crew_user:
            crew_user = User(
                email="crew.patel@civicfix.gov",
                full_name="Vikas Patel (Rapid Road Crew)",
                phone_number="+91 98110 33445",
                hashed_password=get_password_hash("CrewSecure2026!"),
                role=UserRole.FIELD_CREW.value,
                is_active=True,
                is_verified=True
            )
            db.add(crew_user)
            db.flush()

            crew_prof = CrewProfile(
                user_id=crew_user.id,
                department_id=depts["ROADS"].id,
                vehicle_number="TS-09-EA-4521",
                contact_number="+91 98110 33445",
                active_task_count=1
            )
            db.add(crew_prof)

        # 4. Citizens
        citizen1 = db.query(User).filter(User.email == "citizen.arjun@example.com").first()
        if not citizen1:
            citizen1 = User(
                email="citizen.arjun@example.com",
                full_name="Arjun Reddy",
                phone_number="+91 99001 55667",
                hashed_password=get_password_hash("CitizenPass2026!"),
                role=UserRole.CITIZEN.value,
                is_active=True,
                is_verified=True
            )
            db.add(citizen1)
            db.flush()

            c1_prof = CitizenProfile(user_id=citizen1.id, preferred_language="te", address="H.No 4-22, Jubilee Enclave")
            db.add(c1_prof)

        citizen2 = db.query(User).filter(User.email == "citizen.priya@example.com").first()
        if not citizen2:
            citizen2 = User(
                email="citizen.priya@example.com",
                full_name="Priya Nair",
                phone_number="+91 99002 66778",
                hashed_password=get_password_hash("CitizenPass2026!"),
                role=UserRole.CITIZEN.value,
                is_active=True,
                is_verified=True
            )
            db.add(citizen2)
            db.flush()

            c2_prof = CitizenProfile(user_id=citizen2.id, preferred_language="en", address="Apt 203, Green Meadows")
            db.add(c2_prof)

        # 5. Complaints
        existing_complaints = db.query(Complaint).count()
        if existing_complaints == 0:
            now = datetime.now(timezone.utc)

            # Sample 1: Critical P1 Pothole - In Progress
            c1 = Complaint(
                reference_number="CF-2026-0001-DEMO",
                citizen_id=citizen1.id,
                title="Massive Pothole on Inner Ring Road junction causing vehicular skidding",
                description="A 3-foot wide, 8-inch deep crater has developed near the flyover pillar 42. Multiple two-wheelers have skidded in the dark. Requires emergency bitumen patch.",
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
                sla_deadline=now + timedelta(hours=8),
                created_at=now - timedelta(hours=4)
            )
            db.add(c1)
            db.flush()

            ai1 = AIAnalysis(
                complaint_id=c1.id,
                provider="mock",
                model_name="civicfix-deterministic-nlp-v1",
                suggested_category=ComplaintCategory.ROADS.value,
                suggested_subcategory="Road Surface Damage & Potholes",
                suggested_priority=PriorityLevel.P1.value,
                confidence_score=0.96,
                safety_hazard_detected=True,
                urgency_level="CRITICAL",
                summary_explanation="Critical safety hazard detected on active vehicular corridor. High risk of two-wheeler accidents.",
                visual_findings='{"damage_detected": true, "depth_estimate": "20cm", "surface": "Asphalt"}',
                duplicate_checked=True,
                created_at=c1.created_at
            )
            db.add(ai1)

            wo1 = WorkOrder(
                complaint_id=c1.id,
                department_id=depts["ROADS"].id,
                crew_id=crew_user.id,
                title="Emergency Hot-Mix Bitumen Patching - Inner Ring Road",
                instructions="Deploy rapid repair team with hot-mix bitumen. Level crater to road gradient. Secure with warning cones.",
                status=WorkOrderStatus.IN_PROGRESS.value,
                scheduled_date=now - timedelta(hours=2)
            )
            db.add(wo1)

            # Sample 2: Broken Streetlights - Awaiting Citizen Confirmation
            c2 = Complaint(
                reference_number="CF-2026-0002-DEMO",
                citizen_id=citizen1.id,
                title="Continuous row of 5 streetlights dark on 8th Cross Road",
                description="The entire stretch behind the community park has been pitch dark for three nights, creating safety concerns for late pedestrians.",
                category=ComplaintCategory.STREETLIGHTS.value,
                subcategory="Non-functional Luminaire / Broken Pole",
                latitude=17.4435,
                longitude=78.4870,
                address="8th Cross Road, Jubilee Enclave",
                landmark="Behind Community Garden",
                status=ComplaintStatus.AWAITING_CITIZEN_CONFIRMATION.value,
                priority=PriorityLevel.P2.value,
                department_id=depts["LIGHTING"].id,
                sla_deadline=now + timedelta(hours=18),
                created_at=now - timedelta(days=1, hours=6)
            )
            db.add(c2)
            db.flush()

            ai2 = AIAnalysis(
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
                created_at=c2.created_at
            )
            db.add(ai2)

            res2 = ResolutionSubmission(
                complaint_id=c2.id,
                submitted_by_id=staff_user.id,
                resolution_notes="Replaced blown MCB and installed 5 new 70W LED luminaires. Checked lux levels at pavement height. Circuit energized.",
                submitted_at=now - timedelta(hours=3)
            )
            db.add(res2)

            # Sample 3: Garbage Accumulation - Resolved and Verified
            c3 = Complaint(
                reference_number="CF-2026-0003-DEMO",
                citizen_id=citizen2.id,
                title="Garbage bin overflowing and spilling onto sidewalk",
                description="Community dumper bin has not been cleared for 4 days. Stray cattle and foul odor spreading across lane.",
                category=ComplaintCategory.GARBAGE.value,
                subcategory="Waste Accumulation & Illegal Dumping",
                latitude=17.4280,
                longitude=78.4550,
                address="Near Lane 3, Green Meadows",
                landmark="Beside City Public School",
                status=ComplaintStatus.RESOLVED.value,
                priority=PriorityLevel.P3.value,
                department_id=depts["SANITATION"].id,
                sla_deadline=now - timedelta(hours=10),
                created_at=now - timedelta(days=3)
            )
            db.add(c3)
            db.flush()

            ai3 = AIAnalysis(
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
                created_at=c3.created_at
            )
            db.add(ai3)

            verif3 = ResolutionVerification(
                complaint_id=c3.id,
                citizen_id=citizen2.id,
                is_satisfied=True,
                feedback_rating=5,
                feedback_notes="Sanitation crew cleaned the area thoroughly and disinfected with bleaching powder. Excellent work!",
                verified_at=now - timedelta(hours=12)
            )
            db.add(verif3)

            # Sample 4: Water Supply Leakage - Under Review
            c4 = Complaint(
                reference_number="CF-2026-0004-DEMO",
                citizen_id=citizen2.id,
                title="High pressure drinking water pipe ruptured and gushing on road",
                description="Drinking water main line connection cracked. Clean water has been flowing onto the tarmac for over an hour.",
                category=ComplaintCategory.WATER_SUPPLY.value,
                subcategory="Pipeline Leakage / Supply Disruption",
                latitude=17.4350,
                longitude=78.4620,
                address="Sector 4 Main Road, near Water Tank",
                landmark="Adjacent to Overhead Water Tank",
                status=ComplaintStatus.UNDER_REVIEW.value,
                priority=PriorityLevel.P2.value,
                department_id=depts["WATER"].id,
                sla_deadline=now + timedelta(hours=20),
                created_at=now - timedelta(hours=1)
            )
            db.add(c4)
            db.flush()

            ai4 = AIAnalysis(
                complaint_id=c4.id,
                provider="mock",
                model_name="civicfix-deterministic-nlp-v1",
                suggested_category=ComplaintCategory.WATER_SUPPLY.value,
                suggested_subcategory="Pipeline Leakage / Supply Disruption",
                suggested_priority=PriorityLevel.P2.value,
                confidence_score=0.94,
                safety_hazard_detected=False,
                urgency_level="HIGH",
                summary_explanation="Potable water wastage and erosion risk detected.",
                duplicate_checked=True,
                created_at=c4.created_at
            )
            db.add(ai4)

        db.commit()
        print("[SEED] Demonstration dataset seeded successfully!")
        print("  - Municipal Departments: 6")
        print("  - Municipal Officer:     officer.sharma@civicfix.gov (Password: StaffSecure2026!)")
        print("  - Field Crew:            crew.patel@civicfix.gov (Password: CrewSecure2026!)")
        print("  - Citizen 1:             citizen.arjun@example.com (Password: CitizenPass2026!)")
        print("  - Citizen 2:             citizen.priya@example.com (Password: CitizenPass2026!)")
        print("  - Real-world complaints: 4 active lifecycle scenarios")

    finally:
        db.close()

if __name__ == "__main__":
    seed_demo_data()

