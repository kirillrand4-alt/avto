# -*- coding: utf-8 -*-
"""Поиск писем в папках ящика по адресу (read-only): poisk_v_yashchike.py <ящик> <адрес>"""
import io
import os
import sys
BASE = r"C:\sender"
sys.path.insert(0, BASE)
for line in io.open(os.path.join(BASE, "panel.env"), encoding="utf-8", errors="replace").read().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))
from sender.config import Config            # noqa: E402
from sender.mailbrowser import MailBrowser  # noqa: E402
cfg = Config.load(os.path.join(BASE, "sender.yaml"))
mb = MailBrowser(cfg)
for п in mb.folders(sys.argv[1]):
    if п["role"] not in ("inbox", "sent"):
        continue
    р = mb.messages(sys.argv[1], folder=п["name"], limit=20, search=sys.argv[2])
    for m in р.get("messages") or р.get("items") or []:
        print(п["role"], m.get("date_iso", "")[:16], m.get("from_addr"), "->", m.get("to_addr"), "|", (m.get("subject") or "")[:60],
              "| msgid", (m.get("message_id") or "")[:50], "| irt", (m.get("in_reply_to") or "")[:50])
