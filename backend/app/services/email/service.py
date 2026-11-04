import asyncio
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List

from app.core.config import settings

logger = logging.getLogger(__name__)

class EmailDeliveryError(Exception):
    """Raised when SMTP email delivery fails after retries."""
    pass

class EmailService:
    """
    Robust, production-grade SMTP email delivery service.
    Supports asynchronous background sending, bounded retries, STARTTLS / SSL transports,
    templated notifications, and fail-safe error isolation.
    """

    def is_configured(self) -> bool:
        """Returns True only when EMAIL_ENABLED is True and SMTP_HOST is non-empty."""
        return bool(settings.EMAIL_ENABLED and settings.SMTP_HOST)

    async def _send_raw_email(self, to_email: str, subject: str, html_body: str, text_body: str) -> bool:
        """Internal low-level SMTP sender with bounded retries and timeout."""
        if not self.is_configured():
            logger.info(
                "[EMAIL SIMULATED] EMAIL_ENABLED=False. Email to <%s> not transmitted over network. Subject: '%s'",
                to_email, subject
            )
            return True

        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
        msg["To"] = to_email

        # Attach text and html parts
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                smtp_client = aiosmtplib.SMTP(
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    use_tls=settings.SMTP_USE_SSL,
                    start_tls=settings.SMTP_USE_TLS,
                    timeout=settings.SMTP_TIMEOUT_SECONDS
                )
                await smtp_client.connect()

                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    await smtp_client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

                await smtp_client.send_message(msg)
                await smtp_client.quit()

                logger.info("Email successfully delivered to <%s> on attempt %d: '%s'", to_email, attempt, subject)
                return True

            except Exception as exc:
                logger.warning(
                    "SMTP delivery attempt %d to <%s> failed: %s",
                    attempt, to_email, str(exc)
                )
                if attempt == max_retries:
                    logger.error("Failed to deliver email to <%s> after %d attempts.", to_email, max_retries)
                    return False
                await asyncio.sleep(1.0)

        return False

    def _render_base_html(self, title: str, content_html: str, action_url: Optional[str] = None, action_text: Optional[str] = None) -> str:
        action_button = ""
        if action_url and action_text:
            action_button = f"""
            <div style="margin: 28px 0; text-align: center;">
              <a href="{action_url}" style="background-color: #1e3a8a; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">
                {action_text}
              </a>
            </div>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #0f172a; margin: 0; padding: 0; }}
    .container {{ max-width: 600px; margin: 30px auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }}
    .header {{ background-color: #1e3a8a; padding: 24px; text-align: center; color: #ffffff; }}
    .header h2 {{ margin: 0; font-size: 20px; font-weight: 700; }}
    .body {{ padding: 32px 28px; line-height: 1.6; font-size: 15px; color: #334155; }}
    .footer {{ background-color: #f1f5f9; padding: 16px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; background: #e0f2fe; color: #0369a1; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2>CivicFix AI — Municipal Operations</h2>
    </div>
    <div class="body">
      <h3 style="color: #1e3a8a; margin-top: 0;">{title}</h3>
      {content_html}
      {action_button}
    </div>
    <div class="footer">
      <p style="margin: 0 0 6px 0;">CivicFix AI Platform &bull; Report. Resolve. Rebuild Trust.</p>
      <p style="margin: 0;">This is an automated notification from your municipal administration. Please do not reply directly.</p>
    </div>
  </div>
</body>
</html>"""

    async def send_submission_acknowledgment(
        self,
        to_email: str,
        citizen_name: str,
        reference_number: str,
        title: str,
        category: str,
        complaint_id: str
    ) -> bool:
        """Sends complaint submission acknowledgment with tracking reference number."""
        action_url = f"{settings.PUBLIC_APP_URL}/complaints/{complaint_id}"
        subject = f"[CivicFix AI] Complaint Received: #{reference_number}"
        
        content_html = f"""
        <p>Dear {citizen_name},</p>
        <p>Your civic complaint has been registered into the municipal dispatch system.</p>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 20px 0;">
          <p style="margin: 0 0 8px 0;"><strong>Tracking Reference:</strong> <span class="badge">#{reference_number}</span></p>
          <p style="margin: 0 0 8px 0;"><strong>Issue Title:</strong> {title}</p>
          <p style="margin: 0;"><strong>Category:</strong> {category}</p>
        </div>
        <p>Our automated AI triage pipeline is assessing the issue location and severity to route it to the appropriate department.</p>
        """

        text_body = (
            f"Dear {citizen_name},\n\n"
            f"Your civic complaint #{reference_number} has been received.\n"
            f"Title: {title}\n"
            f"Category: {category}\n\n"
            f"Track your complaint online: {action_url}\n"
        )

        html_body = self._render_base_html(
            title="Complaint Submission Acknowledged",
            content_html=content_html,
            action_url=action_url,
            action_text="Track Complaint Progress"
        )

        return await self._send_raw_email(to_email, subject, html_body, text_body)

    async def send_status_update(
        self,
        to_email: str,
        recipient_name: str,
        reference_number: str,
        old_status: str,
        new_status: str,
        reason: Optional[str],
        complaint_id: str
    ) -> bool:
        """Sends status change notification to reporting citizen."""
        action_url = f"{settings.PUBLIC_APP_URL}/complaints/{complaint_id}"
        subject = f"[CivicFix AI] Status Update on #{reference_number}: {new_status}"

        content_html = f"""
        <p>Dear {recipient_name},</p>
        <p>There is an update on your complaint <strong>#{reference_number}</strong>.</p>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 20px 0;">
          <p style="margin: 0 0 8px 0;"><strong>Previous Status:</strong> {old_status}</p>
          <p style="margin: 0 0 8px 0;"><strong>New Status:</strong> <span class="badge">{new_status}</span></p>
          {f'<p style="margin: 0;"><strong>Update Notes:</strong> {reason}</p>' if reason else ''}
        </div>
        """

        text_body = (
            f"Dear {recipient_name},\n\n"
            f"Status update on complaint #{reference_number}:\n"
            f"From: {old_status} -> To: {new_status}\n"
            f"Notes: {reason or 'Administrative update'}\n\n"
            f"View details: {action_url}\n"
        )

        html_body = self._render_base_html(
            title="Complaint Status Changed",
            content_html=content_html,
            action_url=action_url,
            action_text="View Complaint Details"
        )

        return await self._send_raw_email(to_email, subject, html_body, text_body)

    async def send_resolution_awaiting_verification(
        self,
        to_email: str,
        citizen_name: str,
        reference_number: str,
        completion_notes: str,
        complaint_id: str
    ) -> bool:
        """Stage 1 Resolution: Field crew submitted repair evidence, awaiting citizen verification."""
        action_url = f"{settings.PUBLIC_APP_URL}/complaints/{complaint_id}"
        subject = f"[Action Required] Repair Completed for Complaint #{reference_number}"

        content_html = f"""
        <p>Dear {citizen_name},</p>
        <p>The assigned field maintenance crew has finished remediation work on your complaint <strong>#{reference_number}</strong>.</p>
        <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 16px; margin: 20px 0;">
          <h4 style="color: #166534; margin: 0 0 8px 0;">Field Repair Summary:</h4>
          <p style="margin: 0; color: #15803d;">{completion_notes}</p>
        </div>
        <p><strong>Two-Stage Verification Required:</strong> Please inspect the before/after photographic evidence on the portal and confirm if you are satisfied with the resolution, or reopen the ticket if the problem persists.</p>
        """

        text_body = (
            f"Dear {citizen_name},\n\n"
            f"Repair work has been completed for #{reference_number}.\n"
            f"Crew Notes: {completion_notes}\n\n"
            f"Please visit the portal to verify the repair: {action_url}\n"
        )

        html_body = self._render_base_html(
            title="Work Completed — Citizen Verification Required",
            content_html=content_html,
            action_url=action_url,
            action_text="Inspect & Verify Repair"
        )

        return await self._send_raw_email(to_email, subject, html_body, text_body)

    async def send_resolution_confirmed_or_reopened(
        self,
        to_email: str,
        recipient_name: str,
        reference_number: str,
        is_satisfied: bool,
        notes: Optional[str],
        complaint_id: str
    ) -> bool:
        """Stage 2 Result: Citizen approved resolution or reopened ticket."""
        action_url = f"{settings.PUBLIC_APP_URL}/complaints/{complaint_id}"
        outcome_str = "Confirmed & Closed" if is_satisfied else "Contested & Reopened"
        subject = f"[CivicFix AI] Complaint #{reference_number} — {outcome_str}"

        content_html = f"""
        <p>Dear {recipient_name},</p>
        <p>Complaint <strong>#{reference_number}</strong> verification result:</p>
        <div style="background: {'#f0fdf4' if is_satisfied else '#fef2f2'}; border: 1px solid {'#bbf7d0' if is_satisfied else '#fecaca'}; border-radius: 6px; padding: 16px; margin: 20px 0;">
          <p style="margin: 0 0 8px 0;"><strong>Verification Result:</strong> {outcome_str}</p>
          {f'<p style="margin: 0;"><strong>Citizen Commentary:</strong> {notes}</p>' if notes else ''}
        </div>
        """

        text_body = (
            f"Complaint #{reference_number} was {outcome_str}.\n"
            f"Notes: {notes or 'N/A'}\n"
            f"Details: {action_url}\n"
        )

        html_body = self._render_base_html(
            title=f"Resolution {outcome_str}",
            content_html=content_html,
            action_url=action_url,
            action_text="View History"
        )

        return await self._send_raw_email(to_email, subject, html_body, text_body)

email_service = EmailService()

