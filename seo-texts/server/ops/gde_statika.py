import glob, io, os
for п in [r"C:\sender\config.yaml", r"C:\sender\sender.yaml"] + glob.glob(r"C:\sender\*.ps1") + glob.glob(r"C:\sender\*.bat") + glob.glob(r"C:\sender\*.cmd") + glob.glob(r"C:\sender\run*.py"):
    try: т = io.open(п, encoding="utf-8", errors="replace").read()
    except Exception: continue
    for s in т.splitlines():
        if "static" in s.lower() or "dist" in s.lower(): print(п, ":", s.strip()[:200])
import subprocess
print(subprocess.run(["sc", "qc", "SenderPanel"], capture_output=True, text=True, errors="replace").stdout)
for d in glob.glob(r"C:\**\dist\index.html", recursive=False): print(d)
for d in [r"C:\sender\web\dist", r"C:\sender\sender\web\dist", r"C:\sender\dist"]:
    if os.path.isdir(d): print(d, os.listdir(os.path.join(d, "assets"))[:5] if os.path.isdir(os.path.join(d, "assets")) else os.listdir(d)[:5])
