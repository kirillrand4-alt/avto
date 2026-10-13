# -*- coding: utf-8 -*-
# 13.10, владелец («Агро-Альянс»: письмо ушло на control@agro-al.ru холдинга с активными сделками Meyer — сайт был записан
# за тёзкой по базе обзвона, а юрлица холдинга сайта в наших данных не имели, проверка сделок по ИНН/домену их не видела):
# «да, запускай» — по каждому сайту компаний списка юрназвания/ИНН/ОГРН с его страниц (кэш + папки Зенки, только свой
# домен; _inn_zamer_meyer7.одна) сверяются с компаниями, у которых АКТИВНАЯ сделка Meyer (meyer7-sdelki-aktivnye.tsv):
# ИНН/ОГРН со страницы = ИНН/ОГРН сделки — «точно»; ядро юрназвания = ядро названия компании сделки — «по названию»
# (сильное — от 2 слов и 12 знаков, иначе слабое). Названия компаний сделок — из enrich.db/obzvon (DaData не тратим).
# Базу не меняет. Итог — meyer7-sdelki-yur.jsonl (fsync) + дроп, сводка в логе sdelki_yur_*.log.
import collections, io, json, os, sqlite3, sys, time
DIR = r'C:\sender\server'
ВЫХ = os.path.join(DIR, 'meyer7-sdelki-yur.jsonl')


def main():
    sys.path.insert(0, DIR)
    import _inn_zamer_meyer7 as Z
    import meyer7_inn_poisk as P
    t0 = time.time()
    сд = {}
    for s in io.open(r'C:\seostat\drop\drop-storage\meyer7-sdelki-aktivnye.tsv', encoding='utf-8').read().splitlines()[1:]:
        ч = s.split('\t')
        if ч and ч[0].isdigit():
            сд[ч[0]] = ч[1] if len(ч) > 1 else ''
    имена, огрн_сд = collections.defaultdict(set), {}
    for бд, запрос in ((r'C:\sender\enrich.db', 'select inn, name, short_name, ogrn from companies'),
                       (r'C:\sender\obzvon-index.db', 'select inn, name_short, name_full, ogrn from obzvon')):
        c = sqlite3.connect('file:%s?mode=ro' % бд.replace('\\', '/'), uri=True, timeout=120)
        for i, a, b, о in c.execute(запрос):
            i = str(i or '')
            if i in сд:
                for v in (a, b):
                    я = P.ядро(v)
                    if я:
                        имена[я].add(i)
                if о:
                    огрн_сд[str(о)] = i
        c.close()
    print('активных сделок (ИНН)', len(сд), '| с названием', len({i for v in имена.values() for i in v}), '| ядер', len(имена), flush=True)
    сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))['компании']
    конт = {}
    for s in open(os.path.join(DIR, 'meyer7-kontakty.jsonl'), 'rb'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn') in сп and з.get('сайт'):
            конт[з['inn']] = з['сайт']
    карта = json.load(io.open(os.path.join(DIR, 'meyer7-zenno-surrogat.json'), encoding='utf-8'))
    сур = collections.defaultdict(list)
    for кл, i in карта.items():
        сур[i].append(кл)
    цели = {i: (конт.get(i) or к.get('сайт') or '') for i, к in сп.items() if (конт.get(i) or к.get('сайт'))}
    ключи = set(цели) | {к for i in цели for к in сур.get(i, [])}
    файлы = collections.defaultdict(list)
    for п in Z.ZENNO:
        if os.path.isdir(п):
            for e in os.scandir(п):
                if e.name.endswith('.html'):
                    k, _, n = e.name[:-5].rpartition('_')
                    if k in ключи and n.isdigit():
                        файлы[k].append((e.path, int(n), п))
    задачи = [(i, с, сур.get(i, []), {k: файлы[k] for k in [i] + сур.get(i, []) if k in файлы}) for i, с in цели.items()]
    print('компаний с сайтом', len(задачи), '| индекс папок Зенки за %.1f мин' % ((time.time() - t0) / 60), flush=True)
    from concurrent.futures import ProcessPoolExecutor
    рез = []
    with ProcessPoolExecutor(6) as ex:
        for n, r in enumerate(ex.map(Z.одна, задачи, chunksize=25), 1):
            рез.append(r)
            if n % 2000 == 0:
                print('разобрано', n, 'из', len(задачи), 'за %.1f мин' % ((time.time() - t0) / 60), flush=True)
    дом_имя = collections.defaultdict(set)
    for r in рез:
        for ю in list(r['юр']) + list(r['ип']):
            дом_имя[P.ядро(ю)].add(r['домен'])
    сч = collections.Counter()
    with io.open(ВЫХ + '.tmp', 'w', encoding='utf-8') as f:
        for r in рез:
            i = r['ключ']
            совп = []
            for v in r['инн']:
                if v in сд and v != i:
                    совп.append({'как': 'ИНН со страницы', 'сила': 'точно', 'инн_сделки': v, 'что': v, 'страниц': r['инн'][v]})
            for v in r['огрн']:
                if v in огрн_сд and огрн_сд[v] != i:
                    совп.append({'как': 'ОГРН со страницы', 'сила': 'точно', 'инн_сделки': огрн_сд[v], 'что': v, 'страниц': r['огрн'][v]})
            for ю, n in list(r['юр'].items()) + list(r['ип'].items()):
                я = P.ядро(ю)
                for v in sorted(имена.get(я) or []):
                    if v != i and not any(x['инн_сделки'] == v for x in совп):
                        сильн = len(я.split()) >= 2 and len(я) >= 12
                        совп.append({'как': 'юрназвание на сайте', 'сила': 'по названию (сильное)' if сильн else 'по названию (слабое)',
                                     'инн_сделки': v, 'что': ю, 'страниц': n, 'сайтов_с_этим_именем': len(дом_имя[я])})
            if совп:
                сч['компаний с совпадением'] += 1
                for x in совп:
                    сч[x['сила']] += 1
                f.write(json.dumps({'ключ': i, 'домен': r['домен'], 'сайт': цели[i], 'совпадения': совп,
                                    'сделки': {x['инн_сделки']: сд[x['инн_сделки']][:200] for x in совп}}, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(ВЫХ + '.tmp', ВЫХ)
    import shutil
    shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
    print('===ИТОГ СВЕРКИ===', json.dumps(dict(сч), ensure_ascii=False), 'за %.1f мин' % ((time.time() - t0) / 60), flush=True)


if __name__ == '__main__':
    sys.path.insert(0, DIR)
    sys.path.insert(0, r'C:\sender')
    os.chdir(DIR)
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'sdelki_yur_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_sdelki_po_yurnazvaniyam.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False)
        time.sleep(30)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                         ensure_ascii=False))
        sys.exit(0)
    main()
