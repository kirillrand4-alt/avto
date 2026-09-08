# -*- coding: utf-8 -*-
"""Протолкнуть проверку адресов очереди: несколько тиков probe_sync подряд.

Владелец 08.09: «делай чтобы проверена была, или вручную протолкни чтобы
проверил».

Цикл сам ходит раз в 10 минут и будит работника заданием не больше чем на
100 адресов за раз. Непроверенных в очереди больше тысячи, поэтому гоняем
тик руками несколько раз подряд: каждый забирает готовые вердикты и
публикует новую порцию.

Наружу это не шлёт ни одного письма - только обмен с нашим же дропом.

    python protolknut_proby.py [тиков=6] [пауза=20]
"""
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server\ops")
from sender.addr_probe import build_addr_probe                  # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.probe_sync import build_probe_sync                  # noqa: E402
from sender.store import Store                                  # noqa: E402
import varianty_pisma as V                                      # noqa: E402

ТИКОВ = 6
ПАУЗА = 20
for а in sys.argv[1:]:
    if а.startswith(("тиков=", "tikov=")):
        ТИКОВ = max(1, min(int(а.split("=", 1)[1]), 40))
    elif а.startswith(("пауза=", "pauza=")):
        ПАУЗА = max(0, min(int(а.split("=", 1)[1]), 120))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
probe = build_addr_probe(store, cfg)
sync = build_probe_sync(store, probe.probe_, cfg)


def без_вердикта():
    with store._lock:
        пробы = {str(r["email"] or "").lower() for r in
                 store._conn.execute("SELECT email FROM addr_probe")}
        адреса = [str(r["email"] or "").lower() for r in store._conn.execute(
            "SELECT email FROM confirm_reviews WHERE subject IN (%s) "
            "  AND status IN ('pending','approved')"
            % ",".join("?" * len(V.ТЕМЫ)), tuple(V.ТЕМЫ))]
    return sum(1 for а in адреса if а not in пробы), len(адреса)


до, всего = без_вердикта()
print("цикл проб: включён=%s, живой=%s, интервал %s с"
      % (sync.enabled(), sync.running(), sync.interval))
print("последний обмен: %s" % str(sync.last)[:160])
print("в очереди %d писем, без вердикта %d" % (всего, до))
print("")

свод = Counter()
for n in range(1, ТИКОВ + 1):
    try:
        итог = sync.tick()
    except Exception as ex:                                     # noqa: BLE001
        print("   тик %d упал: %s: %s" % (n, type(ex).__name__, str(ex)[:110]),
              flush=True)
        break
    принято = итог.get("принято") or {}
    свод["опубликовано"] += int(итог.get("в_задании") or итог.get("опубликовано") or 0)
    свод["ловушек снято"] += int(итог.get("ловушек") or 0)
    if isinstance(принято, dict):
        for к, в in принято.items():
            if isinstance(в, int):
                свод["принято: " + str(к)] += в
    осталось, _ = без_вердикта()
    print("   тик %d: %s | без вердикта осталось %d"
          % (n, str(итог)[:130], осталось), flush=True)
    if n < ТИКОВ:
        time.sleep(ПАУЗА)

после, всего = без_вердикта()
print("")
print("=" * 74)
print("=== ПРОТАЛКИВАНИЕ ПРОБ ===")
for к, в in свод.most_common():
    print("   %-30s %6d" % (к, в))
print("без вердикта было %d, стало %d (закрыто %d из %d писем очереди)"
      % (до, после, до - после, всего))
