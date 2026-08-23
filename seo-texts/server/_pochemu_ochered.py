# -*- coding: utf-8 -*-
r"""Почему второй круг взял 14 609, если 6025 уже отмечены пройденными."""
import json
import os
import sqlite3

КЕШ = r'C:\seostat\drop\pagecache'
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
свои = {str(r[0]) for r in c.execute('select inn from companies')}
отмечены = {str(r[0]) for r in c.execute(
    "select inn from stage_log where stage='phone_podpis'")}
c.close()
в_кэше = {n.split('.')[0] for n in os.listdir(КЕШ) if n.endswith('.json.gz')}
наши = в_кэше & свои
print(json.dumps({
    'кэш_и_наши': len(наши),
    'отмечено_всего': len(отмечены),
    'отмечено_из_наших': len(отмечены & наши),
    'отмечено_НЕ_из_наших': len(отмечены - наши),
    'осталось_бы_сейчас': len(наши - отмечены),
}, ensure_ascii=False, indent=1))
