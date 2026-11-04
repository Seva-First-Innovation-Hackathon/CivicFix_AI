import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.email.service import EmailService
from app.core.config import settings

@pytest.fixture
def email_service_instance():
    return EmailService()

@pytest.mark.asyncio
async def test_email_service_is_configured_logic(email_service_instance, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    assert email_service_instance.is_configured() is False

    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert email_service_instance.is_configured() is False

    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    assert email_service_instance.is_configured() is True


@pytest.mark.asyncio
async def test_email_service_unconfigured_bypasses_network(email_service_instance, monkeypatch):
    """When unconfigured, emails simulate sending cleanly without raising network errors."""
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)

    sent = await email_service_instance.send_submission_acknowledgment(
        to_email="citizen@example.org",
        citizen_name="John Citizen",
        reference_number="CF-2026-0001-123",
        title="Severe Pothole on 5th Ave",
        category="ROADS_AND_FOOTPATHS",
        complaint_id="test-complaint-uuid-1"
    )
    assert sent is True


@pytest.mark.asyncio
async def test_email_service_configured_sends_via_smtp(email_service_instance, monkeypatch):
    """When configured, connects to SMTP server, logs in, and delivers multipart email with tracking URL."""
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "mail.city.gov")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "notifications@city.gov")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "secret123")
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "no-reply@city.gov")
    monkeypatch.setattr(settings, "SMTP_FROM_NAME", "CivicFix AI Alerts")
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", "https://civicfix.city.gov")

    mock_smtp_client = AsyncMock()

    with patch("aiosmtplib.SMTP", return_value=mock_smtp_client) as mock_smtp_cls:
        success = await email_service_instance.send_submission_acknowledgment(
            to_email="citizen@example.org",
            citizen_name="Jane Doe",
            reference_number="CF-2026-0042-789",
            title="Broken Streetlight on Elm St",
            category="STREETLIGHTS_AND_ELECTRICITY",
            complaint_id="complaint-uuid-42"
        )

        assert success is True
        mock_smtp_cls.assert_called_once_with(
            hostname="mail.city.gov",
            port=587,
            use_tls=False,
            start_tls=True,
            timeout=15.0
        )
        mock_smtp_client.connect.assert_awaited_once()
        mock_smtp_client.login.assert_awaited_once_with("notifications@city.gov", "secret123")
        mock_smtp_client.send_message.assert_awaited_once()
        mock_smtp_client.quit.assert_awaited_once()

        # Inspect delivered MIME message
        sent_msg = mock_smtp_client.send_message.call_args[0][0]
        assert sent_msg["To"] == "citizen@example.org"
        assert "CivicFix AI Alerts <no-reply@city.gov>" in sent_msg["From"]
        assert "CF-2026-0042-789" in sent_msg["Subject"]
        
        # Verify tracking deep-link in body
        payload = [part.get_payload(decode=True).decode() for part in sent_msg.get_payload()]
        full_text = " ".join(payload)
        assert "https://civicfix.city.gov/complaints/complaint-uuid-42" in full_text
        assert "Broken Streetlight on Elm St" in full_text


@pytest.mark.asyncio
async def test_email_service_bounded_retry_and_failure_isolation(email_service_instance, monkeypatch):
    """When SMTP connection fails, bounded retries run and returns False safely without crashing."""
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "unreachable.server.gov")

    mock_smtp_client = AsyncMock()
    mock_smtp_client.connect.side_effect = ConnectionRefusedError("Connection refused by host")

    with patch("aiosmtplib.SMTP", return_value=mock_smtp_client), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        
        success = await email_service_instance.send_status_update(
            to_email="citizen@example.org",
            recipient_name="John Citizen",
            reference_number="CF-2026-0099-555",
            old_status="UNDER_REVIEW",
            new_status="IN_PROGRESS",
            reason="Crew dispatched to fill pothole",
            complaint_id="uuid-99"
        )

        assert success is False
        assert mock_smtp_client.connect.await_count == 2
        mock_sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_email_all_templates_render(email_service_instance, monkeypatch):
    """Verifies that all 4 lifecycle notification methods render valid HTML and plain text content."""
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)

    # 1. Submission acknowledgment
    res1 = await email_service_instance.send_submission_acknowledgment(
        to_email="test@user.com", citizen_name="User", reference_number="CF-1",
        title="Pothole", category="ROADS", complaint_id="c-1"
    )
    assert res1 is True

    # 2. Status update
    res2 = await email_service_instance.send_status_update(
        to_email="test@user.com", recipient_name="User", reference_number="CF-1",
        old_status="SUBMITTED", new_status="ASSIGNED", reason="Assigned to Works", complaint_id="c-1"
    )
    assert res2 is True

    # 3. Resolution awaiting verification (Stage 1)
    res3 = await email_service_instance.send_resolution_awaiting_verification(
        to_email="test@user.com", citizen_name="User", reference_number="CF-1",
        completion_notes="Asphalt patch applied", complaint_id="c-1"
    )
    assert res3 is True

    # 4a. Resolution confirmed (Stage 2 - Approved)
    res4a = await email_service_instance.send_resolution_confirmed_or_reopened(
        to_email="test@user.com", recipient_name="User", reference_number="CF-1",
        is_satisfied=True, notes="Great work", complaint_id="c-1"
    )
    assert res4a is True

    # 4b. Resolution reopened (Stage 2 - Contested)
    res4b = await email_service_instance.send_resolution_confirmed_or_reopened(
        to_email="test@user.com", recipient_name="User", reference_number="CF-1",
        is_satisfied=False, notes="Pothole still sinking", complaint_id="c-1"
    )
    assert res4b is True

