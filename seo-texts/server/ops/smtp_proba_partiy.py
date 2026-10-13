# -*- coding: utf-8 -*-
"""SMTP-проба адресов партий «Россия 9000» и «Белорусь 1000» основным
сервером (работник на VPS удалён).

Владелец 12.10 согласился на умеренный темп. Что делает:
  * технический домен пробы (addr_probe.helo/mail_from) — штатный сборщик
    панели, НЕ домены рассылки;
  * сначала адреса партии 500 (им письма уже пишутся), потом остальные;
  * общий темп 3 с между пробами, а у крупных публичных (mail.ru, yandex
    и родня) — не чаще раза в 20 с на домен: проба с боевого IP, и
    сканировать им ящики подряд нельзя;
  * вердикт — сразу во ВСЕ ТРИ базы (sender.db/addr_probe пишет сама
    проба; enrich.db/emails и obzvon-index/email_probe — здесь), журнал с
    fsync; резюмируемо — адрес с вердиктом повторно не трогаем.

    smtp_proba_partiy.py --zapusk     — запустить фоном
    smtp_proba_partiy.py              — ход
"""
import io
import json
import os
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, r"C:\sender")
ХОД = r"C:\sender\_ops\smtp-proba-partiy.json"
ЖУРНАЛ = r"C:\sender\_ops\smtp-proba-partiy.jsonl"
ГРУППЫ = ("Россия 9000", "Белорусь 1000")
КРУПНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru",
           "yandex.ru", "ya.ru", "yandex.by", "yandex.com", "narod.ru",
           "gmail.com", "rambler.ru", "tut.by", "mail.by"}
ПАУЗА_КРУПНЫХ = 20.0

if "--zapusk" in sys.argv:
    лог = io.open(r"C:\sender\_ops\smtp-proba-partiy.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"],
                         cwd=r"C:\sender", stdout=лог, stderr=лог,
                         creationflags=0x00000008 | 0x00000200)
    io.open(r"C:\sender\_ops\smtp-proba-partiy.pid", "w").write(str(п.pid))
    time.sleep(25)
    print("проба запущена, pid %d, жив %s" % (п.pid, п.poll() is None))
    try:
        print(io.open(ХОД, encoding="utf-8").read()[:400])
    except Exception:  # noqa: BLE001
        pass
    print("=== SMTP-ПРОБА: ЗАПУЩЕНА ===")
    sys.exit(0)

