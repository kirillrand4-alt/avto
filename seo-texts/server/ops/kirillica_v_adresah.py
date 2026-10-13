# -*- coding: utf-8 -*-
"""Адреса со смешанной раскладкой: кириллица-двойник внутри латиницы.

Владелец 13.10: «поменяй на правильную и проверь через пробу». В книгах
MEYER-7 53 адреса вида abakumov@kubrotopaсk.ru (русская «с»): письмо по ним
не уйдёт. Меняем двойники (а е о р с у х к і ј ѕ) на латинские в
recipients (sender.db) и emails (enrich.db), затем проба исправленных адресов
— вердикт в три базы, письма с приговором снимаются в том же прогоне.

    kirillica_v_adresah.py             — сухой прогон
    kirillica_v_adresah.py --primenit  — исправить и запустить пробу (фон)
    kirillica_v_adresah.py --proba     — сама проба (её зовёт --primenit)
    kirillica_v_adresah.py --hod       — ход пробы
"""
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
ЖУРНАЛ = r"C:\sender\_ops\kirillica-v-adresah.jsonl"
ХОД = r"C:\sender\_ops\kirillica-proba.json"
ДВОЙНИКИ = str.maketrans({"а": "a", "е": "e", "ё": "e", "о": "o", "р": "p", "с": "c", "у": "y",
                          "х": "x", "к": "k", "і": "i", "ј": "j", "ѕ": "s"})
КИР = re.compile(r"[\u0400-\u04ff]")
АДРЕС = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
ПРИГОВОР = ("нет ящика", "нет MX")


def починить(адрес):
    """Двойники → латиница; приклеенное русское слово в начале/конце левой
    части («почтаmsk-spectech@bk.ru») — отрезаем."""
    а = адрес.lower().strip()
    if "@" in а:
        лев, прав = а.split("@", 1)
        лев = re.sub(r"^[\u0400-\u04ff]{3,}(?=[a-z0-9])|(?<=[a-z0-9])[\u0400-\u04ff]{3,}$", "", лев)
        а = лев + "@" + прав
    return а.translate(ДВОЙНИКИ)

if "--hod" in sys.argv:
    try:
        print(io.open(ХОД, encoding="utf-8").read())
    except Exception as е:  # noqa: BLE001
        print("хода нет: %s" % е)
    print("=== КИРИЛЛИЦА: ХОД ===")
    sys.exit(0)

if "--proba" in sys.argv:
    from sender.addr_probe import build_addr_probe
    from sender.config import Config
    from sender.store import Store
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    _п = build_addr_probe(store, cfg)
    проба = getattr(_п, "probe", None) or getattr(_п, "probe_")
    проба.per_domain = 10 ** 6
    адреса = []
    for с in io.open(ЖУРНАЛ, encoding="utf-8"):
        з = json.loads(с)
        if з.get("стало") and з["стало"] not in адреса:
            адреса.append(з["стало"])
    ход = {"всего": len(адреса), "проверено": 0, "вердикты": {}, "снято_писем": 0, "мёртвые": []}
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
    посл = {}
    for адрес in адреса:
        дом = адрес.rsplit("@", 1)[-1]
        if time.monotonic() - посл.get(дом, -1e9) < 20:
            time.sleep(20)
        посл[дом] = time.monotonic()
        try:
            рез = проба.probe(адрес, force=True)
        except TypeError:
            рез = проба.probe(адрес)
        except Exception as е:  # noqa: BLE001
            рез = {"verdict": "неясно", "answer": str(е)[:200]}
        вер = str(рез.get("verdict") or "неясно")
        ts = int(time.time())
        ход["проверено"] += 1
        ход["вердикты"][вер] = ход["вердикты"].get(вер, 0) + 1
        try:
            cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
            cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=?, probe_answer=? WHERE lower(email)=?",
                       (вер, ts, str(рез.get("answer") or "")[:300], адрес))
            cx.commit()
            cx.close()
            ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
            ox.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT PRIMARY KEY, verdict TEXT, "
                       "source TEXT, answer TEXT, ts INTEGER)")
            ox.execute("INSERT INTO email_probe (email, verdict, source, answer, ts) VALUES (?,?,?,?,?) "
                       "ON CONFLICT(email) DO UPDATE SET verdict=excluded.verdict, answer=excluded.answer, "
                       "ts=excluded.ts", (адрес, вер, "smtp-server", str(рез.get("answer") or "")[:300], ts))
            ox.commit()
            ox.close()
        except Exception:  # noqa: BLE001
            pass
        if вер in ПРИГОВОР:
            ход["мёртвые"].append(адрес)
            т = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            with c:
                ход["снято_писем"] += c.execute(
                    "UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE status IN "
                    "('scheduled','pending_review') AND recipient_id IN (SELECT id FROM recipients "
                    "WHERE lower(email)=?)", ("снято 13.10: приговор пробы «%s»" % вер, т, адрес)).rowcount
        with io.open(ХОД, "w", encoding="utf-8") as ф:
            json.dump(ход, ф, ensure_ascii=False)
            ф.flush()
            os.fsync(ф.fileno())
    ход["финиш"] = time.strftime("%H:%M:%S")
    with io.open(ХОД, "w", encoding="utf-8") as ф:
        json.dump(ход, ф, ensure_ascii=False)
    sys.exit(0)

