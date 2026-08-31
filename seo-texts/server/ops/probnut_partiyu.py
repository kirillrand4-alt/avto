# -*- coding: utf-8 -*-
"""Отдельный прогон пробы по очереди: гоняем штатный тик без пауз между ними.

Штатный цикл делает 40 адресов раз в 300 секунд — это 480 в час, и свежая
партия ждёт своей очереди часами. Здесь тот же самый AddrProbeLoop.tick(),
только вызываем его подряд: вежливость к чужим серверам живёт ВНУТРИ probe()
(pause_sec, per_domain), её мы не трогаем — убираем лишь простой между тиками.

Резюмируемо и durable: после каждого тика пишем строку в jsonl с fsync.
"""
import io
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\proba-partii.jsonl"
БЮДЖЕТ = int(sys.argv[1]) if len(sys.argv) > 1 else 2400

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
цикл = build_addr_probe(store, cfg)
print("проба включена в конфиге: %s; пачка %s, штатный интервал %s с"
      % (цикл.enabled(), цикл.batch, getattr(цикл, "interval_sec", "?")))
if not цикл.enabled():
    print("проба выключена конфигом — прогон бессмыслен, выхожу")
    raise SystemExit(0)


def без_пробы():
    c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                        timeout=60)
    n = c.execute(
        "SELECT COUNT(DISTINCT lower(trim(cr.email))) FROM confirm_reviews cr"
        " LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
        " WHERE cr.status IN ('pending','approved','edited')"
        "   AND COALESCE(cr.kind,'outbound') <> 'reply'"
        "   AND p.email IS NULL").fetchone()[0]
    c.close()
    return n


было = без_пробы()
print("адресов очереди без пробы на старте: %d" % было)
т0 = time.time()
всего = {"проверено": 0, "снято_писем": 0}
пусто_подряд = 0
тиков = 0
while time.time() - т0 < БЮДЖЕТ:
    try:
        итог = цикл.tick()
    except Exception as e:                                    # noqa: BLE001
        print("тик упал: %s: %s" % (type(e).__name__, str(e)[:140]))
        time.sleep(5)
        continue
    тиков += 1
    for к, v in итог.items():
        if isinstance(v, int):
            всего[к] = всего.get(к, 0) + v
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time()), "tik": тиков,
                            "itog": {к: v for к, v in итог.items()
                                     if isinstance(v, int)}},
                           ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    print("тик %3d: проверено %3d, снято писем %3d, осталось без пробы %d "
          "(%.0f с)" % (тиков, итог.get("проверено", 0),
                        итог.get("снято_писем", 0), без_пробы(),
                        time.time() - т0))
    if itog_pusto := (итог.get("проверено", 0) == 0):
        пусто_подряд += 1
        if пусто_подряд >= 2:
            print("два пустых тика подряд — проверять больше нечего")
            break
        time.sleep(3)
    else:
        пусто_подряд = 0

стало = без_пробы()
print("\n=== ИТОГ ПРОГОНА ПРОБЫ ===")
print("тиков: %d, время %.0f с" % (тиков, time.time() - т0))
print("проверено адресов: %d" % всего.get("проверено", 0))
for к in ("есть", "принимает всё", "нет ящика", "нет MX", "неясно",
          "отказ пробе"):
    if всего.get(к):
        print("   %-16s %5d" % (к, всего[к]))
print("снято писем из очереди: %d" % всего.get("снято_писем", 0))
print("адресов без пробы: было %d, стало %d" % (было, стало))
