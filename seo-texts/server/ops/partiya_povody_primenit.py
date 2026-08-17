# -*- coding: utf-8 -*-
"""Применить приговоры по поводам: карантин сигнала и снятие письма.

Владелец 17.08: «ты удаляешь письма и новостные поводы у таких компаний?».
Проверка без применения бесполезна - 12.08 прогон нашёл 76 мёртвых адресов
и закончился строкой «снято писем: 0». Здесь приговор доводится до конца,
и ровно двумя разными действиями:

1. САМ ПОВОД уходит в карантин: signals.suspect=1. Не удаляем - _digest
   такие сигналы уже обходит стороной, а строка остаётся, если приговор
   придётся пересматривать. Карантиним ТОЛЬКО осуждённый сигнал (по ссылке
   и тексту), а не все новости компании: у неё могут быть и верные.

2. ПИСЬМО, УЖЕ СТОЯЩЕЕ В ОЧЕРЕДИ, снимается - но только если оно на этот
   повод и вправду опирается. Письмо в режиме GENERIC новость не упоминает,
   и снимать его не за что. Опору проверяем по редким словам новости в теме
   и теле: совпало хотя бы два - письмо стоит на чужом событии.

Сухой прогон; писать - argv[1] == "primenit".
"""
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                               # noqa: E402
from sender.probe_enrich import найти as найти_enrich           # noqa: E402
from sender.store import Store                                 # noqa: E402

ПРИМЕНИТЬ = len(sys.argv) > 1 and sys.argv[1] == "primenit"
ПРИГОВОРЫ = r"C:\sender\_ops\povody-prigovory.jsonl"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
# найти() умеет вернуть None, если в конфиге пути нет: тогда берём
# каноническое место рядом с базой панели, иначе оп падает на connect(None).
ENRICH = найти_enrich(cfg) or r"C:\sender\enrich.db"

# --- приговоры: по ИНН берём ПОСЛЕДНИЙ настоящий ------------------------
приговор = {}
for s in (io.open(ПРИГОВОРЫ, encoding="utf-8")
          if os.path.exists(ПРИГОВОРЫ) else []):
    try:
        z = json.loads(s)
    except Exception:                                          # noqa: BLE001
        continue
    if "своя" in (z.get("приговор") or {}):
        приговор[str(z.get("inn"))] = z          # последний побеждает

чужие = {k: v for k, v in приговор.items()
         if v["приговор"].get("своя") is False}
print(f"приговоров с решением: {len(приговор)} | ЧУЖИХ: {len(чужие)}")

# --- 1. карантин сигналов ------------------------------------------------
СЛОВО = re.compile(r"[А-Яа-яЁёA-Za-z0-9]{5,}")
ОБЩИЕ = {"компания", "предприятие", "производство", "продукции", "которая",
         "область", "района", "рублей", "новости", "завода", "завод"}


def редкие(текст, сколько=12):
    сл = [w.lower() for w in СЛОВО.findall(str(текст or ""))]
    видели, итог = set(), []
    for w in сл:
        о = w[:-2] if len(w) >= 7 else w
        if о in ОБЩИЕ or о in видели:
            continue
        видели.add(о)
        итог.append(о)
    return итог[:сколько]


карантин = Counter()
if чужие:
    con = sqlite3.connect(ENRICH, timeout=30)
    try:
        есть_suspect = any(
            r[1] == "suspect" for r in con.execute(
                "PRAGMA table_info(signals)").fetchall())
        if not есть_suspect:
            print("в signals нет колонки suspect — карантинить нечем")
        else:
            for inn, z in чужие.items():
                url = str(z.get("news_url") or "")
                what = str(z.get("news_detail") or "")[:120]
                if ПРИМЕНИТЬ:
                    cur = con.execute(
                        "UPDATE signals SET suspect=1 WHERE inn=? AND "
                        "(COALESCE(source_url,'')=? OR "
                        " COALESCE(what,'') LIKE ?)",
                        (inn, url, what + "%"))
                    карантин["строк в карантин"] += cur.rowcount
                else:
                    n = con.execute(
                        "SELECT COUNT(*) FROM signals WHERE inn=? AND "
                        "(COALESCE(source_url,'')=? OR "
                        " COALESCE(what,'') LIKE ?)",
                        (inn, url, what + "%")).fetchone()[0]
                    карантин["строк под карантин"] += n
            if ПРИМЕНИТЬ:
                con.commit()
    finally:
        con.close()
for k, n in карантин.most_common():
    print(f"  {k:<24} {n}")

# --- 2. письма очереди на чужом поводе -----------------------------------
письма = []
for ст in ("pending", "approved"):
    for r in (store.confirm_list(status=ст, limit=100000) or []):
        if int(r.get("campaign_id") or 0) in (10, 11):
            письма.append(r)
по_инн = {}
for r in письма:
    по_инн.setdefault(str(r.get("inn") or ""), []).append(r)
print(f"\nписем в очереди (pending+approved, к10/к11): {len(письма)} "
      f"| компаний {len(по_инн)}")

счёт = Counter()
на_снятие = []
for inn, z in чужие.items():
    ряд = по_инн.get(inn) or []
    if not ряд:
        счёт["чужой повод, письма нет"] += 1
        continue
    слова = редкие(f"{z.get('news_detail')} {z.get('news_type')}")
    for r in ряд:
        т = f"{r.get('subject') or ''} {r.get('body') or ''}".lower()
        попало = [w for w in слова if w in т]
        if len(попало) >= 2:
            счёт["ПИСЬМО НА ЧУЖОМ ПОВОДЕ"] += 1
            на_снятие.append((r, z, попало))
        else:
            счёт["письмо есть, но повод в нём не звучит"] += 1

for k, n in счёт.most_common():
    print(f"  {k:<38} {n}")

for r, z, попало in на_снятие:
    print(f"\n  #{r.get('id')} {str(r.get('status'))} "
          f"{str(z.get('имя'))[:40]}")
    print(f"    тема: {str(r.get('subject'))[:90]}")
    print(f"    чужая новость: {str(z.get('news_detail'))[:110]}")
    print(f"    совпавшие слова: {', '.join(попало[:6])}")
    print(f"    почему чужая: {str(z['приговор'].get('почему'))[:110]}")

if ПРИМЕНИТЬ and на_снятие:
    снято = 0
    for r, z, _ in на_снятие:
        причина = ("письмо стоит на чужой новости: "
                   + str(z["приговор"].get("почему") or "")[:120])
        if store.confirm_decide(int(r["id"]), status="skipped",
                                decided_by="суд поводов", reason=причина):
            снято += 1
    print(f"\nснято писем: {снято} из {len(на_снятие)}")
elif на_снятие:
    print(f"\nсухой прогон: снял бы {len(на_снятие)} писем")
