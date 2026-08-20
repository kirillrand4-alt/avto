# -*- coding: utf-8 -*-
r"""Почему отбившиеся адреса прошли заслон: не пробовали или проба не могла."""
import json, os, sqlite3
АДРЕСА = ['sales@premfire.ru','snab@taimyr-fish.ru','neapol.sklad@mail.ru',
          'hr@sibach.store','pastarellab@mail.ru','snab@konex.ru',
          'okna_sklad@alkona.net','office@dscavtostrada.com','shop@zavodsota.ru']
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
вышло = []
for a in АДРЕСА:
    дом = a.split('@')[1]
    соседи = dict(c.execute(
        'select verdict, count(*) from addr_probe where email like ? '
        'group by verdict', ('%@' + дом,)).fetchall())
    отпр = c.execute('select min(ts) t from send_log where lower(email)=?',
                     (a,)).fetchone()
    вышло.append({'адрес': a, 'домен': дом, 'отправлено': (отпр['t'] or '')[:19],
                  'вердикты_домена': соседи})
# был ли адрес в задании пробе
задания = []
for п in (r'C:\sender\probe-zadanie.json', r'C:\seostat\drop\probe-zadanie.json'):
    if os.path.exists(п):
        try:
            d = json.load(open(п, encoding='utf-8'))
            спис = d if isinstance(d, list) else (d.get('adresa') or d.get('emails') or [])
            задания.append({'файл': п, 'адресов': len(спис),
                            'наши_в_задании': [a for a in АДРЕСА
                                               if a in [str(x).lower() for x in спис]]})
        except Exception as e:
            задания.append({'файл': п, 'ошибка': str(e)[:80]})
c.close()
print(json.dumps({'адреса': вышло, 'задание_пробе': задания}, ensure_ascii=False, indent=1))
