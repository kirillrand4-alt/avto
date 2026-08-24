# -*- coding: utf-8 -*-
"""Чем письма с живым ответом отличаются от того, что мы делаем сейчас.

Владелец: «сравни, насколько лучше/хуже итоговые письма с теми, на которые
был именно живой ответ». Ответ считаем живым, если событие reply не
автоответ и не отписка.

Меряем то, что можно померить без модели: длина, число абзацев, наличие
строки отказа, наличие имени компании, первая фраза.
"""
import json
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

ответившие = {}
for р in c.execute(
        "SELECT e.message_id, e.detail_json FROM events e "
        " WHERE e.event_type='reply' AND e.message_id IS NOT NULL"):
    д = str(р["detail_json"] or "")
    вид = ""
    м = re.search(r'"reply_kind"\s*:\s*"([^"]+)"', д)
    if м:
        вид = м.group(1)
    if вид in ("auto_reply", "автоответ", "unsub_request"):
        continue
    ответившие[int(р["message_id"])] = вид or "?"
print("писем с живым ответом: %d" % len(ответившие))

def мера(тема, тело):
    т = str(тело or "")
    абз = [a for a in т.split("\n\n") if a.strip()]
    первый = ""
    for a in абз:
        if not re.match(r"(?i)^\s*(добрый день|здравствуйте)", a):
            первый = a.strip()
            break
    return {"знаков": len(т), "абзацев": len(абз),
            "слов": len([w for w in re.split(r"\s+", т) if w]),
            "отказ": bool(re.search(r"(?i)неактуальн|не отвлекать|короткий ответ", т)),
            "перенаправить": bool(re.search(r"(?i)перешл|перенаправ", т)),
            "вопросов": т.count("?"),
            "первая": первый[:110]}


def свод(имя, строки):
    if not строки:
        print("\n%s: нет писем" % имя)
        return
    м = [мера(р["subject"], р["body_rendered"] or "") for р in строки]
    n = len(м)
    print("\n=== %s (%d писем) ===" % (имя, n))
    print("  знаков в среднем:   %d" % (sum(x["знаков"] for x in м) // n))
    print("  слов в среднем:     %d" % (sum(x["слов"] for x in м) // n))
    print("  абзацев в среднем:  %.1f" % (sum(x["абзацев"] for x in м) / n))
    print("  вопросов в среднем: %.1f" % (sum(x["вопросов"] for x in м) / n))
    print("  со строкой отказа:  %d%%" % (100 * sum(1 for x in м if x["отказ"]) // n))
    print("  с просьбой переслать: %d%%"
          % (100 * sum(1 for x in м if x["перенаправить"]) // n))
    print("  первые фразы (3):")
    for x in м[:3]:
        print("    • %s" % x["первая"])


ид = list(ответившие)
места = ",".join("?" * len(ид)) if ид else "0"
отвеченные = c.execute(
    "SELECT id, subject, body_rendered FROM messages WHERE id IN (%s) "
    "  AND COALESCE(body_rendered,'')<>''" % места, ид).fetchall()
свод("ПИСЬМА С ЖИВЫМ ОТВЕТОМ", отвеченные)

без = c.execute(
    "SELECT id, subject, body_rendered FROM messages "
    " WHERE status='sent' AND COALESCE(body_rendered,'')<>'' "
    "   AND id NOT IN (%s) ORDER BY id DESC LIMIT 200" % места, ид).fetchall()
свод("ОТПРАВЛЕННЫЕ БЕЗ ОТВЕТА (последние 200)", без)

дешёвые = c.execute(
    "SELECT cr.id, cr.subject, cr.body body_rendered FROM confirm_reviews cr "
    " WHERE cr.status IN ('pending','approved') "
    "   AND substr(cr.created_at,1,10)=date('now') "
    "   AND COALESCE(cr.body,'')<>'' ORDER BY cr.id DESC LIMIT 200").fetchall()
свод("ЧТО ДЕЛАЕМ СЕЙЧАС (сегодняшняя очередь)", дешёвые)

print("\n=== ВИДЫ ЖИВЫХ ОТВЕТОВ ===")
for к, н in Counter(ответившие.values()).most_common():
    print("  %-18s %d" % (к, н))
