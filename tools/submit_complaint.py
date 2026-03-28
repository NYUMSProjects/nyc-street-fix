from __future__ import annotations

import structlog

from tools.communications import make_311_call, send_311_sms, send_311_email

logger = structlog.get_logger(__name__)

PHONE_NUMBER = "2015510870"
EMAIL_ADDRESS = "lg4143@nyu.edu"


async def submit_311_complaint(method: str, incident: dict) -> bool:
    """Submit a 311 complaint via the chosen method.

    Uses the same phone number for both SMS and Call.
    """
    complaint_text = incident.get("complaint_text", "")
    location = incident.get("location_text", "")
    agency = incident.get("likely_agency", "311")
    issue_type = incident.get("issue_type", "street issue").replace("_", " ")
    severity = incident.get("severity", "unknown")
    summary = incident.get("report_summary", complaint_text[:200])

    logger.info(
        "submit_311_complaint",
        method=method,
        agency=agency,
        location=location,
        complaint_preview=complaint_text[:80],
    )

    try:
        if method == "call":
            report_summary = (
                f"I am reporting a {issue_type} at {location}. "
                f"Severity is {severity}. {summary}"
            )
            result = make_311_call(report_summary=report_summary, phone_number=PHONE_NUMBER)
            logger.info("submit_311_complaint: call result", result=result)
            return "Failed" not in result

        elif method == "sms":
            message = (
                f"NYC 311 Report: {issue_type.title()}\n"
                f"Location: {location}\n"
                f"Severity: {severity.upper()}\n"
                f"Agency: {agency}\n\n"
                f"{complaint_text[:1000]}"
            )
            result = send_311_sms(message=message, phone_number=PHONE_NUMBER)
            logger.info("submit_311_complaint: sms result", result=result)
            return "Failed" not in result

        elif method == "email":
            subject = f"NYC 311 Report: {issue_type.title()} at {location}"
            body = (
                f"NYC StreetFix - Automated 311 Complaint\n"
                f"{'=' * 44}\n\n"
                f"Issue Type: {issue_type.title()}\n"
                f"Severity: {severity.upper()}\n"
                f"Location: {location}\n"
                f"Agency: {agency}\n\n"
                f"Complaint:\n{complaint_text}\n\n"
                f"Summary:\n{summary}\n"
            )
            result = send_311_email(subject=subject, body=body, email_address=EMAIL_ADDRESS)
            logger.info("submit_311_complaint: email result", result=result)
            return "Failed" not in result

        else:
            logger.warning("submit_311_complaint: unknown method", method=method)
            return False

    except Exception as e:
        logger.error("submit_311_complaint: exception", error=str(e), method=method)
        return False
