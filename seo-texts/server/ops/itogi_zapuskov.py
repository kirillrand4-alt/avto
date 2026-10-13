# -*- coding: utf-8 -*-
"""Итоги всех запусков 9000 за сегодня по логу (строки ЗАПУСК / итог / СТОП / ЦЕЛЬ / БЮДЖЕТ)."""
import io
import re
т = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8", errors="replace").read()
for кусок in т.split("==== ЗАПУСК")[-6:]:
    шапка = кусок.splitlines()[0][:70]
    ок = len(re.findall(r"\] ОК ", кусок))
    брак = len(re.findall(r"\] брак ", кусок))
    деньги = sum(float(x) for x in re.findall(r"\d+с \$([\d.]+)", кусок))
    конец = [с.strip()[:110] for с in кусок.splitlines() if re.search(r"итог:|ЦЕЛЬ ДОСТИГНУТА|БЮДЖЕТ ВЫБРАН|ОСТАНОВЛЕН", с)]
    print("ЗАПУСК%s | ОК %d брак %d $%.2f | %s" % (шапка, ок, брак, деньги, " / ".join(конец[-2:]) or "без итога (снят/идёт)"))
print("=== ИТОГИ ЗАПУСКОВ ===")
