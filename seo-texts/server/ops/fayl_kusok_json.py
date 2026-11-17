# -*- coding: utf-8 -*-
"""Кусок файла по символам одной JSON-строкой (стыки кусков не портятся): fayl_kusok_json.py <путь> <с> <длина>"""
import io, json, sys
т = io.open(sys.argv[1], encoding="utf-8", errors="replace").read()
с, д = int(sys.argv[2]), int(sys.argv[3])
print("ВСЕГО %d" % len(т)); print("КУСОК " + json.dumps(т[с:с + д], ensure_ascii=True))
