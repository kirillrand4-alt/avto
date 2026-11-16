# -*- coding: utf-8 -*-
"""Кусок текстового файла по символам: fayl_kusok.py <путь> <с> <длина>. Только чтение."""
import io, sys
т = io.open(sys.argv[1], encoding="utf-8", errors="replace").read()
с, д = int(sys.argv[2]), int(sys.argv[3])
print("всего %d" % len(т)); print(т[с:с + д])
