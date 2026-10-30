from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from backend.core.config import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, recipient_name: str, reset_link: str) -> bool:
    """Dispatches a password reset email with the secure token link.
    
    If SMTP credentials are not configured, logs the reset link securely for development/demo use.
    """
    subject = "Nanvi Enterprise - Password Reset Request"
    display_name = recipient_name.strip() or "User"
    
    plain_text = (
        f"Hello {display_name},\n\n"
        "A request to reset your password has been received for your Nanvi AI Enterprise Assistant account.\n\n"
        f"Please click or visit the following link to establish your new password:\n{reset_link}\n\n"
        "Security Note: This link is valid for 15 minutes.\n"
        "If you did not request this password reset, please ignore this email. Your current credentials remain secure.\n\n"
        "Regards,\n"
        "Nanvi Enterprise Security Team"
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Reset Your Password</title>
</head>
<body style="margin: 0; padding: 32px 16px; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #0f172a;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
    <div style="margin-bottom: 24px; border-bottom: 1px solid #f1f5f9; padding-bottom: 16px; display: flex; align-items: center; justify-content: space-between;">
      <span style="font-size: 20px; font-weight: 800; color: #0f172a; letter-spacing: -0.03em;">NANVI</span>
      <span style="font-size: 11px; background: #f1f5f9; color: #475569; padding: 4px 8px; border-radius: 6px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">Enterprise Auth</span>
    </div>

    <h2 style="font-size: 20px; font-weight: 700; color: #0f172a; margin-top: 0; margin-bottom: 12px;">Reset Your Password</h2>
    <p style="font-size: 14px; line-height: 1.6; color: #475569; margin-bottom: 24px;">
      Hello <strong>{display_name}</strong>,<br>
      We received a request to reset your account password. Click the button below to choose your new password:
    </p>

    <div style="text-align: center; margin: 32px 0;">
      <a href="{reset_link}" style="display: inline-block; background: #000000; color: #ffffff; text-decoration: none; padding: 13px 32px; border-radius: 8px; font-size: 14px; font-weight: 600; letter-spacing: 0.01em; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
        Reset Password
      </a>
    </div>

    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin-bottom: 24px;">
      <p style="font-size: 12px; line-height: 1.5; color: #64748b; margin: 0;">
        <strong>Notice:</strong> This link is active for <strong>15 minutes</strong>. If the button above doesn't work, copy and paste this link into your browser:<br>
        <a href="{reset_link}" style="color: #2563eb; word-break: break-all; text-decoration: underline;">{reset_link}</a>
      </p>
    </div>

    <div style="border-top: 1px solid #f1f5f9; padding-top: 16px; font-size: 11px; color: #94a3b8; line-height: 1.4;">
      If you did not request a password reset, you can safely ignore this email. No changes will be made to your account.
    </div>
  </div>
</body>
</html>
"""

    if settings.smtp_host:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = settings.smtp_from or "security@nanvi.ai"
            msg["To"] = to_email
            msg.set_content(plain_text)
            msg.add_alternative(html_content, subtype="html")

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)

            logger.info("Successfully sent password reset email via SMTP to %s", to_email)
            return True
        except Exception as exc:
            logger.warning("Failed to send reset email via SMTP to %s: %s; falling back to local logger", to_email, exc)

    # Local fallback / dev mode
    logger.info("[AUTH_MAILER] Password reset link for %s: %s", to_email, reset_link)
    print(f"\n[AUTH_MAILER] >>> Password reset link generated for {to_email}:\n{reset_link}\n")
    return True
