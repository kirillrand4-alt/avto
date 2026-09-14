# -*- coding: utf-8 -*-
"""Читается ли ящик i.boyarkin@zernosort.ru и какие ящики вообще не читаются."""
import io, os, re, sys, time
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402

ЯЩИК = "i.boyarkin@zernosort.ru"
п = r"C:\sender\logs\inbox_poll.log"
р = os.path.getsize(п)
with io.open(п, "rb") as f:
    f.seek(max(0, р - 900000))
    т = f.read().decode("utf-8", errors="replace")
строки = т.splitlines()

свои = [с for с in строки if ЯЩИК in с]
print("строк про %s в хвосте лога: %d" % (ЯЩИК, len(свои)))
for с in свои[-12:]:
    print("   " + с[:160])

пров = Counter()
для_ящика = {}
for с in строки:
    м = re.search(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", с, re.I)
    if not м:
        continue
    а = м.group(0).lower()
    if "AUTHENTICATIONFAILED" in с or "invalid credentials" in с.lower() \
            or "parol prilozheniya" in с.lower():
        пров[а] += 1
        для_ящика.setdefault(а, с[:120])

cfg = Config.load(r"C:\sender\sender.yaml")
наши = {str(getattr(mb, "mailbox_id", "")).lower(): str(getattr(mb, "division", ""))
        for mb in cfg.mailboxes()}
print("")
print("--- НАШИ ящики, у которых не проходит вход в почту ---")
плохие = [(а, n) for а, n in пров.most_common() if а in наши]
for а, n in плохие:
    print("   %-42s напр=%-6s отказов %3d | %s"
          % (а[:42], наши.get(а, "?"), n, для_ящика.get(а, "")[:60]))
print("")
print("=" * 74)
print("=== ЧТЕНИЕ ВХОДЯЩИХ ===")
print("ящиков в конфиге: %d; из них с отказом входа: %d"
      % (len(наши), len(плохие)))
print("%s в списке отказов: %s"
      % (ЯЩИК, "ДА" if ЯЩИК in dict(плохие) else "нет"))
