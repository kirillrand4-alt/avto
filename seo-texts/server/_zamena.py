# -*- coding: utf-8 -*-
r"""Есть ли у компаний с catch-all адресом альтернатива с вердиктом «есть»."""
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
проба = {}
for e, v in c.execute('select lower(email), verdict from addr_probe'):
    проба[e] = v
по_инн = {}
for инн, эм in c.execute("select coalesce(inn,''), lower(email) from recipients "
                         "where coalesce(email,'')<>''"):
    if инн:
        по_инн.setdefault(инн, []).append(эм)
c.close()
всё = замена = без_замены = 0
for инн, спис in по_инн.items():
    вердикты = {проба.get(e) for e in спис}
    n = sum(1 for e in спис if проба.get(e) == 'принимает всё')
    if not n:
        continue
    всё += n
    if 'есть' in вердикты:
        замена += n
    else:
        без_замены += n
print(json.dumps({'получателей_принимает_всё': всё,
                  'у_компании_есть_проверенный_адрес': замена,
                  'альтернативы_нет': без_замены,
                  'компаний_всего': len(по_инн)}, ensure_ascii=False))
