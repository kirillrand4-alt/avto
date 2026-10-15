# -*- coding: utf-8 -*-
"""ai_letter: пример в правилах КЦ «реализовал» -> «выполнил» (заслон канцелярита бракует свой же пример)."""
import io
import py_compile
П = r"C:\sender\sender\ai_letter.py"
т = io.open(П, encoding="utf-8").read()
н = т.replace("реализовал больше 6000 объектов", "выполнил больше 6000 объектов")
if н != т:
    io.open(П, "w", encoding="utf-8").write(н)
    py_compile.compile(П, doraise=True)
print("=== РЕАЛИЗОВАЛ: %s ===" % ("ЗАМЕНЕНО" if н != т else "УЖЕ БЫЛО"))
