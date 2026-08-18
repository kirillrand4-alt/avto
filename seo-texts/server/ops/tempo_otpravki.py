# -*- coding: utf-8 -*-
"""С какой скоростью очередь физически может уходить.

Лимит ящика — это потолок за сутки, а темп задаёт пейсинг: пауза между
письмами одного ящика (и, если включён, пауза между письмами в один регион).
Если пауза 90-420 секунд, восемь ящиков дают примерно 110 писем в час — и
никакой потолок этого не ускорит.

    python zapusk_svoego_skripta.py ops/tempo_otpravki.py
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

мин = cfg.get("send_pacing.min_interval_sec", 0)
макс = cfg.get("send_pacing.max_interval_sec", 0)
рег = cfg.get("send_pacing.region_interval_sec", 0)
print(f"пауза между письмами одного ящика: {мин}-{макс} сек")
print(f"пауза между письмами в один регион: {рег} сек (0 = выключено)")

ср = ((мин or 0) + (макс or 0)) / 2 or 1
живых = 8
print(f"\nтеоретический темп: {живых} рабочих ящиков / {ср:.0f} сек в среднем "
      f"= {3600 / ср * живых:.0f} писем в час")

# Факт: сколько ушло за последний час.
сейчас = datetime.now(timezone.utc)
час = (сейчас - timedelta(hours=1)).isoformat()
получас = (сейчас - timedelta(minutes=30)).isoformat()
with store._lock:
    з_час = store._conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type='sent' AND event_ts>?",
        (час,)).fetchone()[0]
    з_полчаса = store._conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type='sent' AND event_ts>?",
        (получас,)).fetchone()[0]
print(f"факт: за последний час {з_час} писем, за последние 30 минут {з_полчаса}")

with store._lock:
    осталось = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE status='approved'"
    ).fetchone()[0]
темп = max(1, з_час)
print(f"\nосталось готовых: {осталось}. При нынешнем темпе это "
      f"{осталось / темп:.1f} часа непрерывной отправки.")
