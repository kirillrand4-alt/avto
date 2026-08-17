# -*- coding: utf-8 -*-
"""Почему в журнале 159 писем, а в панели 134 карточки.

Пункт 2 «Порядка работ» из PEREDACHA-935-SLEDUYUSHCHEY-SESSII.md: пока
расхождение не объяснено, планировать добор по этим числам нельзя.

Меряем, а не гадаем. База открывается ТОЛЬКО на чтение (mode=ro): скрипт
может запускаться при живом прогоне генерации, и лишний писатель в sqlite
тут никому не нужен.

Разделение старых и новых записей журнала - по полю «этап»: его нет ни у
одной записи, сделанной до 17.08 12:43. Отметки времени в записи нет вовсе,
другого признака не существует.
"""
import io
import json
import os
import sqlite3
import sys
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
БАЗА = r"C:\sender\sender.db"
КАМПАНИИ = (10, 11)
ОТЧЁТ = r"C:\sender\_ops\RASKHOZHDENIE-159-134.md"

# --- журнал --------------------------------------------------------------
старые, новые = [], []
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    s = s.strip()
    if not s:
        continue
    try:
        z = json.loads(s)
    except Exception:                                          # noqa: BLE001
        continue
    (новые if z.get("этап") else старые).append(z)

ок_стар = [z for z in старые if z.get("ок")]
рев_стар = [z.get("review_id") for z in ок_стар if z.get("review_id")]
без_рев = [z for z in ок_стар if not z.get("review_id")]

# --- панель, только чтение ----------------------------------------------
conn = sqlite3.connect(f"file:{БАЗА}?mode=ro", uri=True, timeout=30)
conn.row_factory = sqlite3.Row

карточки = {}
for cid in КАМПАНИИ:
    for r in conn.execute(
            "SELECT id, campaign_id, recipient_id, inn, email, status, "
            "created_at FROM confirm_reviews WHERE campaign_id=?", (cid,)):
        карточки[int(r["id"])] = dict(r)

# карточки партии могли уехать и в другие кампании - смотрим по review_id
чужие = {}
for rev in set(рев_стар):
    if rev in карточки:
        continue
    r = conn.execute("SELECT id, campaign_id, recipient_id, inn, email, "
                     "status, created_at FROM confirm_reviews WHERE id=?",
                     (int(rev),)).fetchone()
    if r:
        чужие[int(rev)] = dict(r)

всего_в_кампаниях = Counter(к["campaign_id"] for к in карточки.values())
по_статусу = Counter((к["campaign_id"], к["status"]) for к in карточки.values())

# --- разбор расхождения --------------------------------------------------
счёт = Counter(рев_стар)
повторы = {rev: n for rev, n in счёт.items() if n > 1}
лишних_из_за_повторов = sum(n - 1 for n in повторы.values())

живые = [rev for rev in set(рев_стар) if rev in карточки]
не_в_кампаниях = [rev for rev in set(рев_стар) if rev not in карточки]
исчезли = [rev for rev in не_в_кампаниях if rev not in чужие]

строки = []
def п(s=""):
    строки.append(s)
    print(s)

п("# Расхождение «159 писем» против «134 карточек»")
п()
п(f"записей в журнале всего: {len(старые) + len(новые)} "
  f"(старых без этапа {len(старые)}, новых с этапом {len(новые)})")
п(f"старых записей с ок=true: {len(ок_стар)}")
п(f"  из них с review_id: {len(рев_стар)}")
п(f"  из них БЕЗ review_id: {len(без_рев)}")
п(f"различных review_id среди них: {len(set(рев_стар))}")
п()
п("## Повторные постановки одного и того же письма")
п()
п("confirm_reviews.dedup_key = «ИНН|email|кампания» под UNIQUE-индексом, а")
п("confirm_submit на конфликте делает ON CONFLICT DO NOTHING и возвращает")
п("СУЩЕСТВУЮЩИЙ review_id со status='pending'. partiya_gen.py смотрит только")
п("на status и пишет ок=true - флаг created он не проверяет. Значит три")
п("параллельных прогона 17.08, писавшие письма одним фирмам, дали по записи")
п("ок=true каждый, а карточка в панели одна.")
п()
п(f"review_id, встречающихся в журнале больше одного раза: {len(повторы)}")
п(f"лишних записей ок=true из-за этого: {лишних_из_за_повторов}")
if повторы:
    п("  примеры (review_id: сколько раз):")
    for rev, n in sorted(повторы.items(), key=lambda p: -p[1])[:10]:
        имена = [str(z.get("имя"))[:28] for z in ок_стар
                 if z.get("review_id") == rev][:3]
        п(f"    #{rev}: {n}  {' | '.join(имена)}")
п()
п("## Куда делись карточки")
п()
п(f"review_id живы в кампаниях 10/11: {len(живые)}")
п(f"review_id уехали в другую кампанию: {len(чужие)}")
if чужие:
    for rev, к in sorted(чужие.items())[:10]:
        п(f"    #{rev} -> кампания {к['campaign_id']} ({к['status']})")
п(f"review_id, которых в базе нет вовсе (карточку сняли): {len(исчезли)}")
if исчезли:
    п(f"    {sorted(исчезли)[:20]}")
п()
п("## Панель сейчас")
п()
for cid in КАМПАНИИ:
    ст = {s: n for (c, s), n in по_статусу.items() if c == cid}
    п(f"кампания {cid}: карточек {всего_в_кампаниях.get(cid, 0)} | {ст}")
п(f"карточек в 10+11 всего: {sum(всего_в_кампаниях.values())}")
п()
п("## Сходится ли")
п()
осталось = len(ок_стар) - лишних_из_за_повторов - len(без_рев) - len(исчезли)
п(f"{len(ок_стар)} ок=true")
п(f"  - {лишних_из_за_повторов} повторных постановок на тот же review_id")
п(f"  - {len(без_рев)} записей ок=true вообще без review_id")
п(f"  - {len(исчезли)} снятых карточек")
п(f"  = {осталось} различных живых карточек из журнала")
п(f"в кампаниях 10+11 сейчас: {sum(всего_в_кампаниях.values())}")
п(f"необъяснённый остаток: {sum(всего_в_кампаниях.values()) - осталось} "
  f"(карточки не из журнала - заведены иначе, либо более ранние прогоны)")

# карточки кампаний, которых в журнале нет
не_из_журнала = [к for rev, к in карточки.items() if rev not in set(рев_стар)]
п(f"карточек в 10/11, чьего review_id в журнале НЕТ: {len(не_из_журнала)}")
if не_из_журнала:
    д = Counter(str(к["created_at"])[:10] for к in не_из_журнала)
    п(f"  по дням создания: {dict(sorted(д.items()))}")

try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write("\n".join(строки) + "\n")
    req = None
    import urllib.request
    данные = ("\n".join(строки) + "\n").encode("utf-8")
    req = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/RASKHOZHDENIE-159-134.md",
        data=данные, method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(req, timeout=120) as r:
        r.read()
    print("\nотчёт на дропе: RASKHOZHDENIE-159-134.md")
except Exception as ex:                                        # noqa: BLE001
    print("\nотчёт на дроп не уехал:", str(ex)[:200], file=sys.stderr)
