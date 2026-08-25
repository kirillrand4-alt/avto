# -*- coding: utf-8 -*-
"""То же сведение, но одной таблицей: партия -> куда делось каждое письмо."""
import datetime
import io
import json
import os
import sqlite3
from collections import Counter, defaultdict

ЖУРНАЛЫ = ["gen-partiya-935.jsonl", "deshevaya-partiya.jsonl",
           "tysyacha-sonnet.jsonl", "peregeneraciya-braka.jsonl",
           "peregeneraciya-meyer.jsonl", "perepisano-po-recenzii.jsonl",
           "perepisat-starye.jsonl", "dopisannye-zachiny.jsonl"]
КАТАЛОГ = r"C:\sender\_ops"
С_ДНЯ = "08-22"

письма = {}
for имя in ЖУРНАЛЫ:
    п = os.path.join(КАТАЛОГ, имя)
    if not os.path.exists(п):
        continue
    for с in io.open(п, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с.startswith("{"):
            continue
        try:
            з = json.loads(с)
        except Exception:  # noqa: BLE001
            continue
        if not з.get("review_id"):
            continue
        мод = з.get("модель") or ("механика" if "deshev" in имя else "?")
        письма[int(з["review_id"])] = мод.replace("claude-", "")

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
таб = defaultdict(Counter)
причины = defaultdict(Counter)
for rid, мод in письма.items():
    р = c.execute("SELECT cr.status st, cr.reason rs, COALESCE(m.status,'-') ms, "
                  "       COALESCE(NULLIF(m.last_error,''),'') le, "
                  "       substr(cr.created_at,6,5) д "
                  "  FROM confirm_reviews cr LEFT JOIN messages m "
                  "    ON m.id=cr.message_id WHERE cr.id=?", (rid,)).fetchone()
    if not р:
        continue
    ms, st, д = р["ms"], р["st"], (р["д"] or "??-??")
    if ms == "sent":
        к = "отправлено"
    elif ms in ("scheduled", "sending", "sending_live"):
        к = "в очереди"
    elif st in ("pending", "edited"):
        к = "ждёт"
    elif ms == "failed":
        к = "сорвалось"
    else:
        к = "снято"
        if д >= С_ДНЯ:
            # у одобренной карточки reason — это причина ОДОБРЕНИЯ
            # («bulk-to-auto»), а сняли письмо позже: правду пишет last_error.
            пр = р["rs"] if st == "skipped" else (р["le"] or р["rs"])
            причины[(мод, д)][(пр or "без пометки")[:52]] += 1
    таб[(мод, д)][к] += 1

СТОЛБЦЫ = ["отправлено", "в очереди", "ждёт", "снято", "сорвалось"]
print("%-22s %-6s %7s | %s" % ("модель", "день", "написано",
                               " ".join("%10s" % с for с in СТОЛБЦЫ)))
общий = Counter()
for (мод, д) in sorted(таб, key=lambda k: (k[1], -sum(таб[k].values()))):
    ст = таб[(мод, д)]
    print("%-22s %-6s %7d | %s" % (мод, д, sum(ст.values()),
                                   " ".join("%10d" % ст[с] for с in СТОЛБЦЫ)))
    if д >= С_ДНЯ:
        for с in СТОЛБЦЫ:
            общий[с] += ст[с]
        общий["написано"] += sum(ст.values())
print("\nс %s: написано %d | %s" % (С_ДНЯ, общий["написано"],
                                    " ".join("%s %d" % (с, общий[с])
                                             for с in СТОЛБЦЫ)))
print("\n=== ЗА ЧТО СНЯТЫ ПИСЬМА ПОСЛЕДНИХ ПАРТИЙ ===")
for (мод, д) in sorted(причины, key=lambda k: k[1]):
    if not причины[(мод, д)]:
        continue
    print("%s, %s — снято %d" % (мод, д, sum(причины[(мод, д)].values())))
    for пр, н in причины[(мод, д)].most_common(8):
        print("      %-54s %4d" % (пр, н))
