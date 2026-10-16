# -*- coding: utf-8 -*-
"""КЦ 16.10: крупным (выручка от 1 млрд или размер «крупный») — явная подсказка в
блоке получателя: центробежные и «под ключ в том числе для крупных объектов».
Модель по одному правилу их пропускала (ВЕКА РУС, 3+ млрд). Бэкап .bak-kc1610e-*."""
import io, py_compile, shutil, sys, time
П = r"C:\sender\sender\ai_letter.py"
т = io.open(П, encoding="utf-8").read()
if "КРУПНОЕ ПРЕДПРИЯТИЕ (канон КЦ 16.10)" in т:
    print("=== КЦ 1610e: УЖЕ БЫЛО ==="); sys.exit()
С = """    if size in SIZE_TONE:
        lines.append(f"РАЗМЕР: {SIZE_TONE[size]}")
"""
Н = С + """    try:
        _выр = float(str(ex.get('revenue') or 0).replace(' ', '').replace(',', '.'))
    except (TypeError, ValueError):
        _выр = 0.0
    if division == 'kc' and (size == 'крупный' or _выр >= 1e9):
        lines.append("КРУПНОЕ ПРЕДПРИЯТИЕ (канон КЦ 16.10): во втором абзаце "
                     "ОБЯЗАТЕЛЬНО - проекты под ключ в том числе для крупных "
                     "промышленных объектов и центробежные компрессоры от 132 кВт "
                     "до 14,5 МВт.")
"""
if т.count(С) != 1:
    print("якорь:", т.count(С)); print("=== КЦ 1610e: НЕ ПРИМЕНЕНО ==="); sys.exit()
б = П + ".bak-kc1610e-%d" % int(time.time()); shutil.copy2(П, б)
io.open(П, "w", encoding="utf-8").write(т.replace(С, Н))
try:
    py_compile.compile(П, doraise=True)
except Exception as е:
    shutil.copy2(б, П); print("откат:", е); sys.exit()
print("бэкап:", б); print("=== КЦ 1610e: ПРИМЕНЕНО ===")
