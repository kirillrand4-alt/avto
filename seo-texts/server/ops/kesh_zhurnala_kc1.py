# -*- coding: utf-8 -*-
"""Последние строки журнала КЦ-1 август: модель, вызовы, кэш запись/чтение, цена."""
import io
import json
z = [json.loads(s) for s in io.open(r"C:\sender\_ops\gen-kc1-avgust.jsonl", encoding="utf-8") if '"итог"' in s]
for x in z[-12:]:
    print(x.get("модель"), "вызовов", x.get("вызовов"), "+пров", x.get("вызовов_проверок"),
          "кэш зап", x.get("вход_кэш_запись"), "чт", x.get("вход_кэш_чтение"), "$", x.get("цена_$"), x.get("ок"))
