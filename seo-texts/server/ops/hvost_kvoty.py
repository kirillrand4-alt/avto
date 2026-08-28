# -*- coding: utf-8 -*-
import io
т = io.open(r"C:\sender\sender\confirm.py", encoding="utf-8").read()
i = т.find("def _kvota_kompanii")
j = т.find("\n    def ", i + 10)
print(repr(т[j - 260:j + 40]))
