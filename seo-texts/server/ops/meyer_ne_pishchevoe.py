# -*- coding: utf-8 -*-
"""ai_letter: линза покупателя Meyer — «не пищевое производство» не повод для
НЕ ПОКУПАТЕЛЬ (владелец 12–13.10: пластик, стекло, кварц, щепа, вторсырьё — покупатели).
Такую метку снимаем, письмо идёт в починку. Правка по якорям, бэкап .bak-*.
Откат: meyer_ne_pishchevoe.py --otkat (возвращает последний бэкап этой правки)."""
import glob, io, os, py_compile, shutil, sys, time
ПУТЬ = r"C:\sender\sender\ai_letter.py"
МЕТКА = "НЕПИЩЕВОЕ_НЕ_ДОВОД"
if "--otkat" in sys.argv:
    б = sorted(glob.glob(ПУТЬ + ".bak-nepishch-*"))
    if not б: print("бэкапа нет"); sys.exit(0)
    shutil.copy2(б[-1], ПУТЬ); print("откат из", б[-1]); print("=== НЕПИЩЕВОЕ: ОТКАЧЕНО ==="); sys.exit(0)
т = io.open(ПУТЬ, encoding="utf-8").read()
if МЕТКА in т:
    print("=== НЕПИЩЕВОЕ: УЖЕ БЫЛО ==="); sys.exit(0)
ЯКОРЬ = "        безнадёжные = {i: п for i, п in плохие.items()\n"
ВСТАВКА = (
"        # " + МЕТКА + " (владелец 16.10). Линза Meyer ставила НЕ ПОКУПАТЕЛЬ\n"
"        # стеклотаре со стеклобоем, кварцу, лесопилкам, грануле ПВХ с доводом\n"
"        # «не пищевое производство» - вопреки правилам 12-13.10 в её же промпте.\n"
"        # Для Meyer этот довод не в счёт: снимаем метку, письмо идёт в починку.\n"
"        for i, п in list(плохие.items()):\n"
"            if (str(div_of.get(i, self.default_division) or '').startswith('meyer')\n"
"                    and НЕ_ПОКУПАТЕЛЬ in str(п or '')\n"
"                    and re.search(r'(?i)не\\s+(?:является\\s+|относится\\s+к\\s+)?пищев|для\\s+пищев\\w*\\s+(?:сортировк|производств)', str(п))):\n"
"                плохие[i] = str(п).replace(НЕ_ПОКУПАТЕЛЬ + ':', '').replace(НЕ_ПОКУПАТЕЛЬ, '').strip()\n")
if т.count(ЯКОРЬ) != 1:
    print("якорь: %d" % т.count(ЯКОРЬ)); print("=== НЕПИЩЕВОЕ: НЕ ПРИМЕНЕНО ==="); sys.exit(0)
б = ПУТЬ + ".bak-nepishch-%d" % int(time.time())
shutil.copy2(ПУТЬ, б)
io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(ЯКОРЬ, ВСТАВКА + ЯКОРЬ))
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:
    shutil.copy2(б, ПУТЬ); print("сбой, откат:", е); print("=== НЕПИЩЕВОЕ: ОТКАТ ==="); sys.exit(0)
print("бэкап:", б); print("=== НЕПИЩЕВОЕ: ПРИМЕНЕНО ===")
