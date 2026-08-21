# -*- coding: utf-8 -*-
"""Завести события reject_spam по УЖЕ случившимся отказам почтовика.

Счётчик на панели должен показывать правду с первого дня, а не начинать с
нуля: 43 отказа уже случились и лежат в messages.last_error. Переносим их в
журнал событий — тем же типом, что теперь пишет отправка.

Ящик у 42 из 43 неизвестен (его начали писать только сегодня): такие
события кладём без ящика — общий счёт будет верным, разбивка по ящикам
наполнится с этого момента. Врать про ящик нельзя.

dedup_key стабильный (по письму), поэтому повторный прогон ничего не
задвоит. Сухой прогон по умолчанию. Катить: --katit
"""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.dtos import EventIn                                     # noqa: E402
from sender.otkaz_spam import СОБЫТИЕ, eto_otkaz_spam               # noqa: E402
from sender.store import Store                                      # noqa: E402

КАТИТЬ = "--katit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT id, mailbox_id, campaign_id, recipient_id, updated_at, "
    "       COALESCE(last_error,'') err FROM messages "
    " WHERE COALESCE(last_error,'') <> ''").fetchall()
отказы = [р for р in ряды if eto_otkaz_spam(р["err"])]
print(f"писем с ошибкой: {len(ряды)}; из них отказ по спаму: {len(отказы)}")
print("с известным ящиком:",
      sum(1 for р in отказы if р["mailbox_id"]), "| без ящика:",
      sum(1 for р in отказы if not р["mailbox_id"]))
print("по дням:", dict(sorted(Counter(str(р["updated_at"])[:10]
                                      for р in отказы).items())))

if not КАТИТЬ:
    print("\nсухой прогон. Катить - --katit")
    raise SystemExit(0)

добавлено = 0
for р in отказы:
    try:
        когда = datetime.fromisoformat(str(р["updated_at"]))
        if когда.tzinfo is None:
            когда = когда.replace(tzinfo=timezone.utc)
    except Exception:                                              # noqa: BLE001
        когда = datetime.now(timezone.utc)
    _, новое = store.append_event(EventIn(
        dedup_key=f"otkaz|истор|{р['id']}",
        event_type=СОБЫТИЕ,
        message_id=int(р["id"]),
        recipient_id=р["recipient_id"],
        campaign_id=р["campaign_id"],
        mailbox_id=р["mailbox_id"] or None,
        provider=None,
        event_ts=когда,
        detail={"error": str(р["err"])[:400], "источник": "перенос истории"},
    ))
    добавлено += 1 if новое else 0
print(f"\nсобытий заведено: {добавлено} (повторы пропущены)")
