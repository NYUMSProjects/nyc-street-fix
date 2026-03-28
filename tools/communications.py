import os
from twilio.rest import Client
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

def make_311_call(report_summary: str, phone_number: str = "2015510870") -> str:
    """
    Call the specified phone number to report the 311 incident via an automated voice system.
    Pass a short 'report_summary' (1-2 sentences) of what the agent should say to the 311 operator.
    """
    print(f"📞 [AGENT TOOL EXECUTION] -> make_311_call(phone_number='{phone_number}', summary='{report_summary[:50]}...')")
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    api_key = os.getenv("TWILIO_API_KEY_SID") or os.getenv("TWILIO_AUTH_TOKEN")
    api_secret = os.getenv("TWILIO_API_KEY_SECRET") or os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not account_sid or not api_key or not api_secret or not from_number:
        return f"[MOCK SUCCESS] Placed a simulated call to {phone_number}. Automated 311 voice report delivered: {report_summary} (Twilio keys missing)"

    try:
        client = Client(api_key, api_secret, account_sid)
        # We wrap the text in a Pause to give the person time to pick up and say "Hello"
        twiml_content = f"""<Response>
            <Pause length="2"/>
            <Say voice="alice">Hello. This is the NYC Street Fix AI Co-Pilot reporting an incident.</Say>
            <Say voice="alice">{report_summary}</Say>
            <Say voice="alice">This report has been logged in the 311 dashboard. Thank you and goodbye.</Say>
        </Response>"""
        
        call = client.calls.create(
            twiml=twiml_content,
            to="+1" + phone_number.replace("-", ""),
            from_=from_number
        )
        return f"Successfully called {phone_number}. Reference SID: {call.sid}. The AI summarized the issue: {report_summary}"
    except Exception as e:
        return f"Failed to call {phone_number}: {e}"

def send_311_sms(message: str, phone_number: str = "2015510870") -> str:
    """
    Send an SMS text message containing a brief summary of the 311 issue.
    If the user does not specify a phone number, use the default 201-551-0870.
    """
    print(f"💬 [AGENT TOOL EXECUTION] -> send_311_sms(phone_number='{phone_number}')")
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    api_key = os.getenv("TWILIO_API_KEY_SID") or os.getenv("TWILIO_AUTH_TOKEN")
    api_secret = os.getenv("TWILIO_API_KEY_SECRET") or os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not account_sid or not api_key or not api_secret or not from_number:
        return f"[MOCK SUCCESS] Sent simulated SMS to {phone_number}. Message: {message} (Twilio keys missing)"

    try:
        client = Client(api_key, api_secret, account_sid)
        msg = client.messages.create(
            body=message,
            to=f"+1{phone_number.replace('-', '')}",
            from_=from_number
        )
        return f"Successfully sent SMS to {phone_number}. Reference SID: {msg.sid}"
    except Exception as e:
        return f"Failed to send SMS to {phone_number}: {e}"

def send_311_email(subject: str, body: str, email_address: str = "lg4143@nyu.edu") -> str:
    """
    Send an email containing the full drafted 311 report or a detailed conversation summary. 
    """
    print(f"📧 [AGENT TOOL EXECUTION] -> send_311_email(to='{email_address}', subject='{subject}')")
    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    from_email = "lg4143@nyu.edu" # Usually SendGrid requires a verified sender identity.

    if not sendgrid_key:
        return f"[MOCK SUCCESS] Sent simulated Email to {email_address} with subject '{subject}'. (SendGrid key missing)"

    try:
        message = Mail(
            from_email=from_email,
            to_emails=email_address,
            subject=subject,
            plain_text_content=body
        )
        sg = SendGridAPIClient(sendgrid_key)
        response = sg.send(message)
        if response.status_code < 300:
            return f"Successfully sent email to {email_address} via SendGrid."
        else:
            return f"SendGrid returned status code {response.status_code}: {response.body}"
    except Exception as e:
        return f"Failed to send email to {email_address}: {e}"
