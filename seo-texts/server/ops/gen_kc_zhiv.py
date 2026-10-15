import io,subprocess
for f in ("gen-kc-test","gen-kc-9000"):
    try: pid=io.open(r"C:\sender\_ops\%s.pid"%f).read().strip()
    except Exception: continue
    out=subprocess.run(["tasklist","/FI","PID eq "+pid],capture_output=True,text=True,errors="replace").stdout
    print(f,pid,"ЖИВ" if pid in out else "нет")
    print(io.open(r"C:\sender\_ops\%s.log"%f,encoding="utf-8",errors="replace").read()[-600:])
