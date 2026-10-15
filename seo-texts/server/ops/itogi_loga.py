import io,sys
t=io.open(sys.argv[1],encoding="utf-8",errors="replace").read()
for s in t.splitlines():
    if s.startswith("==== ЗАПУСК") or s.startswith("итог:") or "к генерации" in s or "заслон сработал" in s or "СТОП" in s: print(s[:200])
