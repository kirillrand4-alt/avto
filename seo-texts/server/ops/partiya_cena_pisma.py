# -*- coding: utf-8 -*-
"""Куда уходят деньги и время одного письма.

Владелец 17.08 видит по 2-3 доллара за письмо и 9-13 минут на штуку. Здесь
разбираем ровно это: сколько вызовов провайдера ушло на письмо, сколько из
них сорвалось в рассуждение (срыв = выжженный потолок без текста) и как
цена делится между удачными и бракованными.

Ничего не меняет.
"""
import io
import json
import os
import sys
from collections import Counter

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
строки = [json.loads(s) for s in io.open(Ж, encoding="utf-8") if s.strip()]
новые = [z for z in строки if z.get("этап") == "итог"]

print(f"строк журнала {len(строки)} | писем после починки {len(новые)}")
if not новые:
    raise SystemExit(0)

print(f"\n{'компания':<30} {'сек':>5} {'выз':>4} {'срыв':>5} {'цена$':>7}  итог")
for z in новые:
    print(f"{str(z.get('имя'))[:28]:<30} {z.get('сек'):>5} "
          f"{z.get('вызовов'):>4} {z.get('срывов'):>5} "
          f"{z.get('цена_$'):>7}  "
          + ("ОК #%s" % z.get("review_id") if z.get("ок")
             else str((z.get("брак") or [""])[0])[:52]))

ок = [z for z in новые if z.get("ок")]
брак = [z for z in новые if not z.get("ок")]
цена = sum(z.get("цена_$") or 0 for z in новые)
print(f"\nвсего ${цена:.2f} за {len(новые)} писем "
      f"| ок {len(ок)} | брак {len(брак)}")
if ок:
    print(f"  среднее по ОК:   ${sum(z['цена_$'] for z in ок)/len(ок):.2f} "
          f"| {sum(z['сек'] for z in ок)//len(ок)}с "
          f"| вызовов {sum(z['вызовов'] for z in ок)/len(ок):.1f} "
          f"| срывов {sum(z['срывов'] for z in ок)/len(ок):.1f}")
if брак:
    print(f"  среднее по браку: ${sum(z['цена_$'] for z in брак)/len(брак):.2f} "
          f"| {sum(z['сек'] for z in брак)//len(брак)}с "
          f"| вызовов {sum(z['вызовов'] for z in брак)/len(брак):.1f} "
          f"| срывов {sum(z['срывов'] for z in брак)/len(брак):.1f}")
print("\nсрывов всего:", sum(z.get("срывов") or 0 for z in новые),
      "на вызовов:", sum(z.get("вызовов") or 0 for z in новые))

# Журнал срывов пишет review_lenses - если он есть, покажем последние.
СР = r"C:\sender\_ops\sryvy.jsonl"
if os.path.exists(СР):
    ср = [json.loads(s) for s in io.open(СР, encoding="utf-8") if s.strip()]
    print(f"\nотдельный журнал срывов: {len(ср)} строк, последние 5:")
    for z in ср[-5:]:
        print("  " + json.dumps(z, ensure_ascii=False)[:150])