if "--rabota" in sys.argv:
    from sender.addr_probe import build_addr_probe
    from sender.config import Config
    from sender.store import Store

    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    _петля = build_addr_probe(store, cfg)
    проба = getattr(_петля, "probe", None) or getattr(_петля, "probe_")
    проба.per_domain = 10 ** 6         # темп держим сами, по времени
    с = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
    с.row_factory = sqlite3.Row
    в500 = set(json.load(io.open(r"C:\sender\_ops\partiya-500.json",
                                 encoding="utf-8")))
    адреса, первые = [], []
    for р in с.execute("SELECT id, lower(email) e, inn, extra_json x "
                       "FROM recipients WHERE extra_json LIKE '%gruppy%'"):
        try:
            гр = (json.loads(р["x"] or "{}") or {}).get("gruppy") or []
        except Exception:  # noqa: BLE001
            continue
        if not any(г in гр for г in ГРУППЫ):
            continue
        (первые if р["id"] in в500 else адреса).append((р["e"], р["inn"]))
    с.close()
    # ЗАПАСНЫЕ АДРЕСА (владелец 12.10: «проба должна проверить не только
    # основные адреса, но и 3 адреса после основного, вдруг ему будем
    # писать»). Берём адреса компании из обогащения, сортируем той же
    # лесенкой ролей, что и выбор адреса письма, и добавляем три следующих.
    sys.path.insert(0, r"C:\sender\server")
    try:
        from lead_scoring import _rol_ball
    except Exception:  # noqa: BLE001
        def _rol_ball(р):
            return 4
    cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
    cx.row_factory = sqlite3.Row

    def запасные(список):
        вых, видели = [], {а for а, _ in первые + адреса}
        инны = []
        for _а, инн in список:
            if инн and инн not in инны:
                инны.append(инн)
        for инн in инны:
            свои = []
            for р in cx.execute("SELECT lower(email) e, role FROM emails "
                                "WHERE inn=?", (инн,)):
                роль = str(р["role"] or "")
                if "не для письма" in роль.lower() or _rol_ball(роль) <= 1:
                    continue
                if р["e"] in видели:
                    continue
                свои.append((_rol_ball(роль), р["e"]))
            for _б, е in sorted(свои, key=lambda x: -x[0])[:3]:
                видели.add(е)
                вых.append((е, инн))
        return вых

    зап500 = запасные(первые)
    запост = запасные(адреса)
    cx.close()
    очередь = первые + зап500 + адреса + запост
    ход = {"старт": time.strftime("%H:%M:%S"), "всего": len(очередь),
           "из_500": len(первые), "запасных_500": len(зап500),
           "основных_прочих": len(адреса), "запасных_прочих": len(запост),
           "проверено": 0, "уже_было": 0, "вердикты": {}}
    посл_домен = {}
    отложено = []

    def отметить():
        with io.open(ХОД, "w", encoding="utf-8") as ф:
            json.dump(ход, ф, ensure_ascii=False)
            ф.flush()
            os.fsync(ф.fileno())

    буфер_обзвона = []

    def слить_обзвон():
        if not буфер_обзвона:
            return
        try:
            ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
            ox.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT "
                       "PRIMARY KEY, verdict TEXT, source TEXT, answer TEXT, "
                       "ts INTEGER)")
            ox.executemany(
                "INSERT INTO email_probe (email, verdict, source, answer, ts) "
                "VALUES (?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                "verdict=excluded.verdict, answer=excluded.answer, "
                "ts=excluded.ts", буфер_обзвона)
            ox.commit()
            ox.close()
            del буфер_обзвона[:]
        except Exception:  # noqa: BLE001 - не слилось: попробуем со следующей пачкой
            pass

    def в_три_базы(адрес, инн, вер, ответ):
        ts = int(time.time())
        try:
            cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
            cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=?, "
                       "probe_answer=? WHERE lower(email)=?",
                       (вер, ts, str(ответ)[:300], адрес))
            cx.commit()
            cx.close()
        except Exception:  # noqa: BLE001
            pass
        # БАЗА ОБЗВОНА — ПАЧКАМИ. Она в режиме журнала delete: каждая запись
        # на миг запирает её для чтения, а генерация писем читает её на
        # каждую карточку («database is locked», 12.10). Копим и сливаем
        # одной транзакцией; журнал с fsync держит вердикты до слива.
        буфер_обзвона.append((адрес, вер, "smtp-server", str(ответ)[:300], ts))
        if len(буфер_обзвона) >= 200:
            слить_обзвон()
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
            ж.write(json.dumps({"ts": ts, "email": адрес, "inn": инн,
                                "verdict": вер}, ensure_ascii=False) + "\n")
            ж.flush()
            os.fsync(ж.fileno())

    отметить()
    def пройти(очередь, круг=0):
        global отложено
        while очередь:
            круг += 1
            for адрес, инн in очередь:
                if проба.cached(адрес):
                    ход["уже_было"] += 1
                    continue
                домен = адрес.rsplit("@", 1)[-1]
                if домен in КРУПНЫЕ and time.monotonic() - посл_домен.get(домен, -1e9) < ПАУЗА_КРУПНЫХ:
                    отложено.append((адрес, инн))      # вернёмся следующим кругом
                    continue
                посл_домен[домен] = time.monotonic()
                try:
                    рез = проба.probe(адрес)
                except Exception as e:  # noqa: BLE001
                    рез = {"verdict": "неясно", "answer": str(e)[:200]}
                вер = str(рез.get("verdict") or "неясно")
                ход["проверено"] += 1
                ход["вердикты"][вер] = ход["вердикты"].get(вер, 0) + 1
                в_три_базы(адрес, инн, вер, рез.get("answer") or "")
                if ход["проверено"] % 20 == 0:
                    ход["круг"] = круг
                    ход["осталось_в_круге_отложенных"] = len(отложено)
                    отметить()
            очередь, отложено = отложено, []
            if очередь:
                time.sleep(5)

        return круг

    круг = пройти(очередь)

    # ГЛУБЖЕ ПО ЛЕСЕНКЕ (владелец 13.10: «а если и следующий мёртв?» — «да,
    # доработай»). Основная очередь берёт основной адрес и ТРИ следующих. Если у
    # компании все проверенные адреса мертвы, генератору не на что перейти, а
    # до пятого адреса проба не доходила. Поэтому после основного прохода
    # добираем: компаниям, у которых живого (есть / принимает всё) нет ни
    # одного, проверяем следующие три непроверенных адреса по лесенке — и так
    # до шести раз, пока такие компании и адреса не кончатся.
    ЖИВЫЕ = ("есть", "принимает всё")
    все_инн = []
    for _а, инн in первые + адреса:
        if инн and инн not in все_инн:
            все_инн.append(инн)
    for глубина in range(1, 7):
        cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
        cx.row_factory = sqlite3.Row
        добор = []
        for инн in все_инн:
            свои = []
            живой = False
            for р in cx.execute("SELECT lower(email) e, role FROM emails WHERE inn=?", (инн,)):
                роль = str(р["role"] or "")
                if "не для письма" in роль.lower() or _rol_ball(роль) <= 1:
                    continue
                в = (проба.cached(р["e"]) or {}).get("verdict")
                if в in ЖИВЫЕ:
                    живой = True
                    break
                if not в:
                    свои.append((_rol_ball(роль), р["e"]))
            if живой or not свои:
                continue
            for _б, е in sorted(свои, key=lambda x: -x[0])[:3]:
                добор.append((е, инн))
        cx.close()
        ход["добор_глубина_%d" % глубина] = len(добор)
        отметить()
        if not добор:
            break
        круг = пройти(добор, круг)
    слить_обзвон()
    ход["финиш"] = time.strftime("%H:%M:%S")
    отметить()
    sys.exit(0)

# --- ход ---
try:
    ход = json.load(io.open(ХОД, encoding="utf-8"))
except Exception as e:  # noqa: BLE001
    print("хода нет: %s" % e)
    sys.exit(0)
print("старт %s, финиш %s, круг %s" % (ход.get("старт"), ход.get("финиш", "—"),
                                       ход.get("круг", 1)))
print("в работе %d адресов: основные 500 — %d, их запасные — %d, основные "
      "прочих — %d, их запасные — %d"
      % (ход["всего"], ход["из_500"], ход.get("запасных_500", 0),
         ход.get("основных_прочих", 0), ход.get("запасных_прочих", 0)))
print("проверено %d, вердикт уже был у %d" % (ход["проверено"], ход["уже_было"]))
for в, n in sorted(ход["вердикты"].items(), key=lambda x: -x[1]):
    print("   %-16s %5d" % (в, n))
print("=== SMTP-ПРОБА: ХОД ===")
