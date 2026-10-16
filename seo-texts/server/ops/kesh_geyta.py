# -*- coding: utf-8 -*-
"""Кэш промпта для гейта адресата (владелец 16.10: «кеш не используется»).
default_caller режет промпт по границе «\\nПОЛУЧАТЕЛИ:\\n» (gen_provider._ГРАНИЦЫ),
а гейт клал компании после «Компании:», и схему ответа — в КОНЕЦ, за компании.
Статика уходила в messages и не кэшировалась. Теперь: правила + схема, затем
граница ПОЛУЧАТЕЛИ, затем пачка. Бэкап .bak-keshgeyta-*."""
import io, py_compile, shutil, sys, time
П = r"C:\sender\sender\target_gate.py"
т = io.open(П, encoding="utf-8").read()
if "КЭШ ГЕЙТА (16.10)" in т:
    print("=== КЭШ ГЕЙТА: УЖЕ БЫЛО ==="); sys.exit()
С = """        промпт = ((ПРОДАВЕЦ if линза == "продавец" else СКЕПТИК) +
                  "\\n\\nКомпании:\\n\\n" + "\\n\\n".join(блоки) + СХЕМА)"""
Н = """        # КЭШ ГЕЙТА (16.10): статика (линза + схема ответа) до границы
        # «ПОЛУЧАТЕЛИ:», пачка компаний после — razrezat_promt кладёт статику
        # в system, и шлюз читает её из кэша.
        промпт = ((ПРОДАВЕЦ if линза == "продавец" else СКЕПТИК) + СХЕМА +
                  "\\nПОЛУЧАТЕЛИ:\\n\\n" + "\\n\\n".join(блоки))"""
if т.count(С) != 1:
    print("якорь:", т.count(С)); print("=== КЭШ ГЕЙТА: НЕ ПРИМЕНЕНО ==="); sys.exit()
б = П + ".bak-keshgeyta-%d" % int(time.time()); shutil.copy2(П, б)
io.open(П, "w", encoding="utf-8").write(т.replace(С, Н))
try:
    py_compile.compile(П, doraise=True)
    sys.path.insert(0, r"C:\sender")
    import gen_provider
    from sender import target_gate as tg
    пр = tg.ПРОДАВЕЦ + tg.СХЕМА + "\nПОЛУЧАТЕЛИ:\n\n=== ИНН 1\nКомпания: x\n" + "Деятельность: производство " * 10
    с, тел = gen_provider.razrezat_promt(пр)
    assert с and тел.startswith("\nПОЛУЧАТЕЛИ"), "граница не режется"
    print("статика в system: %d знаков" % len(с))
except Exception as е:
    shutil.copy2(б, П); print("откат:", е); print("=== КЭШ ГЕЙТА: ОТКАТ ==="); sys.exit()
print("бэкап:", б); print("=== КЭШ ГЕЙТА: ПРИМЕНЕНО ===")
