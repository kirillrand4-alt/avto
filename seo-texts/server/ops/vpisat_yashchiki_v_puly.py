# -*- coding: utf-8 -*-
"""Вписать мейеровские ящики в пулы провайдеров (правка sender.yaml).

Четыре ящика направления meyer заведены в конфиге и показаны панелью как
«готов к бою», но не входят НИ В ОДИН пул. Подбор ящика берёт кандидатов
только из пула получателя — поэтому эти четыре не рассматриваются никогда,
и вся мейеровская отправка едет на трёх адресах.

Правим точечно: в списки pool_yandex и pool_fallback дописываем недостающие
ящики того же провайдера. Ничего не удаляем, порядок существующих не трогаем.
Перед правкой — .bak, после — проверка, что YAML читается и пулы выросли
ровно на ожидаемое.
"""
import io
import os
import shutil
import sys

sys.path.insert(0, r"C:\sender")
# pyyaml на сервере нет — у проекта свой мини-парсер, тот же, каким читает
# конфиг сама панель. Проверять правку надо ИМЕННО им: пройдёт у pyyaml, но
# не пройдёт у панели — конфиг сломан.
from sender.config import Config, _load_yaml                           # noqa: E402

ФАЙЛ = r"C:\sender\sender.yaml"
ЦЕЛЕВЫЕ_ПУЛЫ = ("pool_yandex", "pool_fallback")
СУХО = not ({"--катить", "--katit"} & set(sys.argv))

сырой = io.open(ФАЙЛ, encoding="utf-8").read()
конф = _load_yaml(сырой)

пулы = ((конф.get("provider_split") or {}).get("pools")
        or конф.get("provider_pools") or {})
if not пулы:
    print("ОТМЕНА: в конфиге не нашёл пулы"); raise SystemExit(2)
print("пулы найдены:", {k: len(v) for k, v in пулы.items()})

ящики = конф.get("mailboxes") or []
все_в_пулах = {m for сп in пулы.values() for m in сп}
сироты = []
for mb in ящики:
    mid = mb.get("mailbox_id") or mb.get("id")
    if not mid or mid in все_в_пулах:
        continue
    сироты.append((mid, str(mb.get("provider") or ""),
                   str(mb.get("division") or "")))

print("\nящики вне пулов:")
for mid, prov, div in сироты:
    print(f"  {mid:<38} провайдер={prov:<8} направление={div}")
if not сироты:
    print("  нет — вписывать нечего"); raise SystemExit(0)

# дописываем только yandex-ящики в yandex-пулы: провайдер ящика обязан
# совпадать с провайдером пула, иначе получатель уедет не тем маршрутом
план = []
for пул in ЦЕЛЕВЫЕ_ПУЛЫ:
    if пул not in пулы:
        print(f"ОТМЕНА: пула {пул} нет в конфиге"); raise SystemExit(2)
    for mid, prov, div in сироты:
        if prov != "yandex":
            continue
        if mid not in пулы[пул]:
            план.append((пул, mid))

print("\nчто допишем:")
for пул, mid in план:
    print(f"  {пул} += {mid}")
if not план:
    print("  ничего"); raise SystemExit(0)

# правка ТЕКСТА, а не перезапись через дамп: дамп потеряет комментарии и
# порядок ключей, а это боевой конфиг, который читают люди. Пулы записаны
# однострочными списками — «pool_yandex: [a, b, c]», — поэтому дописываем
# перед закрывающей скобкой нужной строки.
новый = сырой
for пул in ЦЕЛЕВЫЕ_ПУЛЫ:
    добавить = [mid for п, mid in план if п == пул]
    if not добавить:
        continue
    строки = новый.split("\n")
    номер = None
    for i, л in enumerate(строки):
        if л.strip().startswith(пул + ":"):
            номер = i
            break
    if номер is None:
        print(f"ОТМЕНА: строку пула {пул} не нашёл"); raise SystemExit(2)
    л = строки[номер]
    if "[" not in л or not л.rstrip().endswith("]"):
        print(f"ОТМЕНА: {пул} записан не однострочным списком — правь руками")
        raise SystemExit(2)
    хвост = л.rstrip()
    строки[номер] = хвост[:-1].rstrip() + ", " + ", ".join(добавить) + "]"
    новый = "\n".join(строки)

проверка = _load_yaml(новый)
нов_пулы = ((проверка.get("provider_split") or {}).get("pools")
            or проверка.get("provider_pools") or {})
print("\nстало:", {k: len(v) for k, v in нов_пулы.items()})
for пул, mid in план:
    if mid not in нов_пулы.get(пул, []):
        print(f"ОТМЕНА: {mid} не оказался в {пул} после правки")
        raise SystemExit(2)
# ничего не пропало
for k, v in пулы.items():
    пропало = set(v) - set(нов_пулы.get(k, []))
    if пропало:
        print(f"ОТМЕНА: из {k} пропали {пропало}"); raise SystemExit(2)
print("проверка пройдена: YAML читается, ничего не пропало")

if СУХО:
    print("\nсухой прогон: файл не тронут. Катить — аргумент --katit")
    raise SystemExit(0)

shutil.copy2(ФАЙЛ, ФАЙЛ + ".bak-puly")
io.open(ФАЙЛ, "w", encoding="utf-8", newline="").write(новый)
print(f"\nВПИСАНО. Резервная копия: {ФАЙЛ}.bak-puly")
print("Панель подхватит после Restart-Service SenderPanel -Force")
