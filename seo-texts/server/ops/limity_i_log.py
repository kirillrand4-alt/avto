# -*- coding: utf-8 -*-
"""Лимит дня ящика v.kuzmin и соседей + следы автоотправки в логе службы.
Только чтение (sqlite mode=ro, реестр nssm, хвост лога)."""
import io
import json
import os
import re
import sqlite3
import subprocess
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.ramp import daily_send_limit                         # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
c = sqlite3.connect(r"file:C:/sender/sender.db?mode=ro", uri=True, timeout=30)
c.row_factory = sqlite3.Row
р = c.execute("SELECT value FROM panel_settings WHERE key='send_limits'").fetchone()
лимиты = json.loads(р[0]) if р and р[0] else {}
print("send_limits: all=%s per_mailbox=%s" % (лимиты.get("all"), len(лимиты.get("per_mailbox") or {})))
for мб in cfg.mailboxes():
    if мб.mailbox_id not in ("v.kuzmin@inspection-systems.ru", "i.belyaev@inspection-systems.ru",
                             "a.miroshnichenko@optic-sort.ru"):
        continue
    ст = c.execute("SELECT ramp_day, day_key, sent_today FROM mailbox_state WHERE mailbox_id=?",
                   (мб.mailbox_id,)).fetchone()
    рд = (ст["ramp_day"] + 1) if ст else 0
    база = daily_send_limit(cfg, мб.provider, рд)
    кап = (лимиты.get("per_mailbox") or {}).get(мб.mailbox_id, лимиты.get("all"))
    print("   %s provider=%s ramp_day(сегодня)=%s рампа=%s потолок=%s -> лимит %s"
          % (мб.mailbox_id, мб.provider, рд, база, кап,
             база if кап is None else min(база, int(кап))))

ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                     r"$p=Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\SenderPanel\Parameters'; $p.AppStdout; $p.AppStderr"],
                    capture_output=True, text=True, encoding="cp866", errors="replace").stdout.split()
print("логи службы: %s" % ps)
for лог in dict.fromkeys(ps):
    if not os.path.exists(лог):
        continue
    with io.open(лог, encoding="utf-8", errors="replace") as f:
        f.seek(max(0, os.path.getsize(лог) - 3_000_000))
        строки = f.read().splitlines()
    нужные = [с for с in строки if re.search(r"auto.send|recover|Started|startup|connect failed|10060", с, re.I)]
    print("--- %s: %d строк в хвосте, по теме %d ---" % (лог, len(строки), len(нужные)))
    for с in нужные[:6] + ["..."] + нужные[-14:]:
        print("   " + с[:200])
print("=== ЛИМИТЫ И ЛОГ ===")
