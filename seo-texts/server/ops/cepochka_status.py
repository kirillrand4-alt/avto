import glob, io
for p in sorted(glob.glob(r"C:\sender\_ops\spisok-meyer-9000-*.json")): print(p, len(__import__("json").load(io.open(p))))
try: print(io.open(r"C:\sender\_ops\cepochka-meyer.log", encoding="utf-8").read()[-1500:])
except Exception as e: print(e)
