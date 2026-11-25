import io
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image
from botocore.exceptions import ClientError
import pytest

from app.core.config import Settings
from app.core.limiter import limiter
from app.models.entities import Complaint, ComplaintAttachment, WorkOrder
from app.models.enums import ComplaintCategory, ComplaintStatus
from app.services.storage.backends import (
    LocalStorageBackend,
    S3CompatibleStorageBackend,
    StorageObjectNotFoundError,
    StorageUnavailableError,
    compute_sha256_hex,
)
from app.services.storage.migrator import migrate_local_uploads_to_cloud
from app.services.storage.service import storage_service


class _FakeS3Body:
    def __init__(self, data: bytes):
        self._data = data
        self._offset = 0

    def read(self, amt: Optional[int] = None) -> bytes:
        if amt is None:
            rem = self._data[self._offset:]
            self._offset = len(self._data)
            return rem
        chunk = self._data[self._offset:self._offset + amt]
        self._offset += len(chunk)
        return chunk

    def iter_chunks(self, chunk_size: int = 65536):
        while self._offset < len(self._data):
            yield self.read(chunk_size)

    def close(self) -> None:
        pass


class FakeS3Client:
    """In-process S3/R2 protocol simulator matching boto3 signatures for isolated testing."""

    def __init__(self):
        self.objects: Dict[tuple[str, str], Dict[str, Any]] = {}
        self.simulate_outage: bool = False
        self.put_calls: int = 0

    def _raise_if_outage(self):
        if self.simulate_outage:
            raise ClientError(
                {"Error": {"Code": "ServiceUnavailable", "Message": "Simulated R2 outage"}},
                "S3Operation",
            )

    @staticmethod
    def _not_found():
        return ClientError(
            {
                "Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            },
            "GetObject",
        )

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str, Metadata: Dict[str, str]):
        self._raise_if_outage()
        self.put_calls += 1
        self.objects[(Bucket, Key)] = {
            "Body": bytes(Body),
            "ContentType": ContentType,
            "Metadata": dict(Metadata),
            "ContentLength": len(Body),
        }
        return {"ETag": compute_sha256_hex(Body)}

    def get_object(self, Bucket: str, Key: str):
        self._raise_if_outage()
        entry = self.objects.get((Bucket, Key))
        if entry is None:
            raise self._not_found()
        return {
            "Body": _FakeS3Body(entry["Body"]),
            "ContentType": entry["ContentType"],
            "Metadata": dict(entry["Metadata"]),
            "ContentLength": entry["ContentLength"],
        }

    def head_object(self, Bucket: str, Key: str):
        self._raise_if_outage()
        entry = self.objects.get((Bucket, Key))
        if entry is None:
            raise self._not_found()
        return {
            "ContentType": entry["ContentType"],
            "Metadata": dict(entry["Metadata"]),
            "ContentLength": entry["ContentLength"],
        }

    def delete_object(self, Bucket: str, Key: str):
        self._raise_if_outage()
        self.objects.pop((Bucket, Key), None)
        return {}

    def generate_presigned_url(self, ClientMethod: str, Params: Dict[str, Any], ExpiresIn: int):
        self._raise_if_outage()
        bucket = Params["Bucket"]
        key = Params["Key"]
        return f"https://fake-r2.example.invalid/{bucket}/{key}?X-Amz-Expires={ExpiresIn}"


def _login(client, email: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (24, 24), color=(120, 40, 200))
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneManufacturer"
    exif[0x0110] = "PrivateGPSDeviceModel"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def test_storage_config_guards_against_missing_r2_creds_and_ephemeral_fallback():
    with pytest.raises(ValueError, match="requires non-empty credentials/endpoint"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="prod-strong-secret-key-with-at-least-thirty-two-bytes",
            DATABASE_URL="postgresql://u:p@localhost:5432/civicfix",
            STORAGE_BACKEND="r2",
            R2_BUCKET_NAME="",
        )

    with pytest.raises(ValueError, match="REQUIRE_DURABLE_STORAGE=True"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="prod-strong-secret-key-with-at-least-thirty-two-bytes",
            DATABASE_URL="postgresql://u:p@localhost:5432/civicfix",
            STORAGE_BACKEND="local",
            REQUIRE_DURABLE_STORAGE=True,
        )

    cfg = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="prod-strong-secret-key-with-at-least-thirty-two-bytes",
        DATABASE_URL="postgresql://u:p@localhost:5432/civicfix",
        STORAGE_BACKEND="r2",
        R2_ACCOUNT_ID="acct123",
        R2_BUCKET_NAME="civicfix-evidence",
        R2_ACCESS_KEY_ID="r2_test_access_id",
        R2_SECRET_ACCESS_KEY="r2_test_secret_value",
    )
    assert cfg.R2_ENDPOINT_URL == "https://acct123.r2.cloudflarestorage.com"


