# -*- coding: utf-8 -*-
"""Есть ли на сервере живые пометки копий и что они показывают.

Соседняя сессия завела store.kopii_avtootveta: статус копии читается из
очереди в момент показа, связь по ключу avtootvet:<исходный получатель>:
<адрес>. Проверяем, что код на сервере и что по нашим восьми он говорит
правду.
"""
import io
import sys

sys.path.insert(0, r"C:\sender")
код = io.open(r"C:\sender\sender\store.py", encoding="utf-8").read()
print("kopii_avtootveta в боевом store.py:", "kopii_avtootveta" in код)
вотчер = io.open(r"C:\sender\sender\imap_watcher.py", encoding="utf-8").read()
print("старая пометка в тексте лида убрана:",
      "копия письма поставлена в очередь" not in вотчер)
апп = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8").read()
print("лента отдаёт поле копии:", "kopii_avtootveta" in апп)

from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
if not hasattr(store, "kopii_avtootveta"):
    print("\nметода нет — служба работает со старым кодом")
    raise SystemExit(0)
вышло = store.kopii_avtootveta()
print(f"\nкопий известно: {len(вышло) if вышло is not None else '—'}")
if isinstance(вышло, dict):
    for k, v in list(вышло.items())[:20]:
        print(f"  {str(k)[:60]:<60} {v}")
else:
    print(" ", str(вышло)[:800])
