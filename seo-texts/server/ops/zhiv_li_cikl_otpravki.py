# -*- coding: utf-8 -*-
"""Крутится ли цикл автоотправки в панели — и что он делает.

Последнее письмо ушло в 07:30 UTC, а подбор ящика на 25 писем отдаёт живой
ящик. Значит вопрос не «кому слать», а «кто должен послать». Смотрим
состояние цикла и хвост лога службы.

    python zapusk_svoego_skripta.py ops/zhiv_li_cikl_otpravki.py
"""
import glob
import io
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)

print("настройки цикла:")
for k in ("auto_send_enabled", "sending_window"):
    print(f"  {k}: {store.get_setting(k, '(нет)')}")
print(f"  auto_send.interval_sec: {cfg.get('auto_send.interval_sec', '(нет)')}")
print(f"  auto_send.batch: {cfg.get('auto_send.batch', '(нет)')}")
print(f"  confirm.live_send: {cfg.get('confirm.live_send', '(нет)')}")

# claim_approved_due — ровно то, что берёт цикл. Спрашиваем БЕЗ отправки.
try:
    беру = store.claim_approved_due(now=сейчас, limit=5, dry_run=True)  # type: ignore
    print(f"\nclaim_approved_due(dry_run) вернул: {len(беру)}")
except TypeError:
    print("\nclaim_approved_due не умеет dry_run — считаем запросом напрямую")
    with store._lock:
        n = store._conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
            "ON c.message_id=m.id WHERE m.status='scheduled' "
            "AND c.status IN ('approved','edited') AND m.scheduled_at<=?",
            (сейчас.isoformat(),)).fetchone()[0]
        print(f"  писем, подходящих под условие цикла: {n}")
except Exception as ex:                                          # noqa: BLE001
    print("\nclaim_approved_due:", type(ex).__name__, str(ex)[:120])

# Хвост лога службы: где бы он ни лежал.
кандидаты = []
for шаблон in (r"C:\sender\logs\*.log", r"C:\sender\*.log",
               r"C:\sender\server\*.log", r"C:\sender\logs\*.txt"):
    кандидаты.extend(glob.glob(шаблон))
кандидаты.sort(key=lambda p: os.path.getmtime(p), reverse=True)
print(f"\nфайлы логов: {[os.path.basename(x) for x in кандидаты[:6]]}")
for путь in кандидаты[:2]:
    m = datetime.fromtimestamp(os.path.getmtime(путь), timezone.utc)
    print(f"\n=== {путь} (изменён {m.strftime('%H:%M')} UTC)")
    try:
        with io.open(путь, "r", encoding="utf-8", errors="replace") as f:
            строки = f.readlines()[-4000:]
    except Exception as ex:                                      # noqa: BLE001
        print("  не прочитан:", str(ex)[:80])
        continue
    нужные = [s for s in строки
              if "auto_send" in s or "autosend" in s.lower()][-15:]
    for s in нужные or строки[-10:]:
        print("  " + s.rstrip()[:160])
