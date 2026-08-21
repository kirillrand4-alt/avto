# -*- coding: utf-8 -*-
"""Сходится ли НАПРАВЛЕНИЕ ЯЩИКА с направлением письма (сегодняшняя отправка).

Расхождение «письмо vs кампания» проверено - его нет. Третье место, где
направление живёт отдельно, - ПОЧТОВЫЙ ЯЩИК: у него своё направление
(sender.py:539), и заслон подтверждения его не смотрит (confirm.py:941,
vne_bazy.py:18). Письмо Meyer из КЦ-ящика даёт получателю чужой домен и
чужую подпись - в панели это и выглядит «не то направление».

Направление ящика берём из БД (на раннере нет pyyaml), плюс голос тела.
"""
import json
import re
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

таблицы = [р[0] for р in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
ящик_напр = {}
for т in ("mailboxes", "mailbox", "boxes", "smtp_accounts"):
    if т not in таблицы:
        continue
    колонки = [р[1] for р in c.execute(f"PRAGMA table_info({т})").fetchall()]
    поле_а = next((k for k in ("email", "from_email", "address", "user")
                   if k in колонки), None)
    поле_н = next((k for k in ("division", "napravlenie", "segment")
                   if k in колонки), None)
    print(f"таблица {т}: адрес={поле_а} направление={поле_н}")
    if поле_а and поле_н:
        for р in c.execute(f"SELECT {поле_а} a, {поле_н} d FROM {т}"):
            if р["a"]:
                ящик_напр[str(р["a"]).lower()] = str(р["d"] or "").lower()
print(f"ящиков с направлением: {len(ящик_напр)}")

строки = c.execute(
    "SELECT m.id AS mid, m.from_email, m.to_email, m.subject, m.updated_at, "
    "       m.campaign_id, COALESCE(cr.panel_json,'') AS pj, "
    "       COALESCE(m.body,'') AS body "
    "  FROM messages m LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    " WHERE m.status='sent' AND substr(m.updated_at,1,10)='2026-08-21' "
    " ORDER BY m.updated_at"
).fetchall()

плохо, счёт, домены = [], {}, {}
for р in строки:
    try:
        п = json.loads(р["pj"] or "{}")
    except Exception:                                              # noqa: BLE001
        п = {}
    д = str(((п.get("letter") or {}).get("division"))
            or п.get("letter_division") or "")
    я = str(р["from_email"] or "").lower()
    ян = ящик_напр.get(я, "")
    тело = str(р["body"] or "")
    голос = ("kc" if re.search(r"Компрессор\s*Центр", тело, re.I) else
             "meyer" if re.search(r"Meyer|Мейер", тело, re.I) else "")
    дом = я.split("@")[-1] if "@" in я else "?"
    домены[f"{д or '?'} <- {дом}"] = домены.get(f"{д or '?'} <- {дом}", 0) + 1
    к = f"письмо={д or '?'} ящик={ян or '?'} голос={голос or '?'}"
    счёт[к] = счёт.get(к, 0) + 1
    if д and ((ян and ян != д) or (голос and голос != д)):
        плохо.append((р["mid"], я, р["to_email"], д, ян, голос, р["subject"]))

print("\nнаправление письма <- домен ящика:")
for к, н in sorted(домены.items(), key=lambda x: -x[1]):
    print(f"  {н:>3}  {к}")
print("\nраскладка (письмо / ящик / голос тела):")
for к, н in sorted(счёт.items(), key=lambda x: -x[1]):
    print(f"  {н:>3}  {к}")
print(f"\nрасхождений: {len(плохо)}")
for r in плохо[:15]:
    print(f"  msg{r[0]} {r[1]} -> {r[2]}")
    print(f"       письмо={r[3]} ящик={r[4] or '-'} голос={r[5] or '-'} | "
          f"{str(r[6])[:60]}")
