# -*- coding: utf-8 -*-
"""Как выглядит обработка not_interested в боевом imap_watcher.

Патч не применился: якорь не нашёлся ни разу. Значит строка на сервере
другой формы — там чужая база плюс наши прежние правки. Гадать нельзя,
печатаем окрестности дословно, с номерами строк.
"""
import io

путь = r"C:\sender\sender\imap_watcher.py"
строки = io.open(путь, encoding="utf-8").read().splitlines()

места = [н for н, с in enumerate(строки) if "not_interested" in с]
print("вхождений «not_interested»: %d" % len(места))
for н in места:
    а, б = max(0, н - 4), min(len(строки), н + 8)
    print("\n--- около строки %d ---" % (н + 1))
    for к in range(а, б):
        print("%5d| %s" % (к + 1, строки[к]))

print("\n=== СТРОКА С _reply_pipeline ===")
for н, с in enumerate(строки):
    if "_reply_pipeline is not None" in с:
        print("%5d| %s" % (н + 1, с))

print("\n=== ЕСТЬ ЛИ УЖЕ НАШ ФЛАГ ===")
print("  _otkaz в файле: %s" % ("да" if any("_otkaz" in с for с in строки)
                                else "нет"))
print("  _lid в файле:   %s" % ("да" if any("def _lid" in с for с in строки)
                                else "нет"))
