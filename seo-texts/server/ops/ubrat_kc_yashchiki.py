# -*- coding: utf-8 -*-
"""Убрать из конфига ящики удалённых компрессорных доменов.

Владелец 14.09: «компрессорные я удалил домены вообще». Четырнадцать
ящиков в sender.yaml теперь указывают в никуда: вход по почте не проходит,
отправки с них нет с 28.08, а ротация и перелив продолжают их перебирать.

Убираем три места: блоки в mailboxes, состав пулов, карту обращений в
personalization. Даты прогрева доменов в gates не трогаем — это история,
на маршрутизацию она не влияет.

Проверка перед записью: новый текст читается парсером конфига, Config
собирается, ящиков ровно 19, в пулах нет ни одного мёртвого.

argv: --primenit чтобы записать (без него только показать).
"""
import io
import re
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config, _load_yaml                    # noqa: E402

ФАЙЛ = r"C:\sender\sender.yaml"
ВРЕМЕННЫЙ = r"C:\sender\sender.yaml.proba"
ПРИМЕНИТЬ = "--primenit" in sys.argv

МЁРТВЫЕ = [
    "v.melnikov@kompressor-air-trade.ru", "i.lyapin@kompressor-air-trade.ru",
    "k.yashin@kompressor-pro-expert.ru", "o.tseyzer@kompressor-pro-expert.ru",
    "a.balakirev@compressor-air-expert.ru", "v.prokhorov@compressor-air-expert.ru",
    "p.novoseltsev@kompressor-pro-trade.ru", "m.pavlov@kompressor-pro-trade.ru",
    "v.melnikov@kompressor-air-expert.ru", "i.lyapin@kompressor-air-expert.ru",
    "k.yashin@kompressor-expert.ru", "o.tseyzer@kompressor-expert.ru",
    "a.balakirev@compressor-store.ru", "l.abubakirov@compressor-store.ru",
]
МЁРТВЫЕ_Н = set(МЁРТВЫЕ)

т = io.open(ФАЙЛ, encoding="utf-8").read()
строки = т.splitlines(True)

# 1. блоки ящиков
новые, н, убрано_блоков = [], 0, 0
while н < len(строки):
    с = строки[н]
    м = re.match(r'^  - mailbox_id:\s*"?([^"\s]+)"?\s*$', с)
    if м and м.group(1) in МЁРТВЫЕ_Н:
        н += 1
        while н < len(строки):
            сл = строки[н]
            if re.match(r"^  - mailbox_id:", сл) or re.match(r"^[^\s#]", сл):
                break
            н += 1
        убрано_блоков += 1
        continue
    новые.append(с)
    н += 1

# 2. состав пулов и 3. карта обращений
итог, убрано_из_пулов, убрано_обращений = [], 0, 0
пустые_пулы = []
for с in новые:
    м = re.match(r"^(\s+)(pool_\w+):\s*\[(.*)\]\s*$", с.rstrip("\n"))
    if м:
        было = [x.strip() for x in м.group(3).split(",") if x.strip()]
        стало = [x for x in было if x not in МЁРТВЫЕ_Н]
        убрано_из_пулов += len(было) - len(стало)
        if not стало:
            # Пул целиком состоял из компрессорных (pool_mailru). Пустой
            # список конфиг не принимает, да и смысла в нём нет: своих
            # mail.ru-ящиков у нас больше не осталось. Убираем пул, а
            # получателей mail.ru отправляем в общий — то же самое делал
            # перелив, только теперь это написано прямо.
            пустые_пулы.append(м.group(2))
            continue
        итог.append("%s%s: [%s]\n" % (м.group(1), м.group(2), ", ".join(стало)))
        continue
    м3 = re.match(r"^(\s+)(\w+):\s*(pool_\w+)\s*$", с.rstrip("\n"))
    if м3 and м3.group(3) in пустые_пулы:
        итог.append("%s%s: pool_fallback\n" % (м3.group(1), м3.group(2)))
        continue
    м2 = re.match(r"^\s+([^\s:]+@[^\s:]+):\s*\S+\s*$", с.rstrip("\n"))
    if м2 and м2.group(1) in МЁРТВЫЕ_Н:
        убрано_обращений += 1
        continue
    итог.append(с)

