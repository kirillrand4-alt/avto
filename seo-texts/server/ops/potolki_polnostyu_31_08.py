# -*- coding: utf-8 -*-
"""Только чтение: есть ли новые ящики в ручных потолках send_limits."""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
v = store.get_setting("send_limits")
if isinstance(v, str):
    v = json.loads(v)
per = (v or {}).get("per_mailbox") or {}
НОВЫЕ = ("food-sort.ru", "sorting-systems", "rentgen-control", "optical-sort",
         "rentgen-inspec", "inspection-syst")

есть_н, нет_н, есть_с, нет_с = [], [], [], []
for mb in cfg.mailboxes():
    mid = mb.mailbox_id
    нов = any(x in mid for x in НОВЫЕ)
    в = mid in per
    (есть_н if (нов and в) else нет_н if нов else есть_с if в else нет_с).append(
        (mid, per.get(mid)))

print("=== send_limits.per_mailbox: %d записей, all=%s ===" % (len(per), (v or {}).get("all")))
print("\n  СТАРЫЕ с потолком: %d" % len(есть_с))
for m, z in есть_с:
    print("     %-40s %s" % (m[:40], z))
print("  СТАРЫЕ без потолка: %d" % len(нет_с))
for m, _ in нет_с:
    print("     %s" % m)
print("\n  НОВЫЕ с потолком: %d" % len(есть_н))
for m, z in есть_н:
    print("     %-40s %s" % (m[:40], z))
print("  НОВЫЕ без потолка: %d" % len(нет_н))
for m, _ in нет_н:
    print("     %s" % m)

print("\n=== ИТОГ ===")
print("  ключи per_mailbox, которых НЕТ среди ящиков конфига (мусор):")
живые = {mb.mailbox_id for mb in cfg.mailboxes()}
мусор = [k for k in per if k not in живые]
print("     %s" % (мусор if мусор else "нет"))