def test_r2_upload_exif_strip_rbac_signed_url_and_outage_isolation(client, test_actors, db_session, monkeypatch):
    fake_s3 = FakeS3Client()
    r2_backend = S3CompatibleStorageBackend(
        bucket_name="civicfix-private-bucket",
        access_key_id="k",
        secret_access_key="s",
        endpoint_url="https://acct.r2.cloudflarestorage.com",
        provider_name="r2",
        client=fake_s3,
    )
    monkeypatch.setattr("app.services.storage.service.settings.STORAGE_BACKEND", "r2")
    monkeypatch.setattr(storage_service, "_cloud_backend", r2_backend)

    adm = test_actors["admin"]
    roads = test_actors["staff_roads"]
    lighting = test_actors["staff_lighting"]
    crew_a = test_actors["crew_a"]
    crew_b = test_actors["crew_b"]
    c_a = test_actors["citizen_a"]
    c_b = test_actors["citizen_b"]

    t_adm = _login(client, adm["email"], adm["password"])["access_token"]
    t_roads = _login(client, roads["email"], roads["password"])["access_token"]
    t_light = _login(client, lighting["email"], lighting["password"])["access_token"]
    t_crew_a = _login(client, crew_a["email"], crew_a["password"])["access_token"]
    limiter._storage.reset()
    t_crew_b = _login(client, crew_b["email"], crew_b["password"])["access_token"]
    t_c_a = _login(client, c_a["email"], c_a["password"])["access_token"]
    t_c_b = _login(client, c_b["email"], c_b["password"])["access_token"]

    comp = client.post("/api/v1/complaints", json={
        "title": "Deep pothole near arterial flyover ramp",
        "description": "Severe asphalt crater damaging commuters' suspension.",
        "category": "ROADS",
        "latitude": 17.441,
        "longitude": 78.491,
    }, headers=_headers(t_c_a)).json()
    cid = comp["id"]

    # Assign WorkOrder to Crew A
    wo_resp = client.post("/api/v1/admin/work-orders", json={
        "complaint_id": cid,
        "department_id": test_actors["departments"]["ROADS"].id,
        "crew_id": crew_a["user"].id,
        "title": "Patch ramp crater",
        "instructions": "Fill with hot mix.",
    }, headers=_headers(t_roads))
    assert wo_resp.status_code == 201

    # Invalid MIME and corrupt image rejected cleanly
    bad_mime = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("script.exe", b"MZ...", "application/octet-stream")},
        data={"attachment_type": "CITIZEN_ORIGINAL"},
        headers=_headers(t_c_a),
    )
    assert bad_mime.status_code == 400

    corrupt_img = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("corrupt.jpg", b"not-a-valid-jpeg", "image/jpeg")},
        data={"attachment_type": "CITIZEN_ORIGINAL"},
        headers=_headers(t_c_a),
    )
    assert corrupt_img.status_code == 400

    # Valid JPEG with EXIF uploaded to private R2 (NOT local disk)
    exif_bytes = _make_jpeg_with_exif()
    up_resp = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("../../evil_name.jpg", exif_bytes, "image/jpeg")},
        data={"attachment_type": "CITIZEN_ORIGINAL"},
        headers=_headers(t_c_a),
    )
    assert up_resp.status_code == 200, up_resp.text
    att = up_resp.json()
    assert att["storage_provider"] == "r2"
    assert att["storage_verification_status"] == "VERIFIED"
    assert len(att["sha256_checksum"]) == 64

    db_att = db_session.query(ComplaintAttachment).filter(ComplaintAttachment.id == att["id"]).first()
    assert db_att.storage_object_key.startswith("complaints/")
    stored_blob = fake_s3.objects[("civicfix-private-bucket", db_att.storage_object_key)]["Body"]

    # Confirm EXIF metadata was stripped in stored R2 blob
    decoded = Image.open(io.BytesIO(stored_blob))
    assert len(decoded.getexif()) == 0
    # Confirm nothing written locally
    assert not (storage_service.complaint_dir / Path(db_att.storage_object_key).name).exists()

    # Private authorization enforcement on both endpoints
    for url in [f"/api/v1/evidence/{att['id']}", att["file_path"]]:
        assert client.get(url).status_code == 401
        r_ca = client.get(url, headers=_headers(t_c_a))
        assert r_ca.status_code == 200
        assert r_ca.content == stored_blob
        assert client.get(url, headers=_headers(t_c_b)).status_code == 403
        assert client.get(url, headers=_headers(t_crew_a)).status_code == 200
        assert client.get(url, headers=_headers(t_crew_b)).status_code == 403
        assert client.get(url, headers=_headers(t_roads)).status_code == 200
        assert client.get(url, headers=_headers(t_light)).status_code == 403
        assert client.get(url, headers=_headers(t_adm)).status_code == 200

    # Short-lived signed URL only returned when authorized
    assert client.get(f"/api/v1/evidence/{att['id']}?signed=true", headers=_headers(t_c_b)).status_code == 403
    signed_ok = client.get(f"/api/v1/evidence/{att['id']}?signed=true", headers=_headers(t_c_a))
    assert signed_ok.status_code == 200
    assert "X-Amz-Expires=300" in signed_ok.json()["signed_url"]

    # Internal evidence uploaded directly onto R2 stays hidden from citizen
    internal_key = "evidence/internal_audit_check.png"
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color=(20, 30, 40)).save(buf, format="PNG")
    r2_backend.put_bytes(internal_key, buf.getvalue(), "image/png")
    internal_att = ComplaintAttachment(
        complaint_id=cid,
        file_name="internal_audit_check.png",
        file_path=f"/uploads/{internal_key}",
        file_size=len(buf.getvalue()),
        mime_type="image/png",
        attachment_type="INTERNAL_STAFF_EVIDENCE",
        is_internal=True,
        uploaded_by_id=roads["user"].id,
        storage_provider="r2",
        storage_object_key=internal_key,
        sha256_checksum=compute_sha256_hex(buf.getvalue()),
        storage_verification_status="VERIFIED",
    )
    db_session.add(internal_att)
    db_session.commit()
    assert client.get(f"/api/v1/evidence/{internal_att.id}", headers=_headers(t_c_a)).status_code == 403
    assert client.get(f"/api/v1/evidence/{internal_att.id}", headers=_headers(t_roads)).status_code == 200

    # Missing object -> 404
    fake_s3.objects.pop(("civicfix-private-bucket", db_att.storage_object_key))
    assert client.get(f"/api/v1/evidence/{att['id']}", headers=_headers(t_c_a)).status_code == 404

    # Simulated R2 outage -> 503 (never silently falls back to local)
    fake_s3.simulate_outage = True
    assert client.get(f"/api/v1/evidence/{att['id']}", headers=_headers(t_c_a)).status_code == 503
    outage_upload = client.post(
        f"/api/v1/complaints/{cid}/attachments",
        files={"file": ("retry.jpg", exif_bytes, "image/jpeg")},
        data={"attachment_type": "CITIZEN_ORIGINAL"},
        headers=_headers(t_c_a),
    )
    assert outage_upload.status_code == 503


