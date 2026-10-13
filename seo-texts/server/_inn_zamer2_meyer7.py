# -*- coding: utf-8 -*-
# 13.10: этап 0 поиска ИНН, уточнение замера (meyer7-inn-zamer.jsonl): только ключи САЙТ: (BY-ключи уже с УНП — не цель);
# 13.10: в enrich.db лежат и суррогатные ключи Зенки — берём только ИНН с верной контрольной цифрой.
# совпадение домена с базой по силе колонки (сайт/почта компании — сильная; кандидат/мета — слабая); сверка ИНН со
# страницы с ИНН из базы (насколько база надёжна); дубли со списком. Базу не меняет. Итог — сводка + meyer7-inn-zamer2.jsonl.
import collections, io, json, os, re, sqlite3, time
DIR = r'C:\sender\server'
print('===ИТОГ===', time.strftime('%H:%M:%S'))


def инн_верен(s):
    d = [int(c) for c in s]
    if len(d) == 10:
        return sum(a * b for a, b in zip((2, 4, 10, 3, 5, 9, 4, 6, 8), d)) % 11 % 10 == d[9] and s[:2] != '00'
    if len(d) == 12:
        n11 = sum(a * b for a, b in zip((7, 2, 4, 10, 3, 5, 9, 4, 6, 8), d)) % 11 % 10
        n12 = sum(a * b for a, b in zip((3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8), d)) % 11 % 10
        return n11 == d[10] and n12 == d[11] and s[:2] != '00'
    return False


def хост(u):
    u = re.sub(r'^[a-z]+://', '', str(u or '').strip().lower()).split('/')[0].split(':')[0]
    return u[4:] if u.startswith('www.') else u


з = [json.loads(s) for s in io.open(os.path.join(DIR, 'meyer7-inn-zamer.jsonl'), encoding='utf-8') if s.strip()]
цели = [r for r in з if r['ключ'].startswith('САЙТ:')]
сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))['компании']
в_списке = {i for i in сп if i.isdigit()}
домены = {r['домен'] for r in цели}
СИЛА = {'obzvon': {'sites': 'сильная', 'emails_site': 'сильная', 'emails_base': 'сильная'},
        'companies': {'site': 'сильная', 'best_email': 'сильная', 'site_checko': 'сильная', 'cand_site': 'слабая',
                      'site_meta_url': 'слабая'}}
карта = collections.defaultdict(lambda: collections.defaultdict(set))  # домен → инн → {сила}
for бд, табл in ((r'C:\sender\obzvon-index.db', 'obzvon'), (r'C:\sender\enrich.db', 'companies')):
    c = sqlite3.connect('file:%s?mode=ro' % бд.replace('\\', '/'), uri=True, timeout=120)
    кол = list(СИЛА[табл])
    for р in c.execute('select inn, %s from %s' % (', '.join(кол), табл)):
        i = str(р[0] or '')
        if not i.isdigit() or not инн_верен(i):  # суррогаты Зенки (00000001643…) в enrich.db — не ИНН
            continue
        for k, v in zip(кол, р[1:]):
            for кус in re.split(r'[\s,;|]+', str(v or '')):
                д = хост(кус.split('@')[-1]) if '.' in кус else ''
                if д in домены:
                    карта[д][i].add(СИЛА[табл][k])
    c.close()
сч = collections.Counter()
свер = collections.Counter()
примеры = collections.defaultdict(list)
with io.open(os.path.join(DIR, 'meyer7-inn-zamer2.jsonl') + '.tmp', 'w', encoding='utf-8') as f:
    for r in цели:
        свои = [v for v in r['инн'] if v not in (r.get('инн_частые') or [])]
        б = карта.get(r['домен']) or {}
        сильн = sorted(i for i, с in б.items() if 'сильная' in с)
        слаб = sorted(i for i in б if i not in сильн)
        if len(свои) == 1:
            итог = 'А. ИНН со страницы (один)'
        elif len(свои) > 1:
            итог = 'Б. ИНН со страницы (несколько)'
        elif len(сильн) == 1:
            итог = 'В. база: сайт/почта компании (один ИНН)'
        elif len(сильн) > 1:
            итог = 'Г. база: несколько ИНН на домен'
        elif r['огрн']:
            итог = 'Д. только ОГРН со страницы'
        elif r['юр'] or r['ип']:
            итог = 'Е. только юрназвание'
        elif слаб:
            итог = 'Ж. база: только слабое совпадение'
        elif not r['страниц']:
            итог = 'З. нет скачанных страниц'
        else:
            итог = 'И. ничего'
        сч[итог] += 1
        if len(свои) == 1 and сильн:
            свер['страница и база: совпал' if свои[0] in сильн else 'страница и база: РАЗНЫЕ'] += 1
            if свои[0] not in сильн and len(примеры['разные']) < 8:
                примеры['разные'].append((r['домен'], свои[0], сильн[:3]))
        кандидаты = свои or сильн
        if any(v in в_списке for v in кандидаты):
            сч['доп: ИНН уже есть в списке (дубль)'] += 1
            if len(примеры['дубль']) < 6:
                примеры['дубль'].append((r['домен'], [v for v in кандидаты if v in в_списке][:2]))
        сч['доп: .by-домен'] += r['домен'].endswith('.by')
        сч['доп: .by и УНП на странице'] += r['домен'].endswith('.by') and bool(r['унп'])
        f.write(json.dumps(dict(r, итог2=итог, база_сильн=сильн, база_слаб=слаб), ensure_ascii=False) + '\n')
    f.flush()
    os.fsync(f.fileno())
os.replace(os.path.join(DIR, 'meyer7-inn-zamer2.jsonl') + '.tmp', os.path.join(DIR, 'meyer7-inn-zamer2.jsonl'))
print('САЙТ-компаний', len(цели))
for k, v in sorted(сч.items()):
    print('  ', k, v)
print('сверка', dict(свер))
print('примеры', json.dumps(примеры, ensure_ascii=False)[:1500])
