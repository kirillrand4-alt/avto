import io, json, os, sys, time
from collections import Counter
ф = sys.argv[1]
print("журнал изменён:", time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(ф))), "| сейчас", time.strftime("%H:%M:%S"))
сч = Counter(); посл = ""
for s in io.open(ф, encoding="utf-8", errors="replace").readlines()[-3000:]:
    try: z = json.loads(s)
    except ValueError: continue
    сч[z.get("этап")] += 1; посл = z.get("этап")
print("последние 3000 строк по этапам:", dict(сч), "| последняя:", посл)
