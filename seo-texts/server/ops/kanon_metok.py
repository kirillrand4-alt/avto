# -*- coding: utf-8 -*-
"""Свести словарь меток ответа к одному: правка leaddesk.py + перелив базы.

Боевой imap_watcher на вежливом отказе пишет f"[отказ] {snippet}", штатный
путь — английский signal.kind. Фильтр ленты шлёт в API английский ключ, и
русские карточки под ним не находятся. Канон ставим на входе в лид, чтобы не
зависеть от того, кто и каким словом пометил.

Файл на сервере новее репозитория (есть napravlenie/v_bitrix), поэтому
правим ТОЛЬКО по якорям, с .bak и проверкой компиляции. Не нашёлся якорь —
не пишем ничего.
"""
import io
import os
import py_compile
import shutil
import sqlite3
import time

ПУТЬ = r"C:\sender\sender\leaddesk.py"
КАНОН = {"отказ": "not_interested", "автоответ": "auto_reply",
         "отписка": "unsub_request", "горячий": "hot",
         "интересуется": "interested", "не туда": "wrong_contact",
         "перенаправление": "redirect", "не интересно": "not_interested"}

ВСТАВКА = '''# Метку ответа в карточку кладут ДВА разных места, и словари у них разные.
# Штатный путь берёт signal.kind классификатора — там всё по-английски
# (ALL_KINDS). Ветка вежливого отказа в imap_watcher вписывает метку русским
# словом прямо в сниппет: f"[отказ] {snippet}". В базе от этого две метки об
# одном и том же, а выпадающий список ленты шлёт в API английский ключ — и
# русские карточки под фильтром «отказ» не находятся вовсе (владелец 24.08:
# «я их не вижу и в отказах»; замер: 18 старых английских против 6 свежих
# русских). Сводим к одному словарю на входе в лид: кто бы каким словом ни
# пометил, в колонке окажется канон, а панель нарисует его подпись сама.
КАНОН_МЕТОК: dict[str, str] = {
    "отказ": "not_interested",
    "не интересно": "not_interested",
    "автоответ": "auto_reply",
    "отписка": "unsub_request",
    "горячий": "hot",
    "интересуется": "interested",
    "не туда": "wrong_contact",
    "перенаправление": "redirect",
}


'''

СТАРОЕ = '''                    elif part and reply_kind is None:
                        reply_kind = part
        return reply_kind, phone, need'''
НОВОЕ = '''                    elif part and reply_kind is None:
                        reply_kind = part
        if reply_kind:
            reply_kind = КАНОН_МЕТОК.get(reply_kind.strip().lower(), reply_kind)
        return reply_kind, phone, need'''
ЯКОРЬ_ВСТАВКИ = "# Допустимые переходы статуса лида."

т = io.open(ПУТЬ, encoding="utf-8").read()
if "КАНОН_МЕТОК" in т:
    print("файл УЖЕ правлен (КАНОН_МЕТОК на месте) — код не трогаем")
else:
    беда = []
    if т.count(ЯКОРЬ_ВСТАВКИ) != 1:
        беда.append("якорь вставки встречается %d раз" % т.count(ЯКОРЬ_ВСТАВКИ))
    if т.count(СТАРОЕ) != 1:
        беда.append("якорь _parse_snippet встречается %d раз" % т.count(СТАРОЕ))
    if беда:
        print("НЕ ПРАВИМ: " + "; ".join(беда))
    else:
        копия = ПУТЬ + ".bak-%d" % int(time.time())
        shutil.copy2(ПУТЬ, копия)
        и = т.index(ЯКОРЬ_ВСТАВКИ)
        новый = т[:и] + ВСТАВКА + т[и:]
        новый = новый.replace(СТАРОЕ, НОВОЕ)
        io.open(ПУТЬ, "w", encoding="utf-8", newline="").write(новый)
        try:
            py_compile.compile(ПУТЬ, doraise=True)
            print("правка легла, компиляция ОК, копия: %s"
                  % os.path.basename(копия))
        except Exception as e:  # noqa: BLE001
            shutil.copy2(копия, ПУТЬ)
            print("КОМПИЛЯЦИЯ УПАЛА, откатили: %s" % e)

print("\n=== ПЕРЕЛИВ СУЩЕСТВУЮЩИХ КАРТОЧЕК ===")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
до = {р["k"]: р["n"] for р in c.execute(
    "SELECT COALESCE(reply_kind,'(пусто)') k, COUNT(*) n FROM leads GROUP BY 1")}
всего = 0
for рус, англ in КАНОН.items():
    cur = c.execute("UPDATE leads SET reply_kind=?, updated_at=updated_at "
                    "WHERE reply_kind=?", (англ, рус))
    if cur.rowcount:
        print("  %-16s -> %-16s %d шт" % (рус, англ, cur.rowcount))
        всего += cur.rowcount
c.commit()
print("  переведено: %d" % всего)

print("\n=== reply_kind ПОСЛЕ ===")
for р in c.execute("SELECT COALESCE(reply_kind,'(пусто)') k, COUNT(*) n "
                   "FROM leads GROUP BY 1 ORDER BY n DESC"):
    было = до.get(р["k"], 0)
    print("  %-16s %4d  (было %d)" % (р["k"], р["n"], было))
