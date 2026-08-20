# -*- coding: utf-8 -*-
r"""Происхождение строк addr_probe с пустым source: не из обзвона ли."""
import json, sqlite3
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
o = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True)
итог = {}
пустые = {}
for e, v in s.execute("select lower(email), verdict from addr_probe "
                      "where coalesce(source,'')=''"):
    пустые[e] = v
итог['пустых_source'] = len(пустые)
кол = [r[1] for r in o.execute('pragma table_info(email_probe)')]
итог['столбцы_email_probe'] = кол
итог['строк_email_probe'] = o.execute('select count(*) from email_probe').fetchone()[0]
поле_адр = next((k for k in ('email', 'addr', 'address') if k in кол), кол[0])
поле_вер = next((k for k in ('verdict', 'verdikt', 'status', 'result', 'answer')
                 if k in кол), None)
обз = {}
for r in o.execute('select "%s", %s from email_probe' % (
        поле_адр, ('"%s"' % поле_вер) if поле_вер else "''")):
    обз[str(r[0]).lower()] = str(r[1])
итог['уникальных_в_обзвоне'] = len(обз)
совпало = set(пустые) & set(обз)
итог['пересечение'] = len(совпало)
итог['доля_пустых_из_обзвона'] = round(100.0 * len(совпало) / max(1, len(пустые)), 1)
итог['примеры_совпавших'] = [
    {'адрес': a, 'в_панели': пустые[a], 'в_обзвоне': обз[a][:40]}
    for a in list(совпало)[:6]]
не_нашлись = [a for a in пустые if a not in обз][:6]
итог['примеры_не_из_обзвона'] = [{'адрес': a, 'вердикт': пустые[a]} for a in не_нашлись]
s.close(); o.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
