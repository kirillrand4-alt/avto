# -*- coding: utf-8 -*-
"""Показать накопленное в потоках замера (патенты / раскрытие)."""
import io
import json
import os
import sys

ПОТОКИ = {'патенты': r'C:\sender\_ops\pat_patents.jsonl',
          'раскрытие': r'C:\sender\_ops\pat_disclosure.jsonl'}
что = sys.argv[1] if len(sys.argv) > 1 else 'патенты'
п = ПОТОКИ.get(что, что)
if not os.path.exists(п):
    print('нет файла', п)
    sys.exit(0)
for ln in io.open(п, encoding='utf-8', errors='replace'):
    try:
        x = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    print(json.dumps(x, ensure_ascii=False, indent=1)[:4500])
    print('-' * 70)
