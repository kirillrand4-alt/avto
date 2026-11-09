# -*- coding: utf-8 -*-
"""Контрольная SMTP-проба БЕЗ записи в базы (владелец 09.11: «проба возможно не работает из-за VPN»):
те же mail_from/helo/source_ip, что у панельной пробы; RCPT по адресам из аргументов, печать кода и
ответа сервера. Плюс внешний IP сервера. addr_probe/enrich/obzvon НЕ трогаем.
    proba_test_mailru.py адрес [адрес…]"""
import smtplib, socket, sys, urllib.request
sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe   # noqa: E402
from sender.config import Config                 # noqa: E402
from sender.store import Store                   # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
p = build_addr_probe(Store(cfg.get("service.db_path", r"C:\sender\sender.db")), cfg)
p = getattr(p, "probe_", p)
try: print("внешний IP:", urllib.request.urlopen("https://api.ipify.org", timeout=10).read().decode())
except Exception as e: print("внешний IP: не узнал", str(e)[:80])
print("helo=%r source_ip=%r mail_from задан=%s timeout=%s" % (getattr(p, "helo", None), getattr(p, "source_ip", None), bool(getattr(p, "mail_from", "")), getattr(p, "timeout", None)))
ОТ = next((a.split("=",1)[1] for a in sys.argv[1:] if a.startswith("from=")), None)
print("MAIL FROM:", ОТ or "(как у пробы)")
for адрес in [a for a in sys.argv[1:] if not a.startswith("from=")]:
    дом = адрес.split("@")[-1]; хост = p.mx_for(дом); код, ответ = None, ""
    try:
        with smtplib.SMTP(хост, 25, timeout=p.timeout or 20, local_hostname=p.helo or None,
                          source_address=((p.source_ip, 0) if p.source_ip else None)) as s:
            s.ehlo_or_helo_if_needed()
            try:
                if s.has_extn("starttls"): s.starttls(); s.ehlo()
            except Exception: pass
            s.mail(ОТ if ОТ is not None else (p.mail_from or ""))
            код, сырой = s.rcpt(адрес); ответ = (сырой or b"").decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        ответ = "ОШИБКА: " + str(e)[:150]
    print("%-36s MX %-22s → %s %s" % (адрес, хост, код, ответ[:140].replace("\n", " ")))
