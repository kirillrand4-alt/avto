# -*- coding: utf-8 -*-
"""Разбор сырых ответов пересказа напоминаний: сколько с JSON, без JSON, длина."""
import io
import re
т = io.open(r"C:\sender\_ops\napominaniya-syroy.txt", encoding="utf-8").read()
куски = [к for к in re.split(r"\n\n======== \d\d:\d\d:\d\d\n", т) if к.strip()]
с_json = [к for к in куски if '{"pisma"' in к]
без = [к for к in куски if '{"pisma"' not in к]
print("ответов:", len(куски), "с JSON:", len(с_json), "без JSON:", len(без))
print("средняя длина без JSON:", sum(len(к) for к in без) // max(1, len(без)), "с JSON:", sum(len(к) for к in с_json) // max(1, len(с_json)))
for к in без[:2]:
    print("--- начало:", к[:300].replace("\n", " "))
    print("--- конец:", к[-300:].replace("\n", " "))
