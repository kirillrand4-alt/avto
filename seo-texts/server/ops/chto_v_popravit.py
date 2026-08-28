# -*- coding: utf-8 -*-
"""Что именно в «поправить»: критично или косметика."""
import io
import json
import re
from collections import Counter

всё = {}
for ф, п in ((r"C:\sender\_ops\sud-vtoryh.jsonl", 1),
             (r"C:\sender\_ops\sud-vtoryh-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            d["_partiya"] = п
            всё[(п, int(d["id"]))] = d
    except FileNotFoundError:
        pass
поправ = {k: d for k, d in всё.items()
          if str(d.get("verdikt") or "").replace("o", "о").replace("p", "р") == "поправить"}
print("«поправить» всего: %d (партия 1: %d, партия 2: %d)"
      % (len(поправ), sum(1 for k in поправ if k[0] == 1),
         sum(1 for k in поправ if k[0] == 2)))

# Разряды по тяжести. Критично — то, что адресат заметит как ложь о себе.
КРИТ = re.compile(
    r"(?i)(выдум|придума|не подтвержд|нет в карточке|нет данных|"
    r"перепута|не производ|не занимается|которых нет|которой нет|"
    r"ошибочн|неверн[оыа]|не соответству|приписан)")
СРЕДН = re.compile(r"(?i)(реклам|обеща|навязчив|обращени|не тому|"
                   r"чужому|роль|адресат)")
КОСМ = re.compile(r"(?i)(склонени|падеж|формулиров|коряв|стилист|"
                  r"опечат|запят|громоздк|длинн|повтор слов)")
разряд = Counter()
примеры = {"критично": [], "среднее": [], "косметика": [], "неясно": []}
for (п, i), d in поправ.items():
    т = str(d.get("chto_ne_tak") or "")
    выд = str(d.get("vydumka") or "").strip()
    факты = d.get("fakty_verny") is False
    if выд or факты or КРИТ.search(т):
        р = "критично"
    elif d.get("obrashchenie_ok") is False or d.get("reklama") is True or СРЕДН.search(т):
        р = "среднее"
    elif d.get("yazyk_ok") is False or КОСМ.search(т):
        р = "косметика"
    else:
        р = "неясно"
    разряд[р] += 1
    if len(примеры[р]) < 5:
        примеры[р].append((п, i, т[:104]))
print("")
for к, n in разряд.most_common():
    print("   %-12s %4d  (%.0f%%)" % (к, n, 100.0 * n / len(поправ)))
for р in ("критично", "среднее", "косметика", "неясно"):
    if примеры[р]:
        print("")
        print("=== %s ===" % р)
        for п, i, т in примеры[р]:
            print("   п%d rev %-6s %s" % (п, i, т))
