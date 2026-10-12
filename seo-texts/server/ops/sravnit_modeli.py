# -*- coding: utf-8 -*-
"""Сравнить качество писем: sonnet против opus на ОДНИХ И ТЕХ ЖЕ компаниях.

Владелец 12.10: «давай сравним по качеству письма на соннет и опусе».

Честные условия:
  * 8 компаний из «идеальных» партии «Россия 9000», не из партии 500,
    по одной на отрасль (8 разных отраслей);
  * пишет ТОЛЬКО заданная модель: запасная — она же (иначе при сбое
    шлюза письмо молча допишет другая и сравнение поплывёт);
  * проверки одинаковые для обоих — sonnet, те же круги правок и гейт,
    best_of из конфига;
  * В ОЧЕРЕДЬ НИЧЕГО НЕ КЛАДЁМ: генератор зовём напрямую, результат —
    в _ops/sravnenie-modeley.json (fsync). Иначе одной компании легло бы
    два письма, и одно могли бы случайно отправить.

    sravnit_modeli.py --zapusk     — выбрать компании и запустить фоном
    sravnit_modeli.py --rabota     — сам прогон (зовёт запуск)
    sravnit_modeli.py              — показать, что готово
"""
import io
import json
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, r"C:\sender")
ВЫХОД = r"C:\sender\_ops\sravnenie-modeley.json"
ВЫБОР = r"C:\sender\_ops\sravnenie-vybor.json"
МОДЕЛИ = ("claude-opus-4-8", "claude-sonnet-4-6")
ПРОВЕРКА = "claude-sonnet-4-6"
ОТРАСЛИ = ["Мясо, птица, молоко", "Лес и деревообработка",
           "Горнодобыча, нерудные", "Зерно, мука, элеваторы, семена",
           "Пластик и полимеры", "Кофе, чай, специи",
           "Хлеб, кондитерка, макароны", "Стекло"]


def сохранить(д):
    with io.open(ВЫХОД, "w", encoding="utf-8") as ф:
        json.dump(д, ф, ensure_ascii=False)
        ф.flush()
        os.fsync(ф.fileno())


if "--zapusk" in sys.argv:
    import sqlite3
    ид = json.load(io.open(r"C:\sender\_ops\idealnye-9000.json", encoding="utf-8"))
    в500 = set(json.load(io.open(r"C:\sender\_ops\partiya-500.json", encoding="utf-8")))
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
    c.row_factory = sqlite3.Row
    кандидаты = [x for x in ид.get("Россия 9000") or [] if x not in в500]
    выбор = []
    for о in ОТРАСЛИ:
        for р in c.execute(
                "SELECT id FROM recipients WHERE segment=? AND id IN (%s) "
                "ORDER BY id LIMIT 1" % ",".join(str(int(x)) for x in кандидаты),
                (о,)):
            выбор.append(р["id"])
    if os.path.exists(ВЫБОР):
        выбор = json.load(io.open(ВЫБОР, encoding="utf-8"))   # те же компании
    json.dump(выбор, io.open(ВЫБОР, "w", encoding="utf-8"))
    print("выбрано компаний: %d" % len(выбор))
    # ПО ПРОЦЕССУ НА МОДЕЛЬ: запасная модель задаётся переменной окружения
    # процесса, у каждого своя — прогоны идут параллельно и не мешают.
    лог = io.open(r"C:\sender\_ops\sravnenie.log", "a", encoding="utf-8")
    for модель in МОДЕЛИ:
        окр = dict(os.environ, LENS_FALLBACK_MODEL=модель)
        п = subprocess.Popen([sys.executable, os.path.abspath(__file__),
                              "--rabota", модель],
                             cwd=r"C:\sender", stdout=лог, stderr=лог, env=окр,
                             creationflags=0x00000008 | 0x00000200)
        print("   %s: pid %d" % (модель, п.pid))
    print("=== СРАВНЕНИЕ: ЗАПУЩЕНО ===")
    sys.exit(0)

