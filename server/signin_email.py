"""Self-contained sign-in email: no remote images, fonts or tracking pixels."""

from email.message import EmailMessage
from html import escape


def message(address, code, link):
    result = EmailMessage()
    result["From"] = "GabbaProc <gabbaproc@kellerkind.info>"
    result["To"] = address
    result["Subject"] = "GabbaProc: Dein Anmeldecode / Your sign-in code"
    result.set_content(
        f"GABBAPROC\n\nDein Anmeldecode / Your sign-in code: {code}\n\n"
        f"Anmeldung öffnen / Open sign-in:\n{link}\n\n"
        "Der Link füllt deinen Code vor. Bestätige die Anmeldung auf der Website.\n"
        "Gültig für 10 Minuten, nur im Browser, in dem du den Code angefordert hast.\n"
        "Du kannst den Code auch in die bereits geöffnete Kontoseite eingeben.\n\n"
        "The link fills in your code. Confirm sign-in on the website.\n"
        "Valid for 10 minutes, only in the browser where you requested it.\n"
        "You can also enter the code on the account page you already opened.\n\n"
        "Nicht angefordert? Ignoriere diese Nachricht. Teile weder Link noch Code.\n"
        "Didn't request this? Ignore this message. Do not share the link or code.\n"
    )
    result.add_alternative(
        f'''<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#0b1320;color:#e8eef7;font-family:Arial,Helvetica,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;">Dein Zugang zu GabbaProc. Der Code ist 10 Minuten gültig. / Your code is valid for 10 minutes.</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#0b1320;"><tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="560" cellspacing="0" cellpadding="0" style="width:100%;max-width:560px;">
<tr><td style="padding:0 8px 22px;font-size:23px;font-weight:bold;letter-spacing:1px;color:#fbbf55;">⚡ GabbaProc</td></tr>
<tr><td style="background-color:#172438;border:1px solid #304962;border-radius:16px;padding:32px 28px;">
<p style="margin:0 0 12px;color:#82e0d3;font-size:12px;font-weight:bold;letter-spacing:2px;">DEIN KONTO · YOUR ACCOUNT</p>
<h1 style="margin:0 0 14px;font-size:27px;line-height:1.25;color:#ffffff;">Willkommen bei GabbaProc</h1>
<p style="margin:0 0 24px;font-size:16px;line-height:1.6;color:#bac8dc;">Mit diesem Code meldest du dich an.<br><span lang="en">Use this code to sign in.</span></p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:22px 8px;background-color:#0d1a2b;border:1px solid #38536f;border-radius:10px;">
<span style="font-family:Consolas,monospace;font-size:32px;letter-spacing:5px;font-weight:bold;color:#fbbf55;">{escape(code)}</span>
</td></tr></table>
<p style="margin:12px 0 24px;text-align:center;color:#bac8dc;font-size:13px;">10 Minuten gültig · Valid for 10 minutes</p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="background-color:#82e0d3;border-radius:8px;">
<a href="{escape(link, quote=True)}" style="display:block;padding:17px 12px;color:#09242a;text-decoration:none;font-size:16px;font-weight:bold;">Bei GabbaProc anmelden · Sign in</a>
</td></tr></table>
<p style="margin:22px 0 12px;font-size:14px;line-height:1.65;color:#bac8dc;">Der Button öffnet die Kontoseite und füllt den Code vor. Bestätige ihn dort. Nutze denselben Browser, in dem du die Anmeldung gestartet hast.</p>
<p lang="en" style="margin:0 0 22px;font-size:14px;line-height:1.65;color:#bac8dc;">The button opens your account page and fills in the code. Confirm it there, using the same browser where you started signing in.</p>
<p style="margin:0;padding-top:20px;border-top:1px solid #304962;font-size:13px;line-height:1.6;color:#bac8dc;">Du kannst den Code auch direkt auf der geöffneten Kontoseite eingeben.<br><span lang="en">You can also enter the code on the account page you already opened.</span></p>
</td></tr>
<tr><td style="padding:22px 12px;font-size:12px;line-height:1.7;color:#9db0c9;">Nicht angefordert? Ignoriere diese E-Mail. Teile weder Link noch Code.<br><span lang="en">Didn't request this? Ignore this email. Do not share the link or code.</span><br><br>GabbaProc · Community proc research<br><a href="https://gabbaproc.kellerkind.info/privacy.html" style="color:#82e0d3;">Datenschutz / Privacy</a> · <a href="https://gabbaproc.kellerkind.info/imprint.html" style="color:#82e0d3;">Impressum / Legal notice</a></td></tr>
</table></td></tr></table></body></html>''',
        subtype="html",
    )
    return result
