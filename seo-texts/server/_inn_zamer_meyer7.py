# -*- coding: utf-8 -*-
# 13.10, владелец: «2 пункт составь план» → «запускай». ЭТАП 0 поиска ИНН для компаний «по сайту» (ключ САЙТ:<домен>,
# 5915 в списке meyer7): ЗАМЕР, базу не меняет. По уже скачанным страницам (кэш pagecache + суррогатные ключи Зенки +
# папки razobrano/gotovo) для каждой компании:
#   * ИНН/ОГРН/ОГРНИП с проверкой контрольной цифры, только рядом со словами ИНН/ОГРН (не телефон); контекст
#     «сайт разработан / веб-студия / хостинг» — не в счёт; ИНН, стоящий на 3+ разных доменах, — подозрительный
#     (студия/платформа/каталог);
#   * УНП (Беларусь, 9 цифр рядом со словом УНП);
#   * юрназвание (ООО/АО/ПАО/ЗАО/ОАО «…», ИП Фамилия И.О., «Общество с ограниченной ответственностью «…»»);
#   * домен сайта = домен почты/сайта компании из базы обзвона (obzvon-index.db) или enrich.db → ИНН.
# Итог — meyer7-inn-zamer.jsonl (по компании, fsync) + сводка в логе inn_zamer_*.log. Провайдер не вызывается.
import collections, glob, io, json, os, re, sqlite3, sys, time, zlib
DIR = r'C:\sender\server'
ZENNO = (r'C:\seostat\drop\zenno\razobrano', r'C:\seostat\drop\zenno\gotovo')
КЭШ = r'C:\seostat\drop\pagecache'
ВЫХОД = os.path.join(DIR, 'meyer7-inn-zamer.jsonl')
ПРОЦЕССОВ = 6


def хост(u):
    u = re.sub(r'^[a-z]+://', '', str(u or '').strip().lower()).split('/')[0].split(':')[0]
    return u[4:] if u.startswith('www.') else u


def инн_верен(s):
    d = [int(c) for c in s]
    if len(d) == 10:
        return sum(a * b for a, b in zip((2, 4, 10, 3, 5, 9, 4, 6, 8), d)) % 11 % 10 == d[9]
    if len(d) == 12:
        n11 = sum(a * b for a, b in zip((7, 2, 4, 10, 3, 5, 9, 4, 6, 8), d)) % 11 % 10
        n12 = sum(a * b for a, b in zip((3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8), d)) % 11 % 10
        return n11 == d[10] and n12 == d[11]
    return False


def огрн_верен(s):
    if len(s) == 13:
        return int(s[:12]) % 11 % 10 == int(s[12])
    if len(s) == 15:
        return int(s[:14]) % 13 % 10 == int(s[14])
    return False


КЛЮЧИ_ОКОН = ('ИНН', 'ОГРН', 'УНП', 'ООО', 'ОАО', 'ЗАО', 'ПАО', 'АО ', 'АО&', 'АО«', 'Общество с ограниченной',
              'ОБЩЕСТВО С ОГРАНИЧЕННОЙ', 'ИП ', 'Индивидуальный предприниматель', 'ЧУП', 'ЧТУП', 'СООО', 'ОДО')
ЗАМЕНЫ = (('&nbsp;', ' '), ('&#160;', ' '), ('&laquo;', '«'), ('&raquo;', '»'), ('&quot;', '"'), ('&#171;', '«'),
          ('&#187;', '»'), ('&amp;', '&'), ('&#34;', '"'), ('\xa0', ' '))
ЧУЖОЙ_КОНТЕКСТ = re.compile(r'разработ|создани[ея] сайт|сайт сделан|веб[- ]?студ|web[- ]?studio|хостинг|продвижени|'
                            r'дизайн сайт|developed|powered|битрикс|bitrix|tilda|маркетплейс|агрегатор', re.I)
