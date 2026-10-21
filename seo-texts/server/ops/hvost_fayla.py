# -*- coding: utf-8 -*-
"""Хвост текстового файла: hvost_fayla.py <путь> [знаков=3000]"""
import io
import sys
т = io.open(sys.argv[1], encoding="utf-8", errors="replace").read()
print(т[-int(sys.argv[2]) if len(sys.argv) > 2 else -3000:])
