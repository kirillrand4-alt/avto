# -*- coding: utf-8 -*-
"""Сколько потрачено сегодня и на что."""
import glob
import io
import json
import os
import time
from collections import Counter, defaultdict

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
день = time.strftime("%Y-%m-%d")
писем = Counter()
деньги = defaultdict(float)
цены = []
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines()[-4000:]:
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        if z.get("этап") != "итог" or z.get("день") != день:
            continue
        писем["всего"] += 1
        писем["ок" if z.get("ок") else "брак"] += 1
        ц = z.get("цена_$")
        if isinstance(ц, (int, float)):
            деньги["всего"] += float(ц)
            цены.append(float(ц))
        for поле in ("цена_письма_$", "цена_проверок_$"):
            v = z.get(поле)
            if isinstance(v, (int, float)):
                деньги[поле] += float(v)

print("=== ГЕНЕРАЦИЯ ЗА %s ===" % день)
print("   обработано: %d, годных %d, брак %d"
      % (писем["всего"], писем["ок"], писем["брак"]))
print("   потрачено:  $%.2f  (письма $%.2f + проверки $%.2f)"
      % (деньги["всего"], деньги["цена_письма_$"], деньги["цена_проверок_$"]))
if писем["ок"]:
    print("   на годное письмо: $%.3f" % (деньги["всего"] / писем["ок"]))
if цены:
    цены.sort()
    print("   цена попытки: медиана $%.3f, максимум $%.3f"
          % (цены[len(цены) // 2], цены[-1]))

print("\n=== ПО ПРОГОНАМ (итоговые строки логов) ===")
for п in sorted(glob.glob(r"C:\sender\_ops\partiya_gen-0831-*.log"),
                key=os.path.getmtime):
    с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    итог = [x for x in с if x.strip().startswith("итог:")]
    print("   %-34s %s" % (os.path.basename(п),
                           итог[-1].strip()[:90] if итог else "(не завершён)"))

print("\n=== ИТОГ ===")
print("сегодня на генерацию ушло $%.2f за %d годных писем"
      % (деньги["всего"], писем["ок"]))