ИНН_РЕ = re.compile(r'ИНН(?:\s*/\s*КПП)?(?:[\s:№.\-–]|<[^>]{0,80}>){0,12}(\d{10}|\d{12})(?!\d)')
ОГРН_РЕ = re.compile(r'ОГРН(ИП)?(?:[\s:№.\-–]|<[^>]{0,80}>){0,12}(\d{13}|\d{15})(?!\d)')
УНП_РЕ = re.compile(r'УНП(?:[\s:№.\-–]|<[^>]{0,80}>){0,12}(\d{9})(?!\d)')
ЮР_РЕ = re.compile(r'(?<![А-ЯA-Zа-я])(ООО|ОАО|ЗАО|ПАО|АО|СООО|ЧУП|ЧТУП|ОДО|Общество с ограниченной ответственностью|'
                   r'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ|Акционерное общество|АКЦИОНЕРНОЕ ОБЩЕСТВО)\s*[«"“„]\s*'
                   r'([^«»"“”„<>\n]{2,60}?)\s*[»"”“]')
ИП_РЕ = re.compile(r'(?<![А-Яа-я])(?:ИП|Индивидуальный предприниматель)\s+([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]*\.?\s*[А-ЯЁ]?[а-яё]*\.?)')


def окна(html):
    """Куски html вокруг ключевых слов (быстро: поиск подстрок), без тегов и сущностей."""
    out = []
    for к in КЛЮЧИ_ОКОН:
        поз, n = 0, 0
        while n < 25:
            i = html.find(к, поз)
            if i < 0:
                break
            кус = html[max(0, i - 250):i + 300]
            for a, b in ЗАМЕНЫ:
                кус = кус.replace(a, b)
            out.append(кус)
            поз, n = i + len(к), n + 1
    return out


def чистый(t):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t))


def страницы_кэша(ключ):
    п = os.path.join(КЭШ, '%s.json.gz' % re.sub(r'[^\w.-]', '_', ключ or ''))
    try:
        with open(п, 'rb') as f:
            return (json.loads(zlib.decompress(f.read(), 47).decode('utf-8', 'replace')) or {}).get('pages') or []
    except Exception:  # noqa: BLE001
        return []


def страницы_зенки(ключ, файлы):
    out, адреса = [], {}
    for путь, n, п in sorted(файлы, key=lambda x: x[1]):
        if п not in адреса:
            try:
                адреса[п] = [x.strip().lstrip('\ufeff') for x in io.open(os.path.join(п, ключ + '.urls.txt'), encoding='utf-8-sig',
                                                                     errors='replace') if x.strip()]
            except OSError:
                адреса[п] = []
        if n < len(адреса[п]):
            try:
                out.append({'url': адреса[п][n], 'html': io.open(путь, encoding='utf-8', errors='replace').read()[:800000]})
            except OSError:
                pass
    return out


