# -*- coding: utf-8 -*-
"""Заголовки проверки подлинности (Authentication-Results, DKIM, SPF, спам-метки) письма в нашем ящике
по UID: zagolovki_pisma.py <ящик> <UID> [папка=INBOX]. Только чтение (PEEK)."""
import imaplib, os, re, sys
sys.path.insert(0, r"C:\sender")
for с in open(r"C:\sender\panel.env", encoding="utf-8", errors="replace").read().splitlines():
    if "=" in с and not с.strip().startswith("#"):
        к, з = с.split("=", 1); os.environ.setdefault(к.strip(), з.strip().strip('"'))
from sender.config import Config  # noqa: E402
ЯЩ, UID = sys.argv[1], sys.argv[2]; ПАП = sys.argv[3] if len(sys.argv) > 3 else "INBOX"
cfg = Config.load(r"C:\sender\sender.yaml")
mb = next(m for m in cfg.mailboxes() if m.mailbox_id == ЯЩ)
im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25); im.login(mb.login, os.getenv(mb.password_env, ""))
im.select(ПАП, readonly=True)
сыр = next(ч[1] for ч in im.uid("FETCH", UID, "(BODY.PEEK[HEADER])")[1] if isinstance(ч, tuple)).decode("utf-8", "replace")
сыр = re.sub(r"\r?\n[ \t]+", " ", сыр)
for с in сыр.splitlines():
    if re.match(r"(?i)(authentication-results|received-spf|x-yandex-spam|x-spam|dkim-signature|from|x-yandex-fwd|arc-authentication)", с):
        print(с[:300])
im.logout()
