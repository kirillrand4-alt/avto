# -*- coding: utf-8 -*-
r"""Сухой прогон подписей по 600 компаниям: что бы записали."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import roli_telefonov as R  # noqa: E402

print(json.dumps(R.progon(predel=600, primenit=False),
                 ensure_ascii=False, indent=1))