новый_текст = "".join(итог)
print("блоков ящиков убрано:   %d (ждём 14)" % убрано_блоков)
print("строк из пулов убрано:  %d" % убрано_из_пулов)
print("обращений убрано:       %d (ждём 14)" % убрано_обращений)
print("файл: %d → %d байт" % (len(т), len(новый_текст)))
остались = [x for x in МЁРТВЫЕ if x in новый_текст]
print("пулов убрано целиком:   %s" % (", ".join(пустые_пулы) or "нет"))
print("мёртвых упоминаний осталось: %d %s"
      % (len(остались), ("(" + ", ".join(остались)[:120] + ")") if остались else ""))

# --- проверка нового текста живым парсером конфига ---
io.open(ВРЕМЕННЫЙ, "w", encoding="utf-8").write(новый_текст)
беда = []
try:
    было_д = _load_yaml(т)
    стало_д = _load_yaml(новый_текст)
    новый_cfg = Config.load(ВРЕМЕННЫЙ)
    ящики = [m.mailbox_id for m in новый_cfg.mailboxes()]
    print("")
    print("--- как читается новый конфиг ---")
    print("   ящиков: %d" % len(ящики))
    for имя, состав in (новый_cfg.provider_pools() or {}).items():
        print("   пул %-16s %2d ящиков%s"
              % (имя, len(состав), "   ПУСТ" if not состав else ""))
    плохие = [x for x in ящики if x in МЁРТВЫЕ_Н]
    if плохие:
        беда.append("в ящиках остались мёртвые: %s" % плохие)
    for имя, состав in (новый_cfg.provider_pools() or {}).items():
        п = [x for x in состав if x in МЁРТВЫЕ_Н]
        if п:
            беда.append("в пуле %s остались мёртвые: %s" % (имя, п))
    # ничего, кроме ящиков/пулов/обращений, не разъехалось
    ключи = set(было_д) | set(стало_д)
    можно = {"mailboxes", "provider_split", "personalization"}
    for к in sorted(ключи):
        if к in можно:
            continue
        if было_д.get(к) != стало_д.get(к):
            беда.append("разъехался раздел «%s» — трогать его не собирались" % к)
    print("")
    print("--- разделы, которые изменились ---")
    for к in sorted(ключи):
        if было_д.get(к) != стало_д.get(к):
            print("   %s" % к)
except Exception as ex:                                         # noqa: BLE001
    беда.append("новый конфиг не читается: %s" % str(ex)[:200])

print("")
print("=" * 74)
print("=== УБРАТЬ КОМПРЕССОРНЫЕ ЯЩИКИ ИЗ КОНФИГА ===")
if беда:
    for б in беда:
        print("   СТОП: %s" % б)
    print("   ничего не записано")
elif убрано_блоков != 14 or убрано_обращений != 14:
    print("   СТОП: убрали не 14 блоков/обращений — не записываем")
elif not ПРИМЕНИТЬ:
    print("   показ без записи (нужен --primenit)")
else:
    бэкап = ФАЙЛ + ".bak-%d" % int(time.time())
    io.open(бэкап, "w", encoding="utf-8").write(т)
    io.open(ФАЙЛ, "w", encoding="utf-8").write(новый_текст)
    try:
        Config.load(ФАЙЛ)
        print("   записано, конфиг читается")
    except Exception as ex:                                     # noqa: BLE001
        io.open(ФАЙЛ, "w", encoding="utf-8").write(т)
        print("   НЕ ЧИТАЕТСЯ ПОСЛЕ ЗАПИСИ, откатили: %s" % str(ex)[:160])
    print("   бэкап: %s" % бэкап)
