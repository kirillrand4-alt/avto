# -*- coding: utf-8 -*-
"""Что теперь вернёт блок контактов для «Росткрана» (оба источника)."""
import importlib.util
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')
# повторяем логику помощника, читая тот же новый файл
import io, os, re, sqlite3
т = io.open(r'C:\sender\_tmp\api_app_novyy4.py', encoding='utf-8', errors='replace').read()
нач = т.index('    def _kontakty_kompanii(')
кон = т.index('    @app.get("/leads/{lead_id}")', нач)
import textwrap
кусок = textwrap.dedent(т[нач:кон])
prostranstvo = {'os': os, 're': re, 'json': json}
exec(кусок, prostranstvo)
из = prostranstvo['_kontakty_kompanii']('3906283152')
print(json.dumps({'телефонов': len(из['telefony']), 'телефоны': из['telefony'],
                  'людей': len(из['lyudi']),
                  'люди': [{'кто': l['person'], 'роль': l['role'],
                            'откуда': l['source']} for l in из['lyudi']]},
                 ensure_ascii=False, indent=1)[:2200])
