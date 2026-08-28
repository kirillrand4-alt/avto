# -*- coding: utf-8 -*-
"""patch_msgid_zaslon.py"""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\store.py"
МЕТКА = "_msgid_sobytiya"
ЗАМЕНЫ = json.loads(r'''[["    event_ts     TEXT NOT NULL,\n    detail_json  TEXT,\n    created_at   TEXT NOT NULL\n);\nCREATE UNIQUE INDEX IF NOT EXISTS ux_events_dedup ON events(dedup_key);", "    event_ts     TEXT NOT NULL,\n    detail_json  TEXT,\n    created_at   TEXT NOT NULL,\n    -- Message-ID входящего письма. Второй, НЕЗАВИСИМЫЙ признак того же\n    -- письма: dedup_key завязан на нумерацию писем в ящике, а она пережила\n    -- уже одну смену (порядковый номер → UID) и при пересоздании ящика\n    -- (UIDVALIDITY) сменится снова. Message-ID письмо несёт с собой и не\n    -- меняет никогда.\n    rfc_msgid    TEXT\n);\nCREATE UNIQUE INDEX IF NOT EXISTS ux_events_dedup ON events(dedup_key);\nCREATE INDEX IF NOT EXISTS ix_events_msgid ON events(mailbox_id, rfc_msgid);"], ["                \"ALTER TABLE confirm_reviews ADD COLUMN manual_email_ts TEXT\",\n            ):", "                \"ALTER TABLE confirm_reviews ADD COLUMN manual_email_ts TEXT\",\n                # Message-ID входящего: см. комментарий в схеме events\n                \"ALTER TABLE events ADD COLUMN rfc_msgid TEXT\",\n            ):"], ["    def append_event(self, e: EventIn) -> tuple[int, bool]:\n        \"\"\"ON CONFLICT(dedup_key) DO NOTHING → (event_id, created?).\"\"\"\n        now_iso = _now_iso()\n        with self.transaction() as conn:\n            cur = conn.execute(\n                \"\"\"\n                INSERT INTO events\n                    (dedup_key, event_type, message_id, recipient_id, campaign_id,\n                     mailbox_id, provider, event_ts, detail_json, created_at)\n                VALUES (?,?,?,?,?,?,?,?,?,?)\n                ON CONFLICT(dedup_key) DO NOTHING\n                \"\"\",\n                (\n                    e.dedup_key, e.event_type, e.message_id, e.recipient_id,\n                    e.campaign_id, e.mailbox_id, e.provider, _to_iso(e.event_ts),\n                    _json_dump(e.detail), now_iso,\n                ),\n            )\n            if cur.rowcount == 1:\n                return int(cur.lastrowid), True\n            row = conn.execute(\n                \"SELECT id FROM events WHERE dedup_key=?\", (e.dedup_key,)\n            ).fetchone()\n            return int(row[\"id\"]), False\n", "    @staticmethod\n    def _msgid_sobytiya(detail) -> str:\n        \"\"\"Message-ID входящего письма из его же заголовков, нормализованный.\"\"\"\n        if not isinstance(detail, dict):\n            return \"\"\n        шапка = detail.get(\"headers\")\n        if not isinstance(шапка, dict):\n            return \"\"\n        for имя in (\"Message-ID\", \"Message-Id\", \"message-id\"):\n            з = шапка.get(имя)\n            if з:\n                return str(з).strip().strip(\"<>\").lower()[:400]\n        return \"\"\n\n    def append_event(self, e: EventIn) -> tuple[int, bool]:\n        \"\"\"ON CONFLICT(dedup_key) DO NOTHING → (event_id, created?).\n\n        Второй заслон — по Message-ID письма. dedup_key завязан на нумерацию\n        писем в ящике, и 28.08 эта нумерация сменилась (порядковый номер →\n        UID): весь архив выглядел новым и лёг в журнал повторно — 132 двойные\n        записи, сводка ответов выросла вдвое. Message-ID письмо несёт с собой,\n        и по нему повтор виден независимо от того, как мы нумеруем ящик.\n        \"\"\"\n        now_iso = _now_iso()\n        msgid = self._msgid_sobytiya(e.detail)\n        with self.transaction() as conn:\n            if msgid:\n                была = conn.execute(\n                    \"SELECT id FROM events WHERE mailbox_id IS ? AND rfc_msgid = ? \"\n                    \" ORDER BY id LIMIT 1\", (e.mailbox_id, msgid)).fetchone()\n                if была:\n                    return int(была[\"id\"]), False\n            cur = conn.execute(\n                \"\"\"\n                INSERT INTO events\n                    (dedup_key, event_type, message_id, recipient_id, campaign_id,\n                     mailbox_id, provider, event_ts, detail_json, created_at,\n                     rfc_msgid)\n                VALUES (?,?,?,?,?,?,?,?,?,?,?)\n                ON CONFLICT(dedup_key) DO NOTHING\n                \"\"\",\n                (\n                    e.dedup_key, e.event_type, e.message_id, e.recipient_id,\n                    e.campaign_id, e.mailbox_id, e.provider, _to_iso(e.event_ts),\n                    _json_dump(e.detail), now_iso, msgid or None,\n                ),\n            )\n            if cur.rowcount == 1:\n                return int(cur.lastrowid), True\n            row = conn.execute(\n                \"SELECT id FROM events WHERE dedup_key=?\", (e.dedup_key,)\n            ).fetchone()\n            return int(row[\"id\"]), False\n"]]''')

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
