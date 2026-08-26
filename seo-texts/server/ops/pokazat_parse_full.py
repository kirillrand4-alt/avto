# -*- coding: utf-8 -*-
import io
т = io.open(r"C:\sender\sender\mailbrowser.py", encoding="utf-8").read()
i = т.index("def _parse_full")
print(repr(т[i:i + 1500]))
