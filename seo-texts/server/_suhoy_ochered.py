# -*- coding: utf-8 -*-
r"""Сухой счёт: кого вернули бы в очередь."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import zenka_v_ochered as Z  # noqa: E402

сводка, _ = Z.kandidaty()
print(json.dumps(сводка, ensure_ascii=False, indent=1))
