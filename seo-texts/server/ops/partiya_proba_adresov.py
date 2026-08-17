# -*- coding: utf-8 -*-
"""Довести проверку адресов ПАРТИИ до конца, не ломая штатную выкладку.

Беда, найденная 17.08: штатный probe_sync дописывает новые адреса к общему
заданию и режет список по размеру партии (400). В задании уже стояли сотни
адресов обычной очереди, мои 828 встали в хвост и обрезались - из них в
работу попали 52. Работник при этом живой: 2485 вердиктов за два часа.

Здесь не трогаем штатный механизм, а просто держим НАШИ адреса в голове
задания и будим работника кругами: положили сотню -> толкнули -> забрали
вердикты -> следующая сотня. Штатный цикл продолжает работать как работал.

Резюмируемо: состояние - в самой базе вердиктов, повторный запуск
продолжает с того места, где остановились. Самоограничение по времени -
серверное задание режется на 1800с.
"""
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.probe_sync import build_probe_sync                # noqa: E402
from sender.store import Store                                # noqa: E402

ГРУППА = "Партия 935"
ПОРЦИЯ = 100          # столько работник берёт за один толчок (его потолок)
ПАУЗА = 45            # сколько ждём между кругами
СТАРТ = time.time()
ЛИМИТ_СЕК = (int(sys.argv[1]) if len(sys.argv) > 1 else 1650) - 120

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
probe = build_addr_probe(store, cfg)
sync = build_probe_sync(store, probe.probe_, cfg)


def nashi_bez_verdikta():
    группы = store.recipient_groups().get("по_id") or {}
    адреса = set()
    for rid, g in группы.items():
        if ГРУППА not in g:
            continue
        rec = store.get_recipient(rid)
        e = str(getattr(rec, "email", "") or "").strip().lower()
        if e and "@" in e:
            адреса.add(e)
    with store._lock:
        есть = {e for (e,) in store._conn.execute(
            "SELECT lower(email) FROM addr_probe")}
    return sorted(адреса - есть), len(адреса), len(адреса & есть)


круг = 0
while time.time() - СТАРТ < ЛИМИТ_СЕК:
    круг += 1
    ждут, всего, готово = nashi_bez_verdikta()
    print(f"[круг {круг}] партия {всего} | с вердиктом {готово} | "
          f"ждут {len(ждут)}")
    if not ждут:
        print("вся партия проверена")
        break

    порция = ждут[:ПОРЦИЯ]
    # Кладём НАШИ в ГОЛОВУ задания, сохраняя хвост чужих: штатная очередь
    # продолжает проверяться, просто после нас.
    было = []
    try:
        сырое = sync._дроп("GET", "probe-zadanie.json").decode("utf-8", "replace")
        v = json.loads(сырое)
        было = v.get("emails") if isinstance(v, dict) else v
        было = [str(x).strip().lower() for x in (было or [])]
    except Exception as e:                                     # noqa: BLE001
        print("  задания ещё нет:", str(e)[:70])
    список, видели = [], set()
    for а in порция + было:
        if а and а not in видели:
            видели.add(а)
            список.append(а)
    список = список[:400]
    sync._дроп("PUT", "probe-zadanie.json",
               json.dumps(список, ensure_ascii=False).encode("utf-8"))
    наших_в_задании = sum(1 for а in список if а in set(порция))
    print(f"  в задании {len(список)}, из них наших {наших_в_задании}")

    try:
        sync._толкнуть(ПОРЦИЯ)
        print("  работник разбужен")
    except Exception as e:                                     # noqa: BLE001
        print("  толкнуть не вышло:", str(e)[:90])

    time.sleep(ПАУЗА)
    try:
        итог = sync.забрать()
        print("  забрано:", {k: v for k, v in (итог or {}).items()
                             if k in ("строк", "применено", "ошибка")})
    except Exception as e:                                     # noqa: BLE001
        print("  забрать не вышло:", str(e)[:90])

ждут, всего, готово = nashi_bez_verdikta()
print(f"\nитог: партия {всего} | с вердиктом {готово} | ждут {len(ждут)}")
with store._lock:
    ряд = store._conn.execute(
        "SELECT verdict, COUNT(*) FROM addr_probe GROUP BY verdict").fetchall()
print("вердикты в базе:", dict(ряд))
