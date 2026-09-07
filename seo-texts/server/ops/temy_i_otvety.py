# -*- coding: utf-8 -*-
"""Влияет ли название компании в теме на ответы. Плюс частые формы тем."""
import re
import sqlite3
from collections import Counter


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=180)
s.row_factory = sqlite3.Row

# отправленные письма кампании 11 с темой и получателем
письма = {}
for r in s.execute(
        "SELECT cr.subject, cr.recipient_id, rc.company_name "
        "  FROM confirm_reviews cr "
        "  JOIN send_log sl ON sl.message_id = cr.message_id "
        "  LEFT JOIN recipients rc ON rc.id = cr.recipient_id "
        " WHERE cr.campaign_id=11 AND sl.outcome='sent'"):
    rid = int(r["recipient_id"] or 0)
    if rid:
        письма[rid] = (str(r["subject"] or ""), str(r["company_name"] or ""))

ответили = {int(r["recipient_id"] or 0) for r in s.execute(
    "SELECT recipient_id FROM events WHERE event_type='reply'")}
s.close()


def ядро_имени(имя):
    """«АО "ДОНДУКОВСКИЙ ЭЛЕВАТОР"» -> «дондуковский элеватор»."""
    м = re.search(r'[«"]([^»"]+)[»"]', имя)
    т = (м.group(1) if м else имя).lower()
    return re.sub(r"\s+", " ", т).strip()


с_именем = [0, 0]
без_имени = [0, 0]
формы = Counter()
формы_отв = Counter()
for rid, (тема, имя) in письма.items():
    ядро = ядро_имени(имя)
    # считаем совпадением, если в теме есть хотя бы первое слово названия
    первое = (ядро.split(" ")[0] if ядро else "")
    есть = bool(первое) and len(первое) > 3 and первое[:5] in тема.lower()
    куда = с_именем if есть else без_имени
    куда[0] += 1
    if rid in ответили:
        куда[1] += 1
    # форма темы: первые два слова
    ф = " ".join(тема.split()[:2]).lower()
    формы[ф] += 1
    if rid in ответили:
        формы_отв[ф] += 1

print("=" * 78)
print("=== СВОДКА: НАЗВАНИЕ В ТЕМЕ И ОТВЕТЫ ===")
print("отправленных писем с темой: %d" % len(письма))
print("")
for метка, (всего, отв) in (("название компании В ТЕМЕ есть", с_именем),
                            ("названия в теме нет", без_имени)):
    print("   %-32s писем %5d  ответов %3d  (%4.2f%%)"
          % (метка, всего, отв, 100.0 * отв / всего if всего else 0))
print("")
print("--- частые формы темы (первые два слова) ---")
for ф, н in формы.most_common(12):
    о = формы_отв.get(ф, 0)
    print("   %-26s писем %5d  ответов %3d  (%4.2f%%)"
          % (ф[:26], н, о, 100.0 * о / н if н else 0))
