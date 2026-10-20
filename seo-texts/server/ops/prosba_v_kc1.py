# -*- coding: utf-8 -*-
"""Доля писем с просьбой переслать/дать контакт коллеги: годные письма КЦ-1
(журнал gen-kc1-avgust) и для сравнения август (avgust-kc-pisma.json), с примерами."""
import io
import json
import re
from collections import Counter
РЕ = re.compile(r"(?i)перешл|переслат|передайте|перенаправ|контакт коллеги|не к вам|кто у вас|кому у вас")
def доля(тексты, имя):
    с = [т for т in тексты if РЕ.search(т or "")]
    print("%s: писем %d, с просьбой %d (%.0f%%)" % (имя, len(тексты), len(с), 100 * len(с) / max(1, len(тексты))))
    обор = Counter()
    for т in с:
        for ф in re.split(r"(?<=[.!?])\s+", т):
            if РЕ.search(ф):
                обор[ф.strip()[:120]] += 1
    for ф, n in обор.most_common(6):
        print("   %3d  %s" % (n, ф))
кц1 = [json.loads(s) for s in io.open(r"C:\sender\_ops\gen-kc1-avgust.jsonl", encoding="utf-8")]
доля([z.get("тело") for z in кц1 if z.get("этап") == "итог" and z.get("ок")], "КЦ-1 август")
авг = json.load(io.open(r"C:\sender\_ops\avgust-kc-pisma.json", encoding="utf-8"))
доля([(x.get("telo") or "").split("\n\nС уважением")[0] for x in авг if x["kamp"] == "Партия 935 — КЦ"], "Август, Партия 935 — КЦ")
доля([(x.get("telo") or "").split("\n\nС уважением")[0] for x in авг if x["kamp"] == "Партия 935 — КЦ" and x["otvetili"]], "  из них ответившие")