def одна(задача):
    кл, сайт, сур, файлы = задача
    дом = хост(сайт)
    стр, были = [], set()
    for k in [кл] + сур:
        for x in страницы_кэша(k) + страницы_зенки(k, файлы.get(k) or []):
            u = x.get('url') or ''
            if u in были or not x.get('html'):
                continue
            были.add(u)
            стр.append(x)
    инн, огрн, унп, юр, ип = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    инн_чужие = collections.Counter()
    стр_с_инн = set()
    for x in стр:
        u, h = x.get('url') or '', x['html']
        if дом and хост(u) and хост(u) != дом and not хост(u).endswith('.' + дом):
            continue  # страница чужого домена (ссылка наружу) — не улика
        с_инн, с_чуж, с_огрн, с_унп, с_юр, с_ип = set(), set(), set(), set(), set(), set()  # по странице — один раз
        for кус in окна(h):
            for м in ИНН_РЕ.finditer(кус):
                v = м.group(1)
                if not инн_верен(v):
                    continue
                пред = чистый(кус[max(0, м.start() - 200):м.start()])
                (с_чуж if ЧУЖОЙ_КОНТЕКСТ.search(пред[-160:]) else с_инн).add(v)
            for м in ОГРН_РЕ.finditer(кус):
                if огрн_верен(м.group(2)) and not ЧУЖОЙ_КОНТЕКСТ.search(чистый(кус[max(0, м.start() - 200):м.start()])[-160:]):
                    с_огрн.add(м.group(2))
            for м in УНП_РЕ.finditer(кус):
                с_унп.add(м.group(1))
            т = чистый(кус)
            for м in ЮР_РЕ.finditer(т):
                if not ЧУЖОЙ_КОНТЕКСТ.search(т[max(0, м.start() - 160):м.start()]):
                    с_юр.add('%s «%s»' % (м.group(1), м.group(2).strip()))
            for м in ИП_РЕ.finditer(т):
                с_ип.add('ИП ' + м.group(1).strip())
        с_чуж -= с_инн  # где-то на сайте тот же ИНН стоит в своём контексте
        инн.update(с_инн); инн_чужие.update(с_чуж); огрн.update(с_огрн); унп.update(с_унп); юр.update(с_юр); ип.update(с_ип)
        if с_инн:
            стр_с_инн.add(u)
    return {'ключ': кл, 'домен': дом, 'страниц': len(стр), 'инн': dict(инн.most_common(6)), 'инн_чужой_контекст': dict(инн_чужие.most_common(3)),
            'огрн': dict(огрн.most_common(4)), 'унп': dict(унп.most_common(4)), 'юр': dict(юр.most_common(6)), 'ип': dict(ип.most_common(3)),
            'стр_с_инн': len(стр_с_инн)}


def база_доменов():
    """домен → {ИНН} по сайтам и почтам компаний из базы обзвона и enrich.db (колонки ищем по имени)."""
    карта = collections.defaultdict(set)
    общие = {'mail.ru', 'yandex.ru', 'gmail.com', 'bk.ru', 'list.ru', 'inbox.ru', 'rambler.ru', 'ya.ru', 'yandex.by', 'tut.by',
             'mail.by', 'icloud.com', 'outlook.com', 'hotmail.com', 'yahoo.com', 'internet.ru', 'narod.ru', 'eo.tensor.ru'}
    for бд, табл in ((r'C:\sender\obzvon-index.db', 'obzvon'), (r'C:\sender\enrich.db', 'companies')):
        try:
            c = sqlite3.connect('file:%s?mode=ro' % бд.replace('\\', '/'), uri=True, timeout=120)
            кол = [r[1] for r in c.execute('pragma table_info(%s)' % табл)]
            нужн = [k for k in кол if re.search(r'site|mail|email|domain|сайт|почт', k, re.I)]
            if 'inn' not in кол or not нужн:
                print('база', табл, 'колонок нет', кол[:30], flush=True)
                continue
            print('база', табл, 'колонки', нужн, flush=True)
            for р in c.execute('select inn, %s from %s' % (', '.join(нужн), табл)):
                i = str(р[0] or '')
                if not i.isdigit():
                    continue
                for v in р[1:]:
                    for кус in re.split(r'[\s,;|]+', str(v or '')):
                        if not кус or '.' not in кус:
                            continue
                        д = хост(кус.split('@')[-1])
                        if д and д not in общие and not д.endswith('.tensor.ru'):
                            карта[д].add(i)
            c.close()
        except Exception as e:  # noqa: BLE001
            print('база', табл, repr(e)[:150], flush=True)
    return карта


