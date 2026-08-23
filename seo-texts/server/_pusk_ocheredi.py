# -*- coding: utf-8 -*-
r"""Дописать в очередь Зенки тех, кого сайт не пустил."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import zenka_v_ochered as Z  # noqa: E402

итог = Z.dopisat()
итог.pop('примеры', None)
print(json.dumps(итог, ensure_ascii=False, indent=1))
