# -*- coding: utf-8 -*-
"""Срез журнала партии: отработала ли версия с записью текста ДО очереди.

Вопрос владельца 17.08: «генерация со спасением пойдёт? там учтена дыра,
которую показала вторая сессия?» Ответ на него - не слова, а два числа:
сколько строк несут поле «этап» (его пишет только починенная версия) и
сколько несут «тело» (сам текст письма). Ничего не меняем.
"""
import io
import json
import os
import time
from collections import Counter

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
if not os.path.exists(Ж):
    print("журнала нет вовсе")
    raise SystemExit(0)

строки = [json.loads(s) for s in io.open(Ж, encoding="utf-8") if s.strip()]
этапы = Counter(str(z.get("этап") or "БЕЗ ЭТАПА (старая версия)")
                for z in строки)
с_телом = [z for z in строки if z.get("тело")]
с_ревью = [z for z in строки if z.get("review_id")]
ок = [z for z in строки if z.get("ок")]

print(f"строк {len(строки)} | ок={len(ок)} | с review_id {len(с_ревью)} | "
      f"С ТЕКСТОМ ПИСЬМА {len(с_телом)}")
print("по этапам:")
for k, n in этапы.most_common():
    print(f"  {k:<34} {n}")
print("файл изменён:", time.strftime(
    "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(Ж))),
    "| сейчас:", time.strftime("%Y-%m-%d %H:%M:%S"))

брак = Counter()
for z in строки:
    if z.get("ок"):
        continue
    б = z.get("брак") or []
    брак[str((б[0] if б else "?"))[:70]] += 1
if брак:
    print("\nпочему браковались (топ 8):")
    for k, n in брак.most_common(8):
        print(f"  {n:>4}  {k}")
