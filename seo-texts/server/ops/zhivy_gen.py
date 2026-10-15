import io,subprocess
for f in ("gen-kc-9000","gen-rossiya-9000"):
    try: pid=io.open(r"C:\sender\_ops\%s.pid"%f).read().strip()
    except Exception as e: print(f,e); continue
    out=subprocess.run(["tasklist","/FI","PID eq "+pid],capture_output=True,text=True,errors="replace").stdout
    t=io.open(r"C:\sender\_ops\%s.log"%f,encoding="utf-8",errors="replace").read()
    print(f,pid,"ЖИВ" if pid in out else "нет"); print(t[t.rfind("==== ЗАПУСК"):][-900:])
