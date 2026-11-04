# -*- coding: utf-8 -*-
"""Автоотправка: кампания без свободных ящиков не загораживает остальные (владелец
04.11: «делай»). Было: проход берёт письма по сроку, самые старые первыми; ~3000
писем Meyer, которым сегодня нет ящика (лимит дня съеден), стоят в голове очереди,
40 порций по 10 уходят на них и до 280 писем КЦ при свободных 28 ящиках проход не
доходит. Стало: если у кампании в этом проходе 20 писем подряд не нашли ящика,
все её scheduled-письма откладываются в сторону (skip_ids) до следующего прохода.
Правка по якорям в auto_send.py: бэкап .bak-sytye-<время>, py_compile, откат.
    avtootpravka_sytye_kampanii.py [--primenit | --otkat] [--koren=<папка>]"""
import glob, io, os, py_compile, shutil, sys, time
КОРЕНЬ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--koren=")), r"C:\sender\sender")
П = os.path.join(КОРЕНЬ, "auto_send.py")
МЕТКА = "СЫТЫЕ-04.11"
ПРАВКИ = [
("""        набрано: set = set()
""", """        набрано: set = set()
        # СЫТЫЕ-04.11 (владелец 04.11 «делай»): направление, которому в проходе
        # 20 раз не нашлось ящика и ни одно письмо не ушло, выходит из выборки
        # (skip_campaigns) — иначе ~3000 писем Meyer без свободного ящика
        # съедают все 40 порций, и письма КЦ при свободных ящиках КЦ стоят.
        нет_ящика: dict = {}
"""),
("""                было = out["sent"]
                try:
                    self._send_one(m, win, now, out)
""", """                было = out["sent"]
                было_возвр = out["released"]
                try:
                    self._send_one(m, win, now, out)
                    if out["sent"] == было and out["released"] > было_возвр:
                        нет_ящика[нап] = нет_ящика.get(нап, 0) + 1
                        if нет_ящика[нап] >= 20 and not по_напр.get(нап):
                            набрано |= {к for к, н in напр_камп.items() if н == нап}
                            logger.info("auto_send: направлению %s ящиков нет — "
                                        "вне прохода", нап)
"""),
]
if "--otkat" in sys.argv:
    б = sorted(glob.glob(П + ".bak-sytye-*"))
    if б:
        shutil.copy2(б[-1], П)
    print("=== СЫТЫЕ: ОТКАТ (нужен рестарт) ===")
    sys.exit(0)
т = io.open(П, encoding="utf-8").read()
if МЕТКА in т:
    print("=== СЫТЫЕ: УЖЕ БЫЛО ===")
    sys.exit(0)
for было, _ in ПРАВКИ:
    if т.count(было) != 1:
        print("якорь найден %d раз:\n%s" % (т.count(было), было[:200]))
        print("=== СЫТЫЕ: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
if "suppress" not in т.split("class ")[0]:
    print("нет suppress в импортах"); print("=== СЫТЫЕ: НЕ ПРИМЕНЕНО ==="); sys.exit(0)
for было, стало in ПРАВКИ:
    т = т.replace(было, стало)
if "--primenit" not in sys.argv:
    print("якоря на месте, сухой прогон. Применить — --primenit")
    sys.exit(0)
бэкап = П + ".bak-sytye-%d" % int(time.time())
shutil.copy2(П, бэкап)
io.open(П, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(П, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, П)
    print("сбой, откат:", е)
    sys.exit(0)
print("бэкап:", бэкап)
print("=== СЫТЫЕ: ПРИМЕНЕНО (нужен рестарт) ===")
