# -*- coding: utf-8 -*-
r"""Инпласт: роли телефонов, запись номера и полный список контактов."""
import importlib
import json
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
LS = importlib.import_module('lid_ssylka')
importlib.reload(LS)

ИНН = '6143038853'
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
ряд = s.execute('select * from leads where inn=? order by id desc limit 1',
                (ИНН,)).fetchone()
лид = dict(ряд) if ряд else {'inn': ИНН}
s.close()
карта = LS.karta_kompanii(ИНН, {'email': лид.get('email'),
                                'phone': лид.get('phone')})
print(json.dumps({
    'телефоны': [{'номер': т['nomer'], 'роль': т.get('kto'),
                  'источников': len(т['istochniki']),
                  'страниц': len([и for и in т['istochniki'] if и.get('url')])}
                 for т in карта['telefony']],
    'почты': [{'адрес': п['adres'], 'роль': п.get('rol'),
               'источник': п.get('istochnik'), 'страниц': len(п.get('stranicy') or [])}
              for п in карта['pochty']],
}, ensure_ascii=False, indent=1)[:2600])
