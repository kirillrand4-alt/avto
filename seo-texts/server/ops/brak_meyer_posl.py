# -*- coding: utf-8 -*-
"""Причины брака последних N итогов журнала Meyer «Россия 9000» + отсев предкласса. Только чтение.
    brak_meyer_posl.py [N=954]"""
import io, json, re, sys
from collections import Counter
N = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 954
ит, отсев = [], []
for s in io.open(next((a.split("=",1)[1] for a in sys.argv if a.startswith("zhurnal=")), r"C:\sender\_ops\gen-rossiya-9000.jsonl"), encoding="utf-8", errors="replace"):
    if '"итог"' in s or "предкласс_отсев" in s:
        try: z = json.loads(s)
        except ValueError: continue
        (ит if z.get("этап") == "итог" else отсев).append(z)
ит = ит[-N:]
плохие = [z for z in ит if not z.get("ок")]
print("итогов %d, годных %d, брак %d; отсев предкласса (последние 500 записей): %d" % (len(ит), len(ит) - len(плохие), len(плохие), len(отсев[-500:])))
def кат(т):
    т0 = т.lower()
    for k, p in [("отказ/сбой модели", r"i can|нет json|json не разобран|упал|http 5"),
                 ("не покупатель → переставить на КЦ", r"переставить на kc"),
                 ("не покупатель", r"не покупатель"),
                 ("рентген/сорт не про этот продукт", r"рентген не видит|не видит|плотност|небезопасн"),
                 ("редактор: слово/оборот", r"редактор|не наше слово"),
                 ("канцелярит/штамп", r"канцеляр|штамп|шаблон"),
                 ("линза/технолог", r"линз|технолог|скептик"),
                 ("числа/факты", r"числ|факт|payload|выдум"),
                 ("тема", r"тема"),
                 ("не встало в очередь", r"очеред|message_id")]:
        if re.search(p, т0): return k
    return "прочее"
сч, прим = Counter(), {}
for z in плохие:
    т = "; ".join(map(str, z.get("брак") or []))
    k = кат(т); сч[k] += 1; прим.setdefault(k, []).append(т[:170])
for k, v in сч.most_common():
    print("\n%4d  %s" % (v, k))
    for p in прим[k][:4]: print("      - " + p)
# что внутри «прочее» и «редактор» — частые первые слова

if "--spisok" in sys.argv:
    рид = sorted({z["recipient_id"] for z in плохие if z.get("recipient_id")})
    json.dump(рид, io.open(r"C:\sender\_ops\spisok-meyer-brak-1610.json", "w"))
    print("список повтора:", len(рид))

if "--spiski-dobor" in sys.argv:
    кц, мей = set(), set()
    for z in плохие:
        т = "; ".join(map(str, z.get("брак") or [])).lower()
        r = z.get("recipient_id")
        if not r: continue
        if "переставить на kc" in т: кц.add(r)
        elif "не покупатель" in т: continue
        else: мей.add(r)
    json.dump(sorted(кц), io.open(r"C:\sender\_ops\spisok-kc-iz-meyer-brak.json", "w"))
    json.dump(sorted(мей), io.open(r"C:\sender\_ops\spisok-meyer-brak-2.json", "w"))
    print("списки: КЦ", len(кц), "Meyer повтор", len(мей))
