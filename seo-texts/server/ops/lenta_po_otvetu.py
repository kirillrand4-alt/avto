# -*- coding: utf-8 -*-
"""Лента лидов — по времени ПОСЛЕДНЕГО ВХОДЯЩЕГО ответа (владелец 23.10: «в
переписке сортировку сделай по времени последнего входящего ответа, а то они
где-то внизу болтаются и не видно их»). Было: store.list_leads сортировал по
created_at — лид, в котором клиент ответил снова, оставался на месте своего
первого ответа. Стало: COALESCE(последний reply по получателю лида,
created_at) DESC — касается всех очередей ленты (новые лиды и так рождаются
ответом, их порядок не меняется).

Индекс events(recipient_id, event_type, event_ts) — если нет, заводится.
Правка по якорю, бэкап .bak-lenta-<время>, py_compile, откат при сбое,
--otkat — из последнего бэкапа. Нужен Restart-Service SenderPanel -Force.
    lenta_po_otvetu.py [--primenit | --otkat]"""
import glob
import io
import py_compile
import shutil
import sqlite3
import sys
import time

ПУТЬ = r"C:\sender\sender\store.py"
БЫЛО = '''        sql.append("ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?")
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_lead(r) for r in rows]'''
СТАЛО = '''        # ЛЕНТА-ПО-ОТВЕТУ-23.10 (владелец: «сортировку сделай по времени
        # последнего входящего ответа, а то они где-то внизу болтаются»):
        # лид поднимается, когда клиент ответил снова, а не стоит на месте
        # своего первого ответа.
        sql.append("ORDER BY COALESCE((SELECT MAX(e.event_ts) FROM events e "
                   "WHERE e.recipient_id = leads.recipient_id "
                   "AND e.event_type = 'reply'), created_at) DESC, "
                   "id DESC LIMIT ? OFFSET ?")
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_lead(r) for r in rows]'''

if "--otkat" in sys.argv:
    б = sorted(glob.glob(ПУТЬ + ".bak-lenta-*"))
    if б:
        shutil.copy2(б[-1], ПУТЬ)
    print("=== ЛЕНТА: ОТКАТ из %s (нужен Restart-Service SenderPanel -Force) ===" % (б[-1] if б else "—"))
    sys.exit(0)
т = io.open(ПУТЬ, encoding="utf-8").read()
if "ЛЕНТА-ПО-ОТВЕТУ-23.10" in т:
    print("=== ЛЕНТА: УЖЕ БЫЛО ===")
    sys.exit(0)
if т.count(БЫЛО) != 1:
    print("якорь найден %d раз" % т.count(БЫЛО))
    print("=== ЛЕНТА: НЕ ПРИМЕНЕНО ===")
    sys.exit(0)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
индексы = [r[1] for r in c.execute("PRAGMA index_list(events)")]
нужен = not any(c.execute("PRAGMA index_info(%s)" % и).fetchone() and
                [r[2] for r in c.execute("PRAGMA index_info(%s)" % и)][:1] == ["recipient_id"] for и in индексы)
print("индекс по events.recipient_id:", "нет — заведу" if нужен else "есть")
if "--primenit" not in sys.argv:
    print("якорь на месте, сухой прогон. Применить — --primenit")
    sys.exit(0)
if нужен:
    with c:
        c.execute("CREATE INDEX IF NOT EXISTS ix_events_recipient_type_ts ON events(recipient_id, event_type, event_ts)")
    print("индекс заведён")
бэкап = ПУТЬ + ".bak-lenta-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(БЫЛО, СТАЛО))
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    sys.exit(0)
print("бэкап:", бэкап)
print("=== ЛЕНТА: ПРИМЕНЕНО (нужен Restart-Service SenderPanel -Force) ===")
