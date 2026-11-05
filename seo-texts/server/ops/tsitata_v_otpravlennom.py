# -*- coding: utf-8 -*-
"""Есть ли цитата первого письма в реально отправленном напоминании: ищем письмо на адрес
в «Отправленных» ящика и печатаем тело. tsitata_v_otpravlennom.py <ящик> <адрес>"""
import io, os, sys
BASE = r"C:\sender"
sys.path.insert(0, BASE)
for line in io.open(os.path.join(BASE, "panel.env"), encoding="utf-8", errors="replace").read().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))
from sender.config import Config            # noqa: E402
from sender.mailbrowser import MailBrowser  # noqa: E402
mb, кому = sys.argv[1], sys.argv[2].lower()
cfg = Config.load(os.path.join(BASE, "sender.yaml"))
mbr = MailBrowser(cfg)
print("ЦИТАТА-27.10 в sender.py:", "ЦИТАТА-27.10" in io.open(os.path.join(BASE, "sender", "sender.py"), encoding="utf-8").read())
for папка in (["INBOX"] if "--vhodyashchie" in sys.argv else ["Sent"]):
    try:
        р = mbr.messages(mb, folder=папка, limit=200)
    except Exception as ex:  # noqa: BLE001
        print(папка, "не читается:", str(ex)[:80]); continue
    for m in р.get("messages") or р.get("items") or []:
        if кому in str(m).lower():
            п = mbr.message(mb, folder=папка, uid=str(m.get("uid")))
            print("=== %s | %s | %s" % (папка, m.get("date_iso"), m.get("subject")))
            print((п.get("text") or п.get("body") or п.get("body_text") or str(п))[:5000])
            sys.exit(0)
    print(папка, ": письма на адрес не найдено среди", len(р.get("messages") or р.get("items") or []))
