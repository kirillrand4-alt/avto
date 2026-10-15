# -*- coding: utf-8 -*-
"""Сколько денег уходит на брак, и отдельно — на отказы модели писать письмо. По журналам gen-*.jsonl. Только чтение."""
import glob, io, json, os
from collections import Counter, defaultdict
def вид(т):
    т = т.lower()
    if "i can" in т or "i won" in т or "нет json" in т or "упал" in т: return "отказ/сбой модели"
    if "не покупатель" in т: return "не покупатель"
    if "линз" in т or "технолог" in т or "скептик" in т: return "линза"
    if "очеред" in т or "message_id" in т: return "не встало в очередь"
    return "гейт текста"
for ф in sorted(glob.glob(r"C:\sender\_ops\gen-*.jsonl"), key=os.path.getmtime)[-8:]:
    n, д, ок, отк_пр = Counter(), defaultdict(float), [0, 0.0], Counter()
    for s in io.open(ф, encoding="utf-8", errors="replace"):
        if '"итог"' not in s: continue
        try: z = json.loads(s)
        except ValueError: continue
        ц = float(z.get("цена_$") or 0)
        if z.get("ок"): ок[0] += 1; ок[1] += ц; continue
        т = "; ".join(map(str, z.get("брак") or []))
        к = вид(т); n[к] += 1; д[к] += ц
        if к == "отказ/сбой модели": отк_пр[т[:70]] += 1
    всего = ок[1] + sum(д.values())
    if not всего: continue
    print("== %s: годных %d за $%.0f, всего $%.0f" % (os.path.basename(ф), ок[0], ок[1], всего))
    for к in n: print("   %-22s %4d писем  $%6.1f  (%.0f%% денег)" % (к, n[к], д[к], 100 * д[к] / всего))
    for k, v in отк_пр.most_common(3): print("      %3d  %s" % (v, k))
