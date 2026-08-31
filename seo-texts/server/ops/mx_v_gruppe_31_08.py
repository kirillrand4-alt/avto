# -*- coding: utf-8 -*-
"""Только чтение: из чего состоит отсечка «свой почтовый сервер» в meyer-v30.

СВОЙ_СЕРВЕР = ("other","unknown","") — но «unknown» и пустое значат «не знаем
провайдера», а не «своя почта». Смотрим, сколько чего."""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

ИМЯ = "meyer-v30"
СВОЙ = ("other", "unknown", "")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
группы = store.recipient_groups().get("по_id") or {}
в_группе = [rid for rid, gr in группы.items() if ИМЯ in (gr or [])]

c = Counter()
инн_своих = set()
инн_всех = set()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        continue
    mx = str(getattr(rec, "mx_provider", "") or "").strip().lower()
    inn = str(getattr(rec, "inn", "") or "")
    инн_всех.add(inn)
    c[mx or "(пусто)"] += 1
    if mx in СВОЙ:
        инн_своих.add(inn)

print("=== mx_provider в группе %s (%d строк) ===" % (ИМЯ, len(в_группе)))
for k, v in c.most_common(14):
    метка = "  <- считается «свой сервер»" if k in СВОЙ or k == "(пусто)" else ""
    print("  %-16s %6d%s" % (k, v, метка))

свои = sum(v for k, v in c.items() if k in СВОЙ or k == "(пусто)")
print("\n=== ИТОГ ===")
print("  строк всего: %d, компаний: %d" % (len(в_группе), len(инн_всех)))
print("  под отсечку «свой сервер»: %d строк, %d компаний"
      % (свои, len(инн_своих)))
неизв = c.get("unknown", 0) + c.get("(пусто)", 0)
print("  из них НЕ «своя почта», а «провайдер не определён»: %d строк" % неизв)
print("  настоящих other (определён как иной): %d строк" % c.get("other", 0))
