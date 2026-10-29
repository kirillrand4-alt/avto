# -*- coding: utf-8 -*-
"""Генерация яруса C ФСА v4 пачками по 100 сверху вниз по выручке (владелец
23.10: «заливай все 9 728 … и запускай генерацию пачками по 100 штук сверху
вниз по выручке»). Отсоединённый процесс-дирижёр:
  * пачка = 100 получателей volna=v4-C без письма и без попытки в журнале
    генерации, у которых проба уже дала «есть» / «принимает всё»; порядок —
    выручка сверху вниз («есть» и «принимает всё» вперемешку по выручке);
  * пачку гонит partiya_gen.py (канон Meyer, кампания 18, журнал
    gen-v4c.jsonl) и ждёт её конца; потом следующая;
  * проба идёт параллельно (smtp_proba_v4c.py, тоже сверху вниз): пачке не
    хватает проверенных — ждём 10 минут; проба кончилась и брать нечего — стоп.
Стоп руками: файл _ops/v4c-pachki.STOP. Лог — _ops/v4c-pachki.log.
    v4c_pachki.py --zapusk | (без ключа — ход)"""
import io
import json
import os
import sqlite3
import subprocess
import sys
import time

ЛОГ = r"C:\sender\_ops\v4c-pachki.log"
ЖУРНАЛ = r"C:\sender\_ops\gen-v4c.jsonl"
СПИСОК = r"C:\sender\_ops\spisok-v4c-pachka.json"
СТОП = r"C:\sender\_ops\v4c-pachki.STOP"
ХОД_ПРОБЫ = r"C:\sender\_ops\smtp-proba-v4c.json"
ПАЧКА = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--pachka=")), "100"))
# владелец 29.10: «стоп при цене письма выше 1$ на 30 компаниях»
ПОРОГ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--porog=")), "2.0")
ОКНО = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--okno=")), "10")
ОДНА = "--odna" in sys.argv   # одна пачка и стоп (проверка цены после починки кэша 23.10)
# --vsego=N (владелец 26.10: «отправим первые по выручке топ 2000 компаний»):
# при старте фиксируем N лучших по выручке готовых получателей, дальше берём только их
ВСЕГО = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--vsego=")), "0"))
ТОП = None

if "--zapusk" in sys.argv:
    л = io.open(ЛОГ, "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"] + [a for a in sys.argv[1:] if a.startswith(("--pachka=", "--vsego=", "--porog=", "--okno=")) or a == "--odna"], cwd=r"C:\sender",
                         stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    io.open(r"C:\sender\_ops\v4c-pachki.pid", "w").write(str(п.pid))
    time.sleep(15)
    print("дирижёр запущен, pid %d, жив %s" % (п.pid, п.poll() is None))
    sys.exit(0)

if "--rabota" not in sys.argv:
    try:
        т = io.open(ЛОГ, encoding="utf-8", errors="replace").read()
    except OSError:
        т = ""
    print("\n".join(s for s in т.splitlines() if s.startswith(("===", "пачка", "итог", "ждём", "стоп")))[-3000:])
    sys.exit(0)


