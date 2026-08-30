# -*- coding: utf-8 -*-
import io, re
т = io.open(r"C:\sender\_ops\sbor-agro.log", encoding="utf-8",
            errors="ignore").read()
шаги = re.findall(r"\[(\d+)/(\d+)\] код ([\d.]+): (готов[^\n]{0,60}|листаю)", т)
print("шагов в логе: %d" % len(шаги))
for н, всего, код, что in шаги[-14:]:
    print("   [%s/%s] %-10s %s" % (н, всего, код, что))
исч = т.count("ключ исчерпан")
ссл = т.count("SSLError")
ост = re.findall(r"живых ключей осталось: (\d+)", т)
print("\nисчерпанных ключей отмечено: %d; SSL-обрывов: %d" % (исч, ссл))
print("живых ключей в последней записи: %s" % (ост[-1] if ост else "—"))
