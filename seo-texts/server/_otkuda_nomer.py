import sqlite3, time, json
НОМ, ИНН, ПОЧТА = '9663218050', '9701069920', 'vodorod-gaz'
print('===ИТОГ===')
for бд in (r'C:\sender\sender.db', r'C:\sender\enrich.db', r'C:\sender\obzvon-index.db'):
    try:
        c = sqlite3.connect('file:%s?mode=ro' % бд, uri=True, timeout=60)
    except Exception as e:
        print(бд, 'ошибка', e); continue
    тт = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
    for т in тт:
        кол = [(r[1], (r[2] or '').upper()) for r in c.execute('pragma table_info("%s")' % т)]
        текст = [к for к, тип in кол if тип in ('', 'TEXT') or 'CHAR' in тип]
        if not текст: continue
        t0 = time.time()
        for иск in (НОМ, ИНН, ПОЧТА):
            усл = ' or '.join('"%s" like ?' % к for к in текст)
            try:
                рр = c.execute('select * from "%s" where %s limit 5' % (т, усл), ['%' + иск + '%'] * len(текст)).fetchall()
            except Exception as e:
                continue
            for r in рр:
                d = {к: (str(v)[:300] if v is not None else None) for (к, _), v in zip(кол, r)}
                # показать только поля с совпадением + источники/даты
                кор = {к: v for к, v in d.items() if v and (иск in v or any(x in к.lower() for x in ('source', 'ист', 'url', 'origin', 'kind', 'type', 'ts', 'created', 'date', 'inn', 'name', 'reason')))}
                print('%s | %s | искали %s | %s' % (бд.split('\\')[-1], т, иск, json.dumps(кор, ensure_ascii=False)[:900]))
        if time.time() - t0 > 60:
            print('  (долго: %s %.0f с)' % (т, time.time() - t0))
    c.close()
