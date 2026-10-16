import glob, io, json, os
for ф in sorted(glob.glob(r"C:\sender\_ops\gen-*.jsonl"), key=os.path.getmtime)[-5:]:
    n = cw = cr = вх = 0
    for s in io.open(ф, encoding="utf-8", errors="replace"):
        if '"итог"' not in s: continue
        z = json.loads(s); n += 1
        cw += z.get("вход_кэш_запись", 0) or 0; cr += z.get("вход_кэш_чтение", 0) or 0
    print(os.path.basename(ф), "писем", n, "кэш-запись", cw, "кэш-чтение", cr)
