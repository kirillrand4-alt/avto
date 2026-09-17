# -*- coding: utf-8 -*-
"""Итог дотяжки + удаление дублей (строка, чей текст совпал с уже существующей)."""
import io, json, os, sqlite3, time, collections

DIR = r'C:\sender\server'
БАЗА = r'C:\sender\enrich.db'
o = {}

# 1. Итог перекачки слабых.
свод = collections.Counter(); длиннее = 0
п = os.path.join(DIR, 'dobor_slabyh.jsonl')
if os.path.exists(п):
    with io.open(п, encoding='utf-8', errors='replace') as f:
        for s in f:
            try: з = json.loads(s)
            except Exception: continue
            свод[з.get('итог','?')] += 1
            ново=(з.get('стало_what') or '').strip(); было=(з.get('было_what') or '').strip()
            if ново and len(ново) > len(было)*1.3: длиннее += 1
o['перекачка_слабых'] = dict(свод)
o['текст_стал_полнее'] = длиннее

# 2. Дубли: показать и удалить с бэкапом.
д = os.path.join(DIR, 'dobor_slabyh.dubli.jsonl')
пары = []
if os.path.exists(д):
    with io.open(д, encoding='utf-8', errors='replace') as f:
        for s in f:
            try: з = json.loads(s)
            except Exception: continue
            пары.append((str(з['inn']), з['url'], з.get('what','')))
o['дублей_в_списке'] = len(пары)

if пары:
    c = sqlite3.connect(БАЗА, timeout=120); c.execute('pragma busy_timeout=120000')
    к_удалению = []
    for inn, url, ново in пары:
        for р in c.execute(
                "select inn, source, event_type, what, coalesce(sum,''), hotness, "
                "source_url, updated_at from signals where inn=? and source_url=?",
                (inn, url)).fetchall():
            к_удалению.append({'inn': р[0], 'источник': р[1], 'тип': р[2], 'старое_что': р[3],
                               'сумма': р[4], 'важность': р[5], 'ссылка': р[6],
                               'узнали': р[7], 'новое_что_совпало_с_существующим': ново})
    o['найдено_строк'] = len(к_удалению)
    if к_удалению:
        бэк = os.path.join(DIR, 'udalyonnye-dubli-%s.jsonl' % time.strftime('%d%m-%H%M'))
        with io.open(бэк, 'w', encoding='utf-8') as f:
            for з in к_удалению:
                f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush(); os.fsync(f.fileno())
        try:
            import shutil
            shutil.copyfile(бэк, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(бэк)))
        except Exception: pass
        o['бэкап'] = os.path.basename(бэк)
        было = c.execute('select count(*) from signals').fetchone()[0]
        n = 0
        for inn, url, _ in пары:
            n += c.execute('delete from signals where inn=? and source_url=?', (inn, url)).rowcount
        c.commit()
        стало = c.execute('select count(*) from signals').fetchone()[0]
        o.update({'удалено': n, 'сигналов_было': было, 'сигналов_стало': стало})
        o['примеры_удалённых'] = [{'тип': з['тип'], 'что': (з['старое_что'] or '')[:90]}
                                  for з in к_удалению[:5]]
    c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:3500])