if "--rabota" in sys.argv:
    from concurrent.futures import ThreadPoolExecutor
    from sender.ai_quota import build_ai_quota
    from sender.ai_letter import AiLetterGen, load_facts
    from sender.config import Config
    from sender.review_lenses import default_caller
    from sender.store import Store

    модель = sys.argv[sys.argv.index("--rabota") + 1]
    файл = ВЫХОД.replace(".json", "-%s.json" % модель)
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    q = build_ai_quota(store, cfg)
    best = int(cfg.get("ai_quota.best_of", 2) or 2)
    выбор = json.load(io.open(ВЫБОР, encoding="utf-8"))
    получатели = [r for r in (store.get_recipient(int(x)) for x in выбор) if r]
    поток = {"model": модель, "старт": time.strftime("%H:%M:%S"),
             "компании": [{"id": r.id, "name": r.company_name,
                           "otrasl": r.segment, "email": r.email}
                          for r in получатели],
             "письма": {}, "вызовов": 0}
    замок = threading.Lock()

    def записать():
        with io.open(файл, "w", encoding="utf-8") as ф:
            json.dump(поток, ф, ensure_ascii=False)
            ф.flush()
            os.fsync(ф.fileno())

    записать()

    def caller(prompt):
        with замок:
            поток["вызовов"] += 1
        текст, ответила = default_caller(prompt, max_tokens=8000, model=модель)
        if ответила and ответила != модель:
            with замок:
                поток.setdefault("подмена", []).append(ответила)
        return текст

    def checker(prompt):
        текст, _ = default_caller(prompt, max_tokens=8000, model=ПРОВЕРКА)
        return текст

    def батч(кусок):
        t0 = time.time()
        ген = AiLetterGen(caller, facts=load_facts(), best_of=best,
                          checker=checker)
        reqs = [q._request(r) for r in кусок]
        q._add_ideas_generic(reqs)
        out = ген.generate(reqs)
        with замок:
            for j, r in enumerate(кусок):
                L = out.ok.get(j)
                if L:
                    поток["письма"][str(r.id)] = {
                        "статус": "ok", "тема": L.get("subject"),
                        "текст": L.get("body"),
                        "кругов": len(L.get("rounds") or []),
                        "сек": round(time.time() - t0)}
                else:
                    черн = (getattr(out, "drafts", None) or {}).get(j) or {}
                    поток["письма"][str(r.id)] = {
                        "статус": "брак",
                        "причины": [str(x)[:200] for x in
                                    (out.rejected.get(j) or [])][:4],
                        "тема": черн.get("subject", ""),
                        "текст": черн.get("body", ""),
                        "сек": round(time.time() - t0)}
            записать()

    try:
        куски = [получатели[n:n + 4] for n in range(0, len(получатели), 4)]
        with ThreadPoolExecutor(max_workers=len(куски)) as пул:
            list(пул.map(батч, куски))
    except Exception as e:  # noqa: BLE001
        поток["ошибка"] = str(e)[:300]
    поток["финиш"] = time.strftime("%H:%M:%S")
    записать()
    sys.exit(0)

# --- показать, что готово ---
for модель in МОДЕЛИ:
    файл = ВЫХОД.replace(".json", "-%s.json" % модель)
    try:
        п = json.load(io.open(файл, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        print("   %-20s файла нет" % модель)
        continue
    ок = sum(1 for x in п["письма"].values() if x["статус"] == "ok")
    print("   %-20s старт %s финиш %s | готово %d из %d (ok %d, брак %d), "
          "вызовов писателя %d%s%s"
          % (модель, п.get("старт"), п.get("финиш", "—"), len(п["письма"]),
             len(п["компании"]), ок, len(п["письма"]) - ок, п["вызовов"],
             ", подмена: %s" % п["подмена"] if п.get("подмена") else "",
             ", ОШИБКА: %s" % п["ошибка"] if п.get("ошибка") else ""))
print("=== СРАВНЕНИЕ: СТАТУС ===")