def main():
    t0 = time.time()
    сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))
    комп = сп['компании']
    цели = {i: к for i, к in комп.items() if not i.isdigit()}
    print('компаний без ИНН (не цифровой ключ):', len(цели), collections.Counter(к.get('сегм_как') for к in цели.values()).most_common(),
          flush=True)
    карта_сур = json.load(io.open(os.path.join(DIR, 'meyer7-zenno-surrogat.json'), encoding='utf-8'))
    сур = collections.defaultdict(list)
    for кл, i in карта_сур.items():
        сур[i].append(кл)
    ключи = set(цели) | {к for i in цели for к in сур.get(i, [])}
    файлы = collections.defaultdict(list)
    for п in ZENNO:
        if os.path.isdir(п):
            for e in os.scandir(п):
                if e.name.endswith('.html'):
                    k, _, n = e.name[:-5].rpartition('_')
                    if k in ключи and n.isdigit():
                        файлы[k].append((e.path, int(n), п))
    print('индекс папок Зенки: ключей', len(файлы), 'за %.1f мин' % ((time.time() - t0) / 60), flush=True)
    задачи = [(i, к.get('сайт') or '', сур.get(i, []), {k: файлы[k] for k in [i] + сур.get(i, []) if k in файлы}) for i, к in цели.items()]
    from concurrent.futures import ProcessPoolExecutor
    рез = []
    with ProcessPoolExecutor(ПРОЦЕССОВ) as ex:
        for n, r in enumerate(ex.map(одна, задачи, chunksize=20), 1):
            рез.append(r)
            if n % 500 == 0:
                print('разобрано', n, 'из', len(задачи), 'за %.1f мин' % ((time.time() - t0) / 60), flush=True)
    # ИНН на 3+ разных доменах — студия/платформа/каталог
    дом_инн = collections.defaultdict(set)
    for r in рез:
        for v in r['инн']:
            дом_инн[v].add(r['домен'])
    частые = {v for v, д in дом_инн.items() if len(д) >= 3}
    база = база_доменов()
    в_списке = {i for i in комп if i.isdigit()}
    сч = collections.Counter()
    with io.open(ВЫХОД + '.tmp', 'w', encoding='utf-8') as f:
        for r in рез:
            к = цели[r['ключ']]
            by = r['ключ'].startswith('BY') or r['домен'].endswith('.by') or к.get('регион') == 'Беларусь'
            свои = [v for v in r['инн'] if v not in частые]
            r['инн_частые'] = [v for v in r['инн'] if v in частые]
            r['база_инн'] = sorted(база.get(r['домен']) or [])
            r['by'] = by
            if by:
                итог = 'УНП со страницы' if r['унп'] else ('юрназвание' if r['юр'] else ('нет страниц' if not r['страниц'] else 'ничего'))
            elif len(свои) == 1:
                итог = 'ИНН со страницы: один'
            elif len(свои) > 1:
                итог = 'ИНН со страницы: несколько'
            elif r['огрн']:
                итог = 'только ОГРН'
            elif r['база_инн']:
                итог = 'домен в базе обзвона'
            elif r['юр'] or r['ип']:
                итог = 'только юрназвание'
            elif not r['страниц']:
                итог = 'нет страниц'
            else:
                итог = 'ничего'
            r['итог'] = итог
            сч[итог] += 1
            if not by:
                сч['доп: домен в базе обзвона (любой итог)'] += bool(r['база_инн'])
                сч['доп: ИНН уже в списке (дубль)'] += any(v in в_списке for v in свои + r['база_инн'])
                сч['доп: юрназвание есть (любой итог)'] += bool(r['юр'] or r['ип'])
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(ВЫХОД + '.tmp', ВЫХОД)
    print('ИНН на 3+ доменах (студии/платформы):', len(частые), sorted(частые)[:10], flush=True)
    print('===ИТОГ ЗАМЕРА===', json.dumps({'компаний': len(рез), 'итоги': dict(сч.most_common()),
                                          'минут': round((time.time() - t0) / 60, 1)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    sys.path.insert(0, DIR)
    os.chdir(DIR)
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'inn_zamer_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                                 stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
        time.sleep(25)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                         ensure_ascii=False))
        sys.exit(0)
    main()
