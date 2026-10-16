import io, re, sys
т = io.open(sys.argv[1], encoding="utf-8", errors="replace").read()
т = т[т.rfind("==== ЗАПУСК"):]
стр = re.findall(r"\[(\d+)/(\d+)\] (ОК|брак)\s.*?\$(\d+\.\d+)", т)
ок = sum(1 for s in стр if s[2] == "ОК"); д = sum(float(s[3]) for s in стр)
print("попыток", len(стр), "из", стр[-1][1] if стр else "?", "| годных", ок, "| $%.2f" % д, "| $%.2f за годное" % (д / ок if ок else 0))
