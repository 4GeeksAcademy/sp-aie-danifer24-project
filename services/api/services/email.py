import json
import logging
import os
from html import escape
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


def send_reset_email(email: str, token: str) -> None:
	try:
		api_key = os.environ.get("RESEND_API_KEY")
		sender = os.environ.get("RESEND_FROM_EMAIL")
		reset_url = os.environ.get("PASSWORD_RESET_URL")
		if not api_key or not sender or not reset_url:
			raise ValueError("Email configuration missing")
		parsed_url = urlsplit(reset_url)
		if parsed_url.scheme not in ("https", "http") or not parsed_url.netloc or parsed_url.query or parsed_url.fragment:
			raise ValueError("Invalid reset URL configuration")
		link = f"{reset_url}?{urlencode({'token': token})}"
		html = f"""<!doctype html>
<html lang="es"><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:24px 16px;background:#f6f8f7;font-family:Arial,sans-serif;color:#212b29">
<div style="max-width:520px;margin:auto;background:white;padding:24px">
<h1 style="font-size:24px;line-height:1.3">Restablece tu contrase&ntilde;a</h1>
<p style="font-size:16px;line-height:1.6">Recibimos una solicitud para restablecer tu contrase&ntilde;a de Nexova. Este enlace caduca en 30 minutos y solo puede usarse una vez.</p>
<p><a href="{escape(link, quote=True)}" style="display:inline-block;background:#14745d;color:white;padding:14px 20px;text-decoration:none;border-radius:4px">Restablecer contrase&ntilde;a</a></p>
<p style="font-size:14px;line-height:1.6">Si no has solicitado este cambio, ignora este correo. Tu contrase&ntilde;a no cambiar&aacute;.</p>
<p style="font-size:14px;line-height:1.6;overflow-wrap:anywhere;word-break:break-all">Enlace alternativo: <a href="{escape(link, quote=True)}">{escape(link)}</a></p>
</div></body></html>"""
		body = json.dumps({
			"from": sender,
			"to": [email],
			"subject": "Restablece tu contrasena de Nexova",
			"html": html,
			"text": f"Restablece tu contrasena de Nexova: {link}\nEl enlace caduca en 30 minutos y es de un solo uso. Si no lo solicitaste, ignora este correo.",
		}).encode("utf-8")
		request = Request(
			"https://api.resend.com/emails",
			data=body,
			headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "Nexova/1.0"},
			method="POST",
		)
		with urlopen(request, timeout=10) as response:
			response.read()
	except Exception:
		logger.error("Password reset email delivery failed; check Resend configuration and availability.")