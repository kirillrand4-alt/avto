# -*- coding: utf-8 -*-
"""Только чтение: отдать компактно (строка;инн;как;стоп) страницами.
argv: <страница 0..n> [размер=120]"""
import io
import json
import os
import sys

БАЗА = os.path.dirname(os.path.abspath(__file__))
уч = json.loads(io.open(os.path.join(БАЗА, "vebinar_inn_rezultat.json"), encoding="utf-8").read())
стоп = json.loads(io.open(os.path.join(БАЗА, "vebinar_stop_rezultat.json"), encoding="utf-8").read())
по_стр = {з["строка"]: з for з in стоп}

стр = int(sys.argv[1]) if len(sys.argv) > 1 else 0
разм = int(sys.argv[2]) if len(sys.argv) > 2 else 120
кусок = уч[стр * разм:(стр + 1) * разм]
for u in кусок:
    з = по_стр.get(u["строка"])
    print("%s;%s;%s;%s" % (u["строка"], u.get("inn") or "", u.get("как") or "",
                           (з["сила"] if з else "")))
print("### стр=%d выдано=%d всего=%d" % (стр, len(кусок), len(уч)))