def test_legacy_upload_migration_dry_run_idempotent_recovery_and_missing_files(db_session, test_actors, tmp_path):
    c_a = test_actors["citizen_a"]["user"]
    comp = Complaint(
        reference_number="CF-2026-MIGRATE01",
        citizen_id=c_a.id,
        title="Legacy attachment migration test case",
        description="Simulating local files pre-R2 migration.",
        category=ComplaintCategory.ROADS.value,
        latitude=17.44,
        longitude=78.49,
        status=ComplaintStatus.UNDER_REVIEW.value,
        priority="P3",
    )
    db_session.add(comp)
    db_session.flush()

    local_root = tmp_path / "legacy_uploads"
    local_backend = LocalStorageBackend(local_root)
    local_backend.ensure_directories()

    blob_1 = b"legacy-evidence-bytes-one"
    blob_2 = b"legacy-evidence-bytes-two"
    local_backend.put_bytes("complaints/legacy_one.jpg", blob_1, "image/jpeg")
    local_backend.put_bytes("complaints/legacy_two.jpg", blob_2, "image/jpeg")

    att_1 = ComplaintAttachment(
        complaint_id=comp.id,
        file_name="legacy_one.jpg",
        file_path="/uploads/complaints/legacy_one.jpg",
        file_size=len(blob_1),
        mime_type="image/jpeg",
        uploaded_by_id=c_a.id,
        storage_provider="local",
    )
    att_2 = ComplaintAttachment(
        complaint_id=comp.id,
        file_name="legacy_two.jpg",
        file_path="/uploads/complaints/legacy_two.jpg",
        file_size=len(blob_2),
        mime_type="image/jpeg",
        uploaded_by_id=c_a.id,
        storage_provider="local",
    )
    att_missing = ComplaintAttachment(
        complaint_id=comp.id,
        file_name="lost_ephemeral.jpg",
        file_path="/uploads/complaints/lost_ephemeral.jpg",
        file_size=1234,
        mime_type="image/jpeg",
        uploaded_by_id=c_a.id,
        storage_provider="local",
    )
    db_session.add_all([att_1, att_2, att_missing])
    db_session.commit()

    fake_s3 = FakeS3Client()
    r2_backend = S3CompatibleStorageBackend(
        bucket_name="civicfix-migrate-bucket",
        access_key_id="k",
        secret_access_key="s",
        endpoint_url="https://acct.r2.cloudflarestorage.com",
        provider_name="r2",
        client=fake_s3,
    )

    # 1. Dry-run makes zero cloud or DB mutations
    dry_report = migrate_local_uploads_to_cloud(
        db=db_session,
        local_backend=local_backend,
        target_backend=r2_backend,
        dry_run=True,
    )
    assert dry_report.total_candidates == 3
    assert dry_report.uploaded_verified == 2
    assert dry_report.missing_local_source == 1
    assert len(fake_s3.objects) == 0

    # 2. Simulate interrupted previous run where legacy_one already landed in R2 before crash
    r2_backend.put_bytes("complaints/legacy_one.jpg", blob_1, "image/jpeg")
    puts_before_resume = fake_s3.put_calls

    # Unsafe deletion without double approval blocked
    with pytest.raises(ValueError, match="approve_local_deletion=True"):
        migrate_local_uploads_to_cloud(
            db=db_session,
            local_backend=local_backend,
            target_backend=r2_backend,
            dry_run=False,
            delete_local=True,
            approve_local_deletion=False,
        )

    # 3. Execute idempotent resumable migration (preserves local files when delete_local=False)
    exec_report = migrate_local_uploads_to_cloud(
        db=db_session,
        local_backend=local_backend,
        target_backend=r2_backend,
        dry_run=False,
        delete_local=False,
    )
    assert exec_report.already_exists_verified == 1
    assert exec_report.uploaded_verified == 1
    assert exec_report.missing_local_source == 1
    assert exec_report.failed == 0
    assert exec_report.local_deleted == 0
    # Only legacy_two triggered a new put_object
    assert fake_s3.put_calls == puts_before_resume + 1
    assert local_backend.exists("complaints/legacy_one.jpg")
    assert local_backend.exists("complaints/legacy_two.jpg")

    db_session.refresh(att_1)
    db_session.refresh(att_2)
    db_session.refresh(att_missing)
    assert att_1.storage_provider == "r2"
    assert att_1.sha256_checksum == compute_sha256_hex(blob_1)
    assert att_2.storage_provider == "r2"
    assert att_2.storage_verification_status == "VERIFIED"
    assert att_missing.storage_provider == "local"
    assert att_missing.storage_verification_status == "MISSING_SOURCE"
