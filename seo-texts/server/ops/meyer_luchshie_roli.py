# -*- coding: utf-8 -*-
"""Сверка ролей по отправкам Meyer (владелец 09.11: «там где не было живых ответов, все ли лучшие роли
были использованы? И всегда именно по лучшим ролям для мейера была отправка?»).

Компании, которым уходили письма кампаний Meyer (Meyer/ФСА/Мейер в названии), и от которых НЕТ живого
ответа (событие reply или лид). Роли и баллы — из enrich.emails.role и lead_scoring._rol_ball
(Meyer-лесенка: технолог 15 > качество 14 > обогатитель/семеновод 13 > производство 12 > техслужба 11 >
элеватор 10 > руководитель 9 > механик 8 > снабжение 7 … общий 3, продажи 2, кадры/бухгалтерия 1).
Годный адрес: не стоп-лист, проба не «нет ящика/нет MX», балл ≥ 2, не числится в панели за другим ИНН.
  1) первое письмо компании ушло на лучший по баллу годный адрес — или ниже (и насколько);
  2) есть ли НЕиспользованный годный адрес с баллом выше, чем у всех, кому уже писали.
Только чтение.  meyer_luchshie_roli.py [--primery]"""
import re, sqlite3, sys
from collections import Counter, defaultdict
sys.path.insert(0, r"C:\sender\server")
from lead_scoring import _rol_ball   # noqa: E402
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=90)
кам = {i: str(n) for i, n in c.execute("SELECT id, name FROM campaigns")}
МК = {i for i, n in кам.items() if re.search(r"(?i)meyer|мейер|фса", n)}
полу = {rid: (str(inn or ""), str(em or "").lower()) for rid, inn, em in c.execute("SELECT id, inn, email FROM recipients")}
за_инн = defaultdict(set)
for rid, (inn, em) in полу.items():
    if inn: за_инн[em].add(inn)
стоп = {str(v).lower() for (v,) in c.execute("SELECT value FROM suppression")}
проба = {str(a).lower(): str(v or "") for a, v in c.execute("SELECT email, verdict FROM addr_probe")}
живые = set()
for (rid,) in c.execute("SELECT DISTINCT recipient_id FROM events WHERE event_type='reply'"):
    if rid in полу and полу[rid][0]: живые.add(полу[rid][0])
for (inn,) in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL"): живые.add(str(inn))
отпр = defaultdict(list)   # inn -> [(sent_at, email, кампания)]
for rid, cid, sa in c.execute("SELECT recipient_id, campaign_id, sent_at FROM messages WHERE status='sent' AND sent_at IS NOT NULL"):
    if cid in МК and rid in полу and полу[rid][0]:
        отпр[полу[rid][0]].append((sa, полу[rid][1], кам.get(cid)))
роль_адреса = {}
def адреса(inn):
    out = {}
    for em, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (inn,)):
        if not em or "@" not in em: continue
        out[em] = роль or ""
    return out
def годен(em, inn):
    if em in стоп or em.split("@")[-1] in стоп: return False
    if проба.get(em, "") in ("нет ящика", "нет MX"): return False
    if за_инн.get(em) and inn not in за_инн[em]: return False
    return True
ит = Counter(); перв_роль = Counter(); недобор_роль = Counter(); прим1, прим2 = [], []
for inn, сп in отпр.items():
    if inn in живые: continue
    ит["компаний без живого ответа"] += 1
    вс = адреса(inn)
    сп.sort()
    писали = {x[1] for x in сп}
    for em in писали: вс.setdefault(em, "")
    бал = {em: _rol_ball(р) for em, р in вс.items()}
    годные = {em: б for em, б in бал.items() if б >= 2 and годен(em, inn)}
    перв = сп[0][1]
    лучш = max(годные.values()) if годные else бал.get(перв, 0)
    б1 = бал.get(перв, 0)
    перв_роль[(вс.get(перв) or "роль неизвестна")[:30]] += 1
    ит["0) у компании есть годный адрес сильной роли (балл ≥10)" if any(б >= 10 for б in годные.values()) else "0) сильной роли в базе нет вовсе"] += 1
    if б1 >= лучш: ит["1) первое письмо — на лучший годный адрес"] += 1
    else:
        ит["1) первое письмо НЕ на лучший (есть адрес выше)"] += 1
        if len(прим1) < 15:
            лучший = max(годные, key=годные.get)
            прим1.append("%s: писали %s [%s] — а был %s [%s]" % (inn, перв, вс.get(перв) or "?", лучший, вс.get(лучший)))
    макс_писали = max(бал.get(em, 0) for em in писали)
    выше = {em: б for em, б in годные.items() if em not in писали and б > макс_писали}
    if выше:
        ит["2) есть неиспользованный адрес с ролью выше всех, кому писали"] += 1
        лучший = max(выше, key=выше.get)
        недобор_роль[(вс.get(лучший) or "?")[:30]] += 1
        ит["2а) из них упущенная роль сильная (технолог…элеватор, балл ≥10)" if выше[лучший] >= 10 else "2б) из них упущенная роль слабая (директор и ниже)"] += 1
        if len(прим2) < 15:
            прим2.append("%s: писали %s — не писали %s [%s]" % (inn, ", ".join("%s[%s]" % (em, вс.get(em) or "?") for em in sorted(писали))[:120], лучший, вс.get(лучший)))
    else:
        ит["2) лучшие роли использованы (выше писавших годных нет)"] += 1
print("кампании Meyer:", sorted(кам[i] for i in МК))
for k, n in sorted(ит.items()): print("  %5d  %s" % (n, k))
print("\nроль первого письма:", перв_роль.most_common(12))
print("\nнеиспользованная лучшая роль (что упустили):"); [print("   %4d  %s" % (n, k)) for k, n in недобор_роль.most_common(14)]
if "--primery" in sys.argv:
    print("\nПРИМЕРЫ 1 (первое письмо не на лучший):"); [print("  ", x) for x in прим1]
    print("\nПРИМЕРЫ 2 (не использован адрес выше):"); [print("  ", x) for x in прим2]
