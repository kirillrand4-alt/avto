# -*- coding: utf-8 -*-
"""Сколько писем НЕ ВЫПУСТИЛ сам Яндекс (наш исходящий SMTP ящиков) за N суток
(по умолч. 3): send_log не-sent и messages failed с текстом ошибки, по дням и
видам ошибки; отдельно — «подозрение на спам» Яндекса."""
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
от = (datetime.utcnow() - timedelta(days=N)).strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
кол = [r[1] for r in c.execute("PRAGMA table_info(send_log)")]
print("send_log:", кол)
тс = next((k for k in ("ts", "created_at", "sent_at", "attempted_at") if k in кол), None)
ош = next((k for k in ("error", "detail", "smtp_response", "last_error", "message") if k in кол), None)
ящ = next((k for k in ("mailbox_id", "mailbox", "from_addr") if k in кол), None)


def вид(e):
    e = str(e or "")
    if re.search(r"(?i)spam|спам|5\.7\.1", e):
        return "подозрение на спам"
    if re.search(r"(?i)limit|quota|too many|лимит|4\.7\.0|5\.5\.4|try later|ratelimit", e):
        return "лимит/частота"
    if re.search(r"(?i)auth|login|password|535", e):
        return "вход в ящик"
    if re.search(r"(?i)timeout|timed out|connection|refused|reset", e):
        return "связь"
    return "прочее"


исх = Counter(r[0] for r in c.execute("SELECT outcome FROM send_log WHERE %s>=?" % тс, (от,)))
print("исходы send_log с", от, ":", dict(исх.most_common()))
по_дням = defaultdict(Counter)
прим = {}
по_ящ = Counter()
for row in c.execute("SELECT %s, outcome, %s, %s FROM send_log WHERE %s>=? AND outcome!='sent'" % (тс, ош or "''", ящ or "''", тс), (от,)):
    к = вид(row[2])
    по_дням[str(row[0])[:10]][(row[1], к)] += 1
    прим.setdefault(к, str(row[2])[:160])
    if к == "подозрение на спам":
        по_ящ[row[3]] += 1
for д in sorted(по_дням):
    print(д, dict(по_дням[д].most_common()))
print("примеры:")
for к, v in прим.items():
    print("  ", к, "|", v)
print("ящики с «подозрением на спам»:", по_ящ.most_common(10))
отпр = Counter(str(r[0])[:10] for r in c.execute("SELECT sent_at FROM messages WHERE status='sent' AND sent_at>=?", (от,)))
print("отправлено по дням:", dict(sorted(отпр.items())))
