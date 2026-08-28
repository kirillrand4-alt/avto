# -*- coding: utf-8 -*-
"""patch_data_pisma.py"""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\imap_watcher.py"
МЕТКА = "_kogda_prishlo"
ЗАМЕНЫ = json.loads(r'''[["from email.message import EmailMessage\n", "from email.message import EmailMessage\nfrom email.utils import parsedate_to_datetime\n"], ["    def _process_event(self, ev: InboundEvent, mailbox_id: str) -> None:", "    # КОГДА ПИСЬМО ПРИШЛО, а не когда мы его заметили. Опрос добирается до\n    # письма когда угодно: 28.08 переход на UID открыл весь архив ящиков\n    # непрочитанным (флаг «прочитано» до этого ставился не тому письму), и\n    # суточная сводка приписала сегодняшнему дню 87 отбивок и 75 ответов\n    # чужих дней — BR% 8.76% вместо 3.8%. Берём Date самого письма; на кривой\n    # или бредовой дате (часы отправителя врут, заголовка нет) честно\n    # откатываемся на «сейчас», а не пишем 1970 год.\n    @staticmethod\n    def _kogda_prishlo(headers: dict) -> datetime:\n        сейчас = datetime.now(timezone.utc)\n        строка = str((headers or {}).get(\"Date\") or \"\").strip()\n        if not строка:\n            return сейчас\n        try:\n            т = parsedate_to_datetime(строка)\n        except (TypeError, ValueError, IndexError):\n            return сейчас\n        if т is None:\n            return сейчас\n        if т.tzinfo is None:\n            т = т.replace(tzinfo=timezone.utc)\n        т = т.astimezone(timezone.utc)\n        рано = datetime(2020, 1, 1, tzinfo=timezone.utc)\n        if т < рано or т > сейчас + timedelta(days=1):\n            return сейчас\n        return т\n\n    def _process_event(self, ev: InboundEvent, mailbox_id: str) -> None:"], ["        event_in = EventIn(\n            dedup_key=ev.dedup_key,\n            event_type=event_type,\n            event_ts=datetime.now(timezone.utc),", "        когда = self._kogda_prishlo(ev.raw_headers)\n        заметили = datetime.now(timezone.utc)\n        # Расхождение больше часа — это доскрёб архива, а не обычный опрос.\n        # Отметку «когда заметили» сохраняем: она объясняет, почему письмо\n        # позавчерашнее, а лид по нему заведён сегодня.\n        if abs((заметили - когда).total_seconds()) > 3600:\n            detail[\"zapisano_ts\"] = заметили.strftime(\"%Y-%m-%dT%H:%M:%S\")\n        event_in = EventIn(\n            dedup_key=ev.dedup_key,\n            event_type=event_type,\n            event_ts=когда,"]]''')

т = io.open(ПУТЬ, encoding="utf-8").read()
if МЕТКА in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:70]))
        raise SystemExit(1)
было = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % ex)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
