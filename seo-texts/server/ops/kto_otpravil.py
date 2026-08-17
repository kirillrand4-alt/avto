# -*- coding: utf-8 -*-
"""Кто отправил письмо: рука оператора или автоматика.

В срезе очереди появилась строка «sent» в кампании 11 (Meyer). Ручная
отправка разрешена, автоматическая - под холдом, и разница между ними
проверяется не на глаз, а по полю «кем решено» и времени решения.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

for r in (store.confirm_list(status="sent", limit=500) or []):
    if int(r.get("campaign_id") or 0) not in (10, 11):
        continue
    print(f"#{r.get('id')} кампания {r.get('campaign_id')} "
          f"{str(r.get('email'))[:38]:<40}")
    print(f"   решил: {r.get('decided_by')!r} | решено: {r.get('decided_at')} "
          f"| создано: {r.get('created_at')}")
    print(f"   тема: {str(r.get('subject'))[:80]}")

print("\nавтоотправка в настройках:",
      cfg.get("auto_send.enabled", None), "| окно:",
      cfg.get("panel_settings.sending_window", None))
