# -*- coding: utf-8 -*-
import json, sqlite3
АДРЕСА = ['sales@premfire.ru','snab@taimyr-fish.ru','neapol.sklad@mail.ru',
          'hr@sibach.store','pastarellab@mail.ru','snab@konex.ru',
          'okna_sklad@alkona.net','office@dscavtostrada.com','shop@zavodsota.ru',
          'test@mail.ru']
итог = {}
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
итог['столбцы'] = [r[1] for r in c.execute('pragma table_info(addr_probe)')]
итог['всего'] = c.execute('select count(*) from addr_probe').fetchone()[0]
кол = итог['столбцы']
поле = 'verdict' if 'verdict' in кол else ('verdikt' if 'verdikt' in кол else None)
if поле:
    итог['по_вердиктам'] = dict(c.execute(
        'select %s, count(*) from addr_probe group by %s' % (поле, поле)).fetchall())
q = ','.join('?' * len(АДРЕСА))
итог['наши'] = [dict(r) for r in c.execute(
    'select * from addr_probe where lower(email) in (%s)' % q,
    [a.lower() for a in АДРЕСА])]
# когда им писали
итог['когда_писали'] = [dict(r) for r in c.execute(
    'select email, ts, outcome from send_log where lower(email) in (%s) '
    'order by ts' % q, [a.lower() for a in АДРЕСА])]
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
