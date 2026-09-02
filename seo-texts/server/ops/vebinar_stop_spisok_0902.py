# -*- coding: utf-8 -*-
"""Только чтение: отдать список отсеянных по сделкам с причинами.
argv: <страница 0/1> [размер=28]"""
import io
import json
import os
import sys

БАЗА = os.path.dirname(os.path.abspath(__file__))
стоп = json.loads(io.open(os.path.join(БАЗА, "vebinar_stop_rezultat.json"),
                          encoding="utf-8").read())
порядок = {"точное": 0, "среднее": 1, "слабое": 2}
стоп.sort(key=lambda з: (порядок.get(з["сила"], 9), з["строка"]))

стр = int(sys.argv[1]) if len(sys.argv) > 1 else 0
разм = int(sys.argv[2]) if len(sys.argv) > 2 else 28
for з in стоп[стр * разм:(стр + 1) * разм]:
    прич = " + ".join(з["причины"])
    print("%s|%s|%s|%s|%s|%s" % (з["строка"], з["сила"], з["email"],
                                 з["компания"], з.get("inn") or "", прич[:96]))
print("### стр=%d всего=%d" % (стр, len(стоп)))
