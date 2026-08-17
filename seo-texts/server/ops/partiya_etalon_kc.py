# -*- coding: utf-8 -*-
"""Эталон КЦ: письма кампании 10, которые РЕАЛЬНО ушли, против свежих.

Первая сверка взяла эталоном письма со статусом 'sent' - и все четыре
оказались Meyer. Сравнивать с ними письма КЦ нельзя: у направлений разный
канон (у Meyer представление по имени и ссылка на видео, у КЦ - заход
«смотрел профиль» и подпись Компрессор Центра). Здесь берём эталон по
send_log: там лежат письма, которые действительно отправлены.

Плюс проверяем две находки первой сверки:
  * подстановка ИМЯ_ОТПРАВИТЕЛЯ, оставшаяся в теле;
  * расхождение направления: panel.division против campaign_id письма, и
    выставила ли панель stop_flags.
"""
import io
import json
import os
import re
import sqlite3
import sys
import urllib.request

БАЗА = r"C:\sender\sender.db"
ОТЧЁТ = r"C:\sender\_ops\ETALON-KC.md"
ОТ = int(sys.argv[1]) if len(sys.argv) > 1 else 1259
ДО = int(sys.argv[2]) if len(sys.argv) > 2 else 1276

conn = sqlite3.connect(f"file:{БАЗА}?mode=ro", uri=True, timeout=30)
conn.row_factory = sqlite3.Row

С = []


def п(s=""):
    С.append(s)


def слов(т):
    return len([w for w in re.split(r"\s+", т or "") if w.strip()])


ПОДСТАНОВКИ = ("ИМЯ_ОТПРАВИТЕЛЯ", "ИМЯ_", "{name}", "[имя]", "XXX",
               "ФИО_", "_ОТПРАВИТЕЛЯ", "SENDER_NAME")


def тело(r):
    return (r["edited_body"] or r["body"] or "")


def разбор(r, метка):
    b = тело(r)
    s = r["edited_subject"] or r["subject"] or ""
    try:
        panel = json.loads(r["panel_json"] or "{}")
    except Exception:                                          # noqa: BLE001
        panel = {}
    комп = (panel.get("company") or {})
    див_карточки = str(комп.get("division") or "")
    див_письма = "kc" if r["campaign_id"] == 10 else (
        "meyer" if r["campaign_id"] == 11 else str(r["campaign_id"]))
    флаги = panel.get("stop_flags") or []
    подст = [p for p in ПОДСТАНОВКИ if p in b or p in s]
    п(f"### {метка} #{r['id']} — "
      f"{str(комп.get('name') or '')[:44]} (кампания {r['campaign_id']}, "
      f"{r['status']})")
    п()
    п(f"**Тема:** {s}")
    п()
    п("```")
    п(b.strip())
    п("```")
    п()
    п(f"слов {слов(b)} | направление карточки **{див_карточки or '?'}** | "
      f"направление письма **{див_письма}** | "
      f"{'СОВПАДАЕТ' if див_карточки == див_письма else '**РАСХОЖДЕНИЕ**'}")
    п(f"stop_flags панели: {флаги or 'нет'}")
    if подст:
        п(f"**ПОДСТАНОВКА В ТЕЛЕ: {подст}**")
    п(f"карточка: activity={str(комп.get('activity'))[:150]!r} | "
      f"источник={комп.get('activity_source')!r} | "
      f"проверено={комп.get('activity_verified')}")
    п(f"why_equipment={комп.get('why_equipment')!r}")
    п()
    return {"подстановка": bool(подст),
            "расхождение": див_карточки != див_письма and bool(див_карточки),
            "слов": слов(b), "флаги": bool(флаги)}


п("# Эталон КЦ против свежих писем")
п()

# --- эталон: кампания 10, реально отправленные --------------------------
отправленные = [int(x["message_id"]) for x in conn.execute(
    "SELECT message_id FROM send_log WHERE campaign_id=10 "
    "AND outcome='sent' ORDER BY id DESC LIMIT 40") if x["message_id"]]
п(f"## Эталон — письма КЦ, реально ушедшие ({len(отправленные)} в send_log)")
п()
эталон = []
for mid in отправленные:
    r = conn.execute("SELECT * FROM confirm_reviews WHERE message_id=?",
                     (mid,)).fetchone()
    if r and тело(r):
        эталон.append(r)
    if len(эталон) >= 4:
        break
if not эталон:
    п("карточек по этим message_id в очереди нет — письма ушли мимо очереди")
свод_э = [разбор(r, "УШЛО (КЦ)") for r in эталон]

# --- свежие --------------------------------------------------------------
п("## Свежие письма после правки")
п()
свежие = list(conn.execute(
    "SELECT * FROM confirm_reviews WHERE id BETWEEN ? AND ? ORDER BY id",
    (ОТ, ДО)))
свод_с = [разбор(r, "ПОСЛЕ ПРАВКИ") for r in свежие]

п("## Итог")
п()
п(f"| | эталон КЦ | свежие |")
п("|---|---|---|")
п(f"| писем | {len(свод_э)} | {len(свод_с)} |")
п(f"| с подстановкой в теле | {sum(1 for x in свод_э if x['подстановка'])} | "
  f"**{sum(1 for x in свод_с if x['подстановка'])}** |")
п(f"| направление карточки ≠ письма | {sum(1 for x in свод_э if x['расхождение'])} | "
  f"**{sum(1 for x in свод_с if x['расхождение'])}** |")
п(f"| со stop_flags | {sum(1 for x in свод_э if x['флаги'])} | "
  f"{sum(1 for x in свод_с if x['флаги'])} |")
если_э = [x["слов"] for x in свод_э]
если_с = [x["слов"] for x in свод_с]
п(f"| слов (мин-макс) | {min(если_э) if если_э else '—'}-"
  f"{max(если_э) if если_э else '—'} | "
  f"{min(если_с) if если_с else '—'}-{max(если_с) if если_с else '—'} |")

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/ETALON-KC.md",
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as r:
        r.read()
    print("отчёт на дропе: ETALON-KC.md")
except Exception as ex:                                        # noqa: BLE001
    print("на дроп не уехал:", str(ex)[:160])

print(f"эталон КЦ: {len(свод_э)} писем")
print(f"свежих: {len(свод_с)}, с подстановкой "
      f"{sum(1 for x in свод_с if x['подстановка'])}, с расхождением "
      f"направления {sum(1 for x in свод_с if x['расхождение'])}")