ПРИМЕНИТЬ = "--primenit" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
cx.row_factory = sqlite3.Row
ЛАТ = re.compile(r"[a-z]")


def смешано(адрес):
    """Кириллица и латиница в ОДНОЙ части адреса — опечатка-двойник.
    Целиком кириллический домен (грядки.рф) — настоящий адрес, не трогаем."""
    for часть in re.split(r"[@.]", адрес.lower()):
        if КИР.search(часть) and ЛАТ.search(часть):
            return True
    return False


правки, сомнительные, idn = [], [], []
for р in c.execute("SELECT id, email FROM recipients"):
    е = str(р["email"] or "")
    if not КИР.search(е):
        continue
    if not смешано(е):
        idn.append((р["id"], е))
        continue
    стало = починить(е)
    if not АДРЕС.match(стало):
        сомнительные.append((р["id"], е))
        continue
    занят = c.execute("SELECT id FROM recipients WHERE lower(email)=? AND id<>?", (стало, р["id"])).fetchone()
    правки.append((р["id"], е, стало, занят[0] if занят else None))
адр_enrich = []
for р in cx.execute("SELECT rowid, inn, email FROM emails"):
    е = str(р["email"] or "")
    if КИР.search(е) and смешано(е):
        стало = починить(е)
        адр_enrich.append((р["rowid"], р["inn"], е, стало, bool(АДРЕС.match(стало))))
print("получатели с кириллицей в адресе: %d; исправимо %d (из них адрес уже есть у другого получателя: %d); "
      "не исправить двойниками: %d" % (len(правки) + len(сомнительные), len(правки),
                                       sum(1 for x in правки if x[3]), len(сомнительные)))
в_очереди = c.execute(
    "SELECT count(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN "
    "('scheduled','pending_review') AND r.email GLOB '*[а-яА-ЯёЁ]*'").fetchone()[0]
print("русские домены целиком (.рф/.рус — настоящие адреса): %d; писем таким в очереди: %d" % (len(idn), в_очереди))
for rid, е, ст, занят in правки[:12]:
    print("   %s: %s -> %s%s" % (rid, е, ст, " (уже есть у #%s)" % занят if занят else ""))
for rid, е in сомнительные[:8]:
    print("   НЕ ИСПРАВИТЬ %s: %s" % (rid, е))
print("enrich.emails с кириллицей: %d, исправимо %d" % (len(адр_enrich), sum(1 for x in адр_enrich if x[4])))
if ПРИМЕНИТЬ:
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
        with c:
            for rid, е, ст, занят in правки:
                if занят:
                    # такой адрес уже заведён правильно — кривой получатель лишний:
                    # его письма в очереди снимаем, сам адрес не трогаем
                    n = c.execute("UPDATE messages SET status='skipped', last_error=? WHERE recipient_id=? AND "
                                  "status IN ('scheduled','pending_review')",
                                  ("снято 13.10: кириллица в адресе, верный адрес у #%s" % занят, rid)).rowcount
                    ж.write(json.dumps({"rid": rid, "было": е, "дубль_у": занят, "снято": n},
                                       ensure_ascii=False) + "\n")
                    continue
                c.execute("UPDATE recipients SET email=?, domain=? WHERE id=?", (ст, ст.split("@")[-1], rid))
                ж.write(json.dumps({"rid": rid, "было": е, "стало": ст}, ensure_ascii=False) + "\n")
        with cx:
            for rowid, inn, е, ст, ок in адр_enrich:
                if not ок:
                    continue
                if cx.execute("SELECT 1 FROM emails WHERE inn=? AND lower(email)=?", (inn, ст)).fetchone():
                    cx.execute("DELETE FROM emails WHERE rowid=?", (rowid,))
                else:
                    cx.execute("UPDATE emails SET email=? WHERE rowid=?", (ст, rowid))
                ж.write(json.dumps({"enrich_inn": inn, "было": е, "стало": ст}, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--proba"], cwd=r"C:\sender",
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x00000008 | 0x00000200)
    time.sleep(5)
    print("исправлено; проба запущена, pid %d, жив %s" % (п.pid, п.poll() is None))
    print("=== КИРИЛЛИЦА: ПРИМЕНЕНО ===")
else:
    print("=== КИРИЛЛИЦА: СУХОЙ ПРОГОН ===")
