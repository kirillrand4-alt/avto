# -*- coding: utf-8 -*-
"""«Неясные» адреса - на работника VPS: у него есть обратная запись DNS.

Владелец 17.08: «PTR есть на ВПС». Это меняет роль работника целиком. У
основного сервера обратной записи нет, и корпоративные почтовики рвут с ним
сессию до вопроса про ящик: 141 ответ «Server not connected», 33 прямых
«550 rejected. ip name lookup failed», плюс заметная часть таймаутов. Это
утверждения ПРО НАС, а не про ящик, - потому и вердикт «неясно».

Работник выходит с адреса, у которого PTR есть, и тем же серверам он не
безымянный. Значит спрашивать у них должен он.

Берём только те «неясно», причина которых - наш IP, а не сам адрес.
Отказ «нет такого ящика» сюда не попадает: он уже окончателен. Кладём их
в ГОЛОВУ задания на дропе, сохраняя хвост общей очереди, и будим работника
кругами по сотне - его потолок.

Резюмируемо: состояние в самой базе вердиктов, повторный запуск продолжит.
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


# Приметы «дело не в ящике, а в нас»: сервер закрыл сессию, не ответил
# вовремя, отказал по обратной записи или отказался соединяться. Сюда НЕ
# входят «нет ящика» и «нет MX» - те окончательны и переспрашивать их
# незачем, и не входит «принимает всё» - там уже всё ясно.
НАШИ_БЕДЫ = ("not connected", "timed out", "timeout",
             "ip name lookup", "refused", "unreachable", "reset",
             "try again", "421", "disabled")


def nashi_neyasnye():
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
        ряд = store._conn.execute(
            "SELECT lower(email), COALESCE(answer,''), ts FROM addr_probe "
            "WHERE verdict='неясно'").fetchall()
    наши, спрошены = [], set()
    for e, ответ, ts in ряд:
        if e not in адреса:
            continue
        спрошены.add(e)
        о = str(ответ).lower()
        if any(п in о for п in НАШИ_БЕДЫ):
            # Уже переспрошенных работником не гоняем по кругу: у них ts
            # свежее момента запуска этого прогона.
            if str(ts or "") < МЕТКА:
                наши.append(e)
    return sorted(наши), len(адреса), len(спрошены)


МЕТКА = __import__("datetime").datetime.now(
    __import__("datetime").timezone.utc).isoformat()

круг = 0
while time.time() - СТАРТ < ЛИМИТ_СЕК:
    круг += 1
    ждут, всего, готово = nashi_neyasnye()
    print(f"[круг {круг}] партия {всего} | неясных {готово} | "
          f"переспросить работником {len(ждут)}")
    if not ждут:
        print("переспрашивать нечего")
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

ждут, всего, готово = nashi_neyasnye()
print(f"\nитог: партия {всего} | с вердиктом {готово} | ждут {len(ждут)}")
with store._lock:
    ряд = store._conn.execute(
        "SELECT verdict, COUNT(*) FROM addr_probe GROUP BY verdict").fetchall()
print("вердикты в базе:", dict(ряд))
