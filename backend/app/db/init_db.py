import logging
from sqlalchemy import inspect, text
from app.db.session import engine, Base
import app.models.entities

logger = logging.getLogger(__name__)

def ensure_schema_upgrades():
    """
    Ensures all database tables and new Phase 2 columns exist.
    Performs safe incremental schema alterations for existing databases.
    """
    Base.metadata.create_all(bind=engine)
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        # 1. complaints table columns
        if "complaints" in tables:
            complaint_cols = [c["name"] for c in inspector.get_columns("complaints")]
            new_complaint_cols = [
                ("cancellation_reason", "TEXT"),
                ("rejection_reason", "TEXT"),
                ("investigation_notes", "TEXT"),
                ("clarification_requested", "TEXT"),
            ]
            for col_name, col_type in new_complaint_cols:
                if col_name not in complaint_cols:
                    conn.execute(text(f"ALTER TABLE complaints ADD COLUMN {col_name} {col_type}"))
                    conn.commit()

        # 2. municipal_departments columns
        if "municipal_departments" in tables:
            dept_cols = [c["name"] for c in inspector.get_columns("municipal_departments")]
            if "jurisdiction" not in dept_cols:
                conn.execute(text("ALTER TABLE municipal_departments ADD COLUMN jurisdiction VARCHAR(255) DEFAULT 'City-wide'"))
                conn.commit()

        # 3. department_memberships columns
        if "department_memberships" in tables:
            mem_cols = [c["name"] for c in inspector.get_columns("department_memberships")]
            if "jurisdiction" not in mem_cols:
                conn.execute(text("ALTER TABLE department_memberships ADD COLUMN jurisdiction VARCHAR(255) DEFAULT 'City-wide'"))
                conn.commit()

        # 4. complaint_attachments columns
        if "complaint_attachments" in tables:
            att_cols = [c["name"] for c in inspector.get_columns("complaint_attachments")]
            if "is_internal" not in att_cols:
                conn.execute(text("ALTER TABLE complaint_attachments ADD COLUMN is_internal BOOLEAN DEFAULT FALSE"))
                conn.commit()
            if "description" not in att_cols:
                conn.execute(text("ALTER TABLE complaint_attachments ADD COLUMN description VARCHAR(500)"))
                conn.commit()