def лог(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def попытки():
    инн = set()
    try:
        for s in io.open(ЖУРНАЛ, encoding="utf-8"):
            try:
                z = json.loads(s)
            except ValueError:
                continue
            # попытка, сгоревшая на пустом кошельке шлюза (HTTP 403, 23.10), — не попытка
            # и техсбой «прогон упал» (нет/битый JSON у модели) — тоже не попытка: перегенерируем (владелец 29.10)
            _бр = json.dumps(z.get("брак") or [], ensure_ascii=False)
            if z.get("inn") and "HTTP 403" not in _бр and "прогон упал" not in _бр:
                инн.add(str(z["inn"]))
    except OSError:
        pass
    return инн


def проба_кончилась():
    try:
        return bool(json.load(io.open(ХОД_ПРОБЫ, encoding="utf-8")).get("финиш"))
    except Exception:  # noqa: BLE001
        return False


номер = 0
лог("=== ДИРИЖЁР ЯРУСА C: старт ===")
while not os.path.exists(СТОП):
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
    проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
    с_письмом = {r[0] for r in c.execute("SELECT DISTINCT recipient_id FROM messages")}
    были = попытки()
    # гейт адресата уже сказал «не покупатель» — в журнал такие не попадают,
    # и без этого верх по выручке снова и снова приходил одними отказниками (23.10)
    try:
        были |= {str(r[0]) for r in c.execute("SELECT inn FROM target_verdicts WHERE verdict='не покупатель'")}
    except sqlite3.Error:
        pass
    кандидаты, ждут = [], 0
    for rid, em, inn, ex in c.execute("SELECT id, lower(email), inn, extra_json FROM recipients WHERE extra_json LIKE '%v4-C%'"):
        x = json.loads(ex or "{}")
        if x.get("volna") != "v4-C" or rid in с_письмом or str(inn) in были:
            continue
        в = проба.get(em, "")
        if not в:
            ждут += 1
            continue
        if в not in ("есть", "принимает всё"):
            continue
        try:
            выр = float(x.get("revenue_rub") or 0)
        except (TypeError, ValueError):
            выр = 0.0
        кандидаты.append((-выр, rid))
    c.close()
    if ВСЕГО:
        if ТОП is None:
            ТОП = {r for _, r in sorted(кандидаты)[:ВСЕГО]}
            лог("топ-%d по выручке зафиксирован: %d получателей" % (ВСЕГО, len(ТОП)))
        кандидаты = [k for k in кандидаты if k[1] in ТОП]
        if not кандидаты:
            лог("=== ДИРИЖЁР ЯРУСА C: топ-%d разобран — стоп ===" % ВСЕГО)
            break
    if len(кандидаты) < ПАЧКА and not проба_кончилась() and not ВСЕГО:
        лог("ждём пробу: готовых %d, ещё без вердикта %d" % (len(кандидаты), ждут))
        time.sleep(600)
        continue
    if not кандидаты:
        лог("=== ДИРИЖЁР ЯРУСА C: брать нечего, проба кончилась — стоп ===")
        break
    номер += 1
    пачка = [r for _, r in sorted(кандидаты)[:ПАЧКА]]
    json.dump(пачка, io.open(СПИСОК, "w"))
    лог("пачка %d: %d получателей (готовых всего %d, без вердикта %d)" % (номер, len(пачка), len(кандидаты), ждут))
    with io.open(r"C:\sender\_ops\gen-v4c.log", "a", encoding="utf-8") as гл:
        гл.write("\n==== ЗАПУСК %s: пачка %d ====\n" % (time.strftime("%H:%M:%S"), номер))
        гл.flush()
        р = subprocess.run([sys.executable, r"C:\sender\server\ops\partiya_gen.py", str(len(пачка)), "5400", "meyer", "0",
                            "gruppa=ФСА волна 1", "camp_meyer=18", "zhurnal=" + ЖУРНАЛ, "threads=6",
                            "spisok=" + СПИСОК, "revenue=0", "model=claude-sonnet-4-6", "porog=" + ПОРОГ, "okno=" + ОКНО,
                            "--bez-zacepki", "--bez-predklassa"],
                           cwd=r"C:\sender", stdout=гл, stderr=гл, env=dict(os.environ, PROVIDER_THINKING_FIELD="omit"))
    try:
        хв = io.open(r"C:\sender\_ops\gen-v4c.log", encoding="utf-8", errors="replace").read()[-3000:]
        итог = [s for s in хв.splitlines() if s.startswith("итог:")]
        лог("пачка %d готова, код %s | %s" % (номер, р.returncode, итог[-1] if итог else "итога нет"))
    except OSError:
        pass
    if ОДНА:
        лог("=== ДИРИЖЁР ЯРУСА C: одна пачка (--odna) — стоп ===")
        break
    try:
        if "СТОП ПО ЦЕНЕ" in хв:   # хвост лога — это конец только что прошедшей пачки
            лог("=== ДИРИЖЁР ЯРУСА C: в пачке сработал СТОП ПО ЦЕНЕ (порог $%s на %s) — стоп ===" % (ПОРОГ, ОКНО))
            break
    except NameError:
        pass
лог("=== ДИРИЖЁР ЯРУСА C: конец ===")
