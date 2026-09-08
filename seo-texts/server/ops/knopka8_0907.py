# -*- coding: utf-8 -*-
"""Только чтение: на какой адрес ложится черновик ответа из карточки лида."""
import io

т = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8",
            errors="ignore").read()
i = т.find('@app.post("/leads/{lead_id}/reply")')
j = т.find("ВЛОЖЕНИЯ_КОРЕНЬ", i)
k = т.find("\n    @app.", j)
print(т[j:k if k > 0 else j + 2600])
