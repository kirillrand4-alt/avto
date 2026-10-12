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
    json.dump(выбор, io.open(ВЫБОР, "w", encoding="utf-8"))
    print("выбрано компаний: %d" % len(выбор))
    лог = io.open(r"C:\sender\_ops\sravnenie.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"],
                         cwd=r"C:\sender", stdout=лог, stderr=лог,
                         creationflags=0x00000008 | 0x00000200)
    print("сравнение запущено фоном, pid %d" % п.pid)
    print("=== СРАВНЕНИЕ: ЗАПУЩЕНО ===")
    sys.exit(0)

if "--rabota" in sys.argv:
    from sender.ai_quota import build_ai_quota
    from sender.ai_letter import AiLetterGen, load_facts
    from sender.config import Config
    from sender.review_lenses import default_caller
    from sender.store import Store

    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    q = build_ai_quota(store, cfg)
    best = int(cfg.get("ai_quota.best_of", 2) or 2)
    выбор = json.load(io.open(ВЫБОР, encoding="utf-8"))
    получатели = [store.get_recipient(int(x)) for x in выбор]
    получатели = [r for r in получатели if r is not None]
    итог = {"старт": time.strftime("%H:%M:%S"), "модели": {}, "компании": []}
    for r in получатели:
        итог["компании"].append({"id": r.id, "inn": r.inn, "email": r.email,
                                 "name": r.company_name, "otrasl": r.segment})
    сохранить(итог)
    замок = threading.Lock()

    def прогон(модель):
        поток = {"model": модель, "письма": {}, "время_с": 0, "вызовов": 0}
        t0 = time.time()
        try:
            def caller(prompt):
                поток["вызовов"] += 1
                текст, ответила = default_caller(prompt, max_tokens=8000,
                                                 model=модель)
                if ответила and ответила != модель:
                    поток.setdefault("подмена", []).append(ответила)
                return текст

            def checker(prompt):
                текст, _ = default_caller(prompt, max_tokens=8000, model=ПРОВЕРКА)
                return текст

            ген = AiLetterGen(caller, facts=load_facts(), best_of=best,
                              checker=checker)
            reqs = [q._request(r) for r in получатели]
            q._add_ideas_generic(reqs)
            for n in range(0, len(reqs), 4):
                out = ген.generate(reqs[n:n + 4])
                for j in range(len(reqs[n:n + 4])):
                    r = получатели[n + j]
                    L = out.ok.get(j)
                    if L:
                        поток["письма"][str(r.id)] = {
                            "статус": "ok", "тема": L.get("subject"),
                            "текст": L.get("body"),
                            "кругов": len(L.get("rounds") or [])}
                    else:
                        черн = (getattr(out, "drafts", None) or {}).get(j) or {}
                        поток["письма"][str(r.id)] = {
                            "статус": "брак",
                            "причины": [str(x)[:200] for x in
                                        (out.rejected.get(j) or [])][:4],
                            "тема": черн.get("subject", ""),
                            "текст": черн.get("body", "")}
        except Exception as e:  # noqa: BLE001
            поток["ошибка"] = str(e)[:300]
        поток["время_с"] = round(time.time() - t0)
        with замок:
            итог["модели"][модель] = поток
            сохранить(итог)

    # Запасная = та же модель: сбой шлюза не подменит автора письма.
    # Переменная читается внутри каждого вызова, поэтому прогоны — по
    # очереди, а не параллельно (иначе один поток перебьёт другому).
    for модель in МОДЕЛИ:
        os.environ["LENS_FALLBACK_MODEL"] = модель
        прогон(модель)
    итог["финиш"] = time.strftime("%H:%M:%S")
    сохранить(итог)
    sys.exit(0)

# --- показать, что готово ---
try:
    итог = json.load(io.open(ВЫХОД, encoding="utf-8"))
except Exception as e:  # noqa: BLE001
    print("результата нет: %s" % e)
    sys.exit(0)
print("старт %s, финиш %s" % (итог.get("старт"), итог.get("финиш", "—")))
for м, п in (итог.get("модели") or {}).items():
    ок = sum(1 for x in п["письма"].values() if x["статус"] == "ok")
    print("   %-20s писем ok %d / брак %d, %d с, вызовов писателя %d%s%s"
          % (м, ок, len(п["письма"]) - ок, п["время_с"], п["вызовов"],
             ", подмена: %s" % п["подмена"] if п.get("подмена") else "",
             ", ОШИБКА: %s" % п["ошибка"] if п.get("ошибка") else ""))
print("=== СРАВНЕНИЕ: СТАТУС ===")
