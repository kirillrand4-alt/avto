# -*- coding: utf-8 -*-
"""Уникальность партии «провалы Meyer» по журналу meyer-partiya.jsonl (шаг 3, владелец 16.11).
По каждому шаблону: сходство пар писем по 4-словным шинглам (Жаккар), без приветствия; сколько пар > 50%,
у каждого письма — максимум сходства с другими; доля предложений, повторяющихся в ≥10 письмах; темы.
Письма, у которых есть пара > ПОРОГ, пишет в _ops/meyer-partiya-dubli.jsonl (их пересобрать/снять).
    meyer_provaly_unikalnost.py [--porog=0.5] [--pokazat=N]   Только чтение журнала."""
import io, json, re, sys
from collections import Counter, defaultdict
ПОРОГ = float(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--porog=")), "0.5"))
ПОК = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--pokazat=")), "0"))
зз = [json.loads(с) for с in io.open(r"C:\sender\_ops\meyer-partiya.jsonl", encoding="utf-8")]
зз = [з for з in зз if з.get("status") == "ок"]
по = defaultdict(list)
for з in зз: по[з["shablon"]].append(з)


def шинглы(т):
    т = т.split("\n\n", 1)[1] if "\n\n" in т else т                       # без приветствия
    сл = re.findall(r"[а-яёa-z0-9]+", т.lower())
    return {" ".join(сл[i:i + 4]) for i in range(len(сл) - 3)}


пред = lambda т: [x.strip() for x in re.split(r"(?<=[.!?])\s+", т) if x.strip()]
дубли = set(); итог = {}
for ш, пис in по.items():
    сш = [шинглы(з["pismo"]) for з in пис]
    макс = [0.0] * len(пис); пар = 0; примеры = []
    for i in range(len(пис)):
        a = сш[i]
        for j in range(i + 1, len(пис)):
            b = сш[j]; п = len(a & b) / max(1, len(a | b))
            if п > макс[i]: макс[i] = п
            if п > макс[j]: макс[j] = п
            if п > ПОРОГ:
                пар += 1; дубли.add(пис[j]["kluch"])
                if len(примеры) < 3: примеры.append((round(п, 2), пис[i]["kluch"], пис[j]["kluch"]))
    сч = Counter(p for з in пис for p in set(пред(з["pismo"])))
    доли = []
    for з in пис:
        пп = пред(з["pismo"]); всего = sum(len(x) for x in пп)
        доли.append(sum(len(x) for x in пп if сч[x] >= 10) / max(1, всего))
    доли.sort(); мс = sorted(макс)
    print("== %s: писем %d, тем %d" % (ш, len(пис), len({з["tema"] for з in пис})))
    if пис:
        print("   макс. сходство с ближайшим письмом: медиана %.0f%%, 90%% писем ниже %.0f%%, максимум %.0f%%"
              % (100 * мс[len(мс) // 2], 100 * мс[int(len(мс) * 0.9)], 100 * мс[-1]))
        print("   пар сходством > %.0f%%: %d; писем-дублей (второе в паре): %d" % (100 * ПОРОГ, пар, len({p[2] for p in примеры}) if False else sum(1 for з in пис if з["kluch"] in дубли)))
        print("   доля текста из фраз, повторяющихся в ≥10 письмах: медиана %.0f%%, макс %.0f%%" % (100 * доли[len(доли) // 2], 100 * доли[-1]))
        print("   самые частые фразы:", [(p[:50], n) for p, n in сч.most_common(3)])
        if примеры: print("   примеры пар:", примеры)
with io.open(r"C:\sender\_ops\meyer-partiya-dubli.jsonl", "w", encoding="utf-8") as ф:
    for к in sorted(дубли): ф.write(json.dumps({"kluch": к}, ensure_ascii=False) + "\n")
ст = Counter(json.loads(с).get("status") for с in io.open(r"C:\sender\_ops\meyer-partiya.jsonl", encoding="utf-8"))
print("статусы журнала:", dict(ст), "| дублей к пересборке:", len(дубли))
if ПОК:
    for з in зз[:ПОК]:
        print("\n=== %s | %s | перефраз %s\nТема: %s\n\n%s" % (з["shablon"], з["kompaniya"], з["perefraz"], з["tema"], з["pismo"]))
