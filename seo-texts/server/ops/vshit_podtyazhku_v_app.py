# -*- coding: utf-8 -*-
"""Вшить подтяжку очереди в серверный api/app.py, НЕ перезаписывая файл.

Серверная копия app.py разошлась с моей и не совпадает ни с одним коммитом:
это чья-то живая правка (каталог общий с соседней сессией). Перезаписать её
целиком — стереть чужую работу. Поэтому вносим ровно два своих куска:
импорт podtyanut_pod_okno и вызов подтяжки в POST /sending-window.

Идемпотентно: если куски уже на месте, ничего не делает. Перед правкой
кладёт рядом .bak-копию.
"""
import io
import os
import shutil
import sys

ФАЙЛ = r"C:\sender\sender\api\app.py"
СУХО = not ({"--катить", "--katit"} & set(sys.argv))

s = io.open(ФАЙЛ, encoding="utf-8").read()
исходно = s

СТАРЫЙ_ИМПОРТ = ("    from sender.auto_send import (AutoSendLoop, ENABLED_KEY, "
                 "next_slot,\n"
                 "                                  recipient_tz_name, "
                 "window_from)")
НОВЫЙ_ИМПОРТ = ("    from sender.auto_send import (AutoSendLoop, ENABLED_KEY, "
                "next_slot,\n"
                "                                  podtyanut_pod_okno, "
                "recipient_tz_name,\n"
                "                                  window_from)")

СТАРЫЙ_ВЫЗОВ = '''        deps.store.set_setting("sending_window", win)
        try:
            deps.store.append_audit(action="sending_window.set", actor_user_id=p.user_id,
                                    entity_type="settings", entity_id="sending_window",
                                    detail=win)
        except Exception:  # noqa: BLE001
            pass
        return {"window": win, "source": "override"}'''
НОВЫЙ_ВЫЗОВ = '''        deps.store.set_setting("sending_window", win)
        # ПОДТЯЖКА ОЧЕРЕДИ. Расширить окно мало: письма, которым цикл раньше
        # не нашёл часа, уже отложены на завтра, и назад их не тянет никто.
        # 19.08 так встали 107 одобренных писем — окно продлили с 11:00 до
        # 15:00, а очередь осталась стоять до утра. Двигаем только раньше.
        подтянуто = 0
        with suppress(Exception):
            подтянуто = podtyanut_pod_okno(deps.store, win)
        try:
            deps.store.append_audit(action="sending_window.set", actor_user_id=p.user_id,
                                    entity_type="settings", entity_id="sending_window",
                                    detail=dict(win, подтянуто=подтянуто))
        except Exception:  # noqa: BLE001
            pass
        return {"window": win, "source": "override", "подтянуто": подтянуто}'''

if "podtyanut_pod_okno" in s:
    print("подтяжка уже вшита — ничего не делаю")
    raise SystemExit(0)

for имя, старое, новое in (("импорт", СТАРЫЙ_ИМПОРТ, НОВЫЙ_ИМПОРТ),
                           ("вызов", СТАРЫЙ_ВЫЗОВ, НОВЫЙ_ВЫЗОВ)):
    n = s.count(старое)
    print(f"{имя}: якорь найден {n} раз(а)")
    if n != 1:
        print(f"ОТМЕНА: якорь «{имя}» не единственный — руками, вслепую нельзя")
        raise SystemExit(2)
    s = s.replace(старое, новое, 1)

if "from contextlib import suppress" not in s:
    print("ОТМЕНА: в файле нет suppress — вызов не соберётся")
    raise SystemExit(2)

import ast
try:
    ast.parse(s)
except SyntaxError as ex:
    print("ОТМЕНА: после правки файл не парсится:", ex)
    raise SystemExit(2)
print("после правки файл парсится: да")
print(f"было {len(исходно)} байт, стало {len(s)} байт")

if СУХО:
    print("\nсухой прогон: файл не тронут. Катить — аргумент --катить")
    raise SystemExit(0)

shutil.copy2(ФАЙЛ, ФАЙЛ + ".bak-podtyazhka")
io.open(ФАЙЛ, "w", encoding="utf-8", newline="").write(s)
print(f"ВШИТО. Резервная копия: {ФАЙЛ}.bak-podtyazhka")
print("Панель подхватит после Restart-Service SenderPanel -Force")
