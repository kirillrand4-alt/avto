# -*- coding: utf-8 -*-
"""Ключ дедупа входящих не должен съедать ЧУЖОЕ письмо.

Ключ собран как imap:{uidvalidity}:{номер}:{вид}. Нумерация писем в ящике
съезжает (удалили письмо — номера сдвинулись), и занятый ключ бывает не
повтором, а другим письмом. 04.09 так пропал горячий ответ Медведовского
ЗПП: лёг на ключ ...:32:reply, уже занятый автоответом X5 от 02.09, вышел
из append_event как «уже видели», получил \\Seen — и исчез совсем.

Правка хирургическая: если ключ занят письмом с ДРУГИМ Message-ID (повтор
того же письма отсекает строка выше — по его собственному Message-ID),
пишем событие под ключом с хвостом от Message-ID.

argv: --primenit чтобы записать (без него только показать).
"""
import hashlib
import io
import os
import py_compile
import sys
import time

ФАЙЛ = r"C:\sender\sender\store.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv

ЯКОРЬ = '''        now_iso = _now_iso()
        msgid = self._msgid_sobytiya(e.detail)
        with self.transaction() as conn:
            if msgid:
                была = conn.execute(
                    "SELECT id FROM events WHERE mailbox_id IS ? AND rfc_msgid = ? "
                    " ORDER BY id LIMIT 1", (e.mailbox_id, msgid)).fetchone()
                if была:
                    return int(была["id"]), False
'''

ЗАМЕНА = '''        now_iso = _now_iso()
        msgid = self._msgid_sobytiya(e.detail)
        ключ = e.dedup_key
        with self.transaction() as conn:
            if msgid:
                была = conn.execute(
                    "SELECT id FROM events WHERE mailbox_id IS ? AND rfc_msgid = ? "
                    " ORDER BY id LIMIT 1", (e.mailbox_id, msgid)).fetchone()
                if была:
                    return int(была["id"]), False
                # ЗАНЯТЫЙ КЛЮЧ — НЕ ВСЕГДА ПОВТОР. Ключ входящих собран как
                # imap:{uidvalidity}:{номер}:{вид}, а нумерация писем в ящике
                # съезжает: удалили письмо — номера сдвинулись и разошлись с
                # UID. Повтор ТОГО ЖЕ письма отсечён строкой выше, по его
                # собственному Message-ID; значит здесь письмо ДРУГОЕ и ему
                # нужен свой ключ. Иначе append_event отвечает «уже видели»,
                # обработчик молча выходит, сборщик ставит письму \\\\Seen — и
                # живой ответ пропадает навсегда. Так 04.09 потеряли
                # «Пришлите предложение по оборудованию» от Медведовского ЗПП:
                # ключ ...:32:reply был занят автоответом X5 от 02.09.
                занято = conn.execute(
                    "SELECT rfc_msgid FROM events WHERE dedup_key=?",
                    (ключ,)).fetchone()
                if занято is not None and (занято["rfc_msgid"] or "") != msgid:
                    ключ = "%s:%s" % (ключ, _hashlib.sha1(
                        msgid.encode("utf-8")).hexdigest()[:10])
'''

ЯКОРЬ2 = '''                (
                    e.dedup_key, e.event_type, e.message_id, e.recipient_id,'''
ЗАМЕНА2 = '''                (
                    ключ, e.event_type, e.message_id, e.recipient_id,'''

ЯКОРЬ3 = '''            row = conn.execute(
                "SELECT id FROM events WHERE dedup_key=?", (e.dedup_key,)
            ).fetchone()'''
ЗАМЕНА3 = '''            row = conn.execute(
                "SELECT id FROM events WHERE dedup_key=?", (ключ,)
            ).fetchone()'''

ЯКОРЬ4 = "import json\nimport logging\n"
ЗАМЕНА4 = "import hashlib as _hashlib\nimport json\nimport logging\n"

т = io.open(ФАЙЛ, encoding="utf-8").read()
шаги = [("тело append_event", ЯКОРЬ, ЗАМЕНА),
        ("ключ в INSERT", ЯКОРЬ2, ЗАМЕНА2),
        ("ключ в добор id", ЯКОРЬ3, ЗАМЕНА3),
        ("импорт hashlib", ЯКОРЬ4, ЗАМЕНА4)]

уже = "ЗАНЯТЫЙ КЛЮЧ — НЕ ВСЕГДА ПОВТОР" in т
print("файл: %s (%d байт), правка уже стоит: %s"
      % (ФАЙЛ, len(т), "да" if уже else "нет"))
беда = []
for имя, як, зам in шаги:
    n = т.count(як)
    print("   якорь «%s»: вхождений %d" % (имя, n))
    if n != 1 and not уже:
        беда.append(имя)
if уже:
    raise SystemExit("правка уже применена — больше ничего не делаем")
if беда:
    raise SystemExit("НЕ ТРОГАЕМ: якоря не сошлись (%s)" % ", ".join(беда))

новый = т
for имя, як, зам in шаги:
    новый = новый.replace(як, зам, 1)
print("   стало байт: %d (+%d)" % (len(новый), len(новый) - len(т)))

if not ПРИМЕНИТЬ:
    print("")
    print("=" * 74)
    print("=== ПОКАЗ БЕЗ ЗАПИСИ (нужен --primenit) ===")
    raise SystemExit(0)

бэкап = ФАЙЛ + ".bak-%d" % int(time.time())
io.open(бэкап, "w", encoding="utf-8").write(т)
io.open(ФАЙЛ, "w", encoding="utf-8").write(новый)
try:
    py_compile.compile(ФАЙЛ, doraise=True)
    сообщение = "записано, компилируется"
except Exception as ex:                                         # noqa: BLE001
    io.open(ФАЙЛ, "w", encoding="utf-8").write(т)
    сообщение = "НЕ КОМПИЛИРУЕТСЯ, откатили: %s" % str(ex)[:160]

print("")
print("=" * 74)
print("=== КЛЮЧ ДЕДУПА ВХОДЯЩИХ ===")
print("   бэкап: %s" % бэкап)
print("   итог:  %s" % сообщение)
