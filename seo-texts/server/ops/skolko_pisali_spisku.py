# -*- coding: utf-8 -*-
"""Сколько раз мы писали компаниям из списка (CSV с колонкой «ИНН», файл с дропа), без активных сделок КЦ.
Письмо = отправленное письмо кампании (messages sent) + отправленная карточка-ответ/напоминание
(confirm_reviews kind=reply, status=sent). Пишет _ops/<имя>-pisali.csv (ИНН; название; категория; писем;
напоминаний; направления; последнее; сделка КЦ). Только чтение базы.
    skolko_pisali_spisku.py <имя_файла_на_дропе> [порог=2]"""
import csv, io, re, sqlite3, sys
from collections import Counter, defaultdict
ФАЙЛ = r"C:\seostat\drop\drop-storage" + "\\" + sys.argv[1]
ПОРОГ = int(next((a for a in sys.argv[2:] if a.isdigit()), "2"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
def цифры(x): return "".join(ч for ч in str(x or "") if ч.isdigit())
строки = list(csv.DictReader(io.open(ФАЙЛ, encoding="utf-8-sig"), delimiter=";"))
спис = {цифры(r.get("ИНН")): r for r in строки if цифры(r.get("ИНН"))}
print("в файле: %d строк, ИНН: %d" % (len(строки), len(спис)))
кам = {i: str(n) for i, n in c.execute("SELECT id, name FROM campaigns")}
def напр(имя): return "Meyer" if re.search(r"(?i)meyer|мейер|фса", имя) else "КЦ"
писем, напр_к, посл = Counter(), defaultdict(Counter), {}
for inn, cid, sa in c.execute("SELECT r.inn, m.campaign_id, m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'"):
    ц = цифры(inn)
    if ц in спис:
        писем[ц] += 1; напр_к[ц][напр(кам.get(cid, ""))] += 1; посл[ц] = max(посл.get(ц, ""), str(sa or ""))
отв = Counter()
for inn, т in c.execute("SELECT inn, decided_at FROM confirm_reviews WHERE kind='reply' AND status='sent'"):
    ц = цифры(inn)
    if ц in спис: отв[ц] += 1; посл[ц] = max(посл.get(ц, ""), str(т or ""))
кц = set()
try:
    for (inn,) in c.execute("SELECT inn FROM sdelki_napr WHERE kc=1"): кц.add(цифры(inn))
except sqlite3.Error: pass
ит = Counter(); вых = []
for ц, r in спис.items():
    всего = писем[ц] + отв[ц]
    ит["писали %s" % ("0" if всего == 0 else "1" if всего == 1 else "2+")] += 1
    if всего >= ПОРОГ:
        if ц in кц: ит["2+ но активная сделка КЦ — исключены"] += 1; continue
        вых.append((ц, r.get("Название", ""), r.get("Категории", ""), писем[ц], отв[ц], "+".join("%s:%d" % kv for kv in sorted(напр_к[ц].items())), посл.get(ц, "")[:10]))
вых.sort(key=lambda x: -(x[3] + x[4]))
путь = r"C:\sender\_ops\%s-pisali.csv" % re.sub(r"\.\w+$", "", sys.argv[1])
with io.open(путь, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";"); w.writerow(["ИНН", "Название", "Категории", "Писем кампаний", "Ответов/напоминаний", "Направления", "Последнее"]); w.writerows(вых)
print(dict(ит)); print("в итоговом списке (≥%d, без сделок КЦ): %d → %s" % (ПОРОГ, len(вых), путь))
print("распределение писем:", sorted(Counter(min(x[3] + x[4], 6) for x in вых).items()))
print("по направлениям:", Counter("Meyer+КЦ" if ("Meyer" in x[5] and "КЦ" in x[5]) else ("Meyer" if "Meyer" in x[5] else "КЦ" if "КЦ" in x[5] else "только ответы") for x in вых).most_common())
for x in вых[:15]: print("  ", x)
if "--vse" in sys.argv:
    # владелец 10.11: «отметь есть ли среди 8к активные сделки, я формирую новую базу» — весь файл + колонки
    import json as _j
    сд = {}
    try:
        for inn, m, k, sc, det in c.execute("SELECT inn, meyer, kc, sc, detali FROM sdelki_napr"): сд[цифры(inn)] = (m, k, sc, det)
    except sqlite3.Error: pass
    путь2 = r"C:\sender\_ops\%s-sdelki.csv" % re.sub(r"\.\w+$", "", sys.argv[1])
    поля = list(строки[0].keys()) + ["Активная сделка", "Сделка КЦ", "Сделка Meyer", "Сделка СЦ", "Сделки (ID: воронка, стадия)", "Писали раз"]
    сч = Counter()
    with io.open(путь2, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(поля)
        for r in строки:
            ц = цифры(r.get("ИНН")); д = сд.get(ц)
            дет = ""
            if д and д[3]:
                try: дет = "; ".join("%s: %s, %s" % (x.get("id"), x.get("v"), x.get("st")) for v in _j.loads(д[3]).values() for x in v)
                except Exception: дет = str(д[3])[:200]
            есть = bool(д and (д[0] or д[1] or д[2]))
            сч["с активной сделкой" if есть else "без сделки"] += 1
            if д: сч["КЦ"] += bool(д[1]); сч["Meyer"] += bool(д[0]); сч["СЦ"] += bool(д[2])
            w.writerow(list(r.values()) + ["да" if есть else "нет", "да" if д and д[1] else "", "да" if д and д[0] else "", "да" if д and д[2] else "", дет, писем[ц] + отв[ц]])
    print("ВЕСЬ ФАЙЛ со сделками:", dict(сч), "→", путь2)
