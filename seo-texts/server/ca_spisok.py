# -*- coding: utf-8 -*-
r"""Шаг 3 плана PLAN_CA_O2_N2.md: список компаний ЦА O2/N2 для ночного конвейера контактов (набор «ca»).

09.11, владелец: «ночью не забудь выполнить задачу по полному поиску контактов под азот и кислород».
Вход: ca\ca-reestr.jsonl (замер ca_fns_reestr: МСП + не-МСП) и ca\ca-ne-msp-kat.jsonl (добор ca_okved_dobor).
Категории пересчитываются текущим ca_cel (правки 09.11). В список (ca-spisok.json, формат poisk_otbor):
  * только ЮЛ (ИП — отдельным решением: без выручки и сайтов), основной ОКВЭД в категории статуса «ядро» / «новая» /
    «по нашим сделкам», выручка не ниже порога категории;
  * n2_lazer пока НЕ берём: 13,5 тыс. компаний, без признака азота (тендеры, сайт) это обход наугад — после шага 2;
  * снимаем (лист «снято» с причиной): активная сделка КЦ (решение 13: активные не трогать; проваленные КЦ, СЦ и Meyer
    берём), запреты панели, ГУП/МУП/учреждения, ликвидированные/банкроты, конкуренты из нашей базы.
Сайт: наши базы (enrich.companies, обзвон), затем сайт из добора; нет — поиск xmlriver по названию и региону
(не больше CA_POISK_SAYTA). Чей сайт — проверяют шаги конвейера (kc_audit, kc_sayt_proverka).
Выход: C:\sender\server\ca-spisok.json (+ дроп). Только чтение баз.
"""
import collections, io, json, os, re, sqlite3, sys, threading, time

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'
sys.path.insert(0, DIR)
os.chdir(DIR)
import ca_cel  # noqa: E402
import enrich_contacts as EC  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

ВЫХОД = os.path.join(DIR, 'ca-spisok.json')
БРАТЬ = ('ядро', 'новая', 'по нашим сделкам')
ПОКА_НЕ = {'n2_lazer'}
ЛИМИТ_ПОИСКА = int(os.environ.get('CA_POISK_SAYTA', '4000'))
ГОС = re.compile(r'\b(ГУП|МУП|ФГУП|ФГБУ|ФКП|ГБУ|МБУ|ГКУ|МКУ|ФГБОУ|ГАУ|МАУ|ГОСУДАРСТВЕНН\w* (?:УНИТАРН|БЮДЖЕТН|КАЗЕНН)|'
                 r'МУНИЦИПАЛЬН\w* (?:УНИТАРН|БЮДЖЕТН|КАЗЕНН|АВТОНОМН))', re.I)
ЗАКУПКИ = re.compile(r'zakupki\.gov|b2b-center|fabrikant|tektorg|sberbank-ast|rts-tender|otc\.ru|roseltorg', re.I)


def коды(*сс):
    out = []
    for s in сс:
        for к in (s if isinstance(s, list) else re.findall(r'\d{2}(?:\.\d{1,2}){0,2}', str(s or ''))):
            if к and к not in out:
                out.append(str(к))
    return out


def main():
    t0 = time.time()
    # ---------- кандидаты ----------
    канд = {}
    for имя in ('ca-reestr.jsonl', 'ca-ne-msp-kat.jsonl'):
        п = os.path.join(ПАПКА, имя)
        if not os.path.exists(п):
            continue
        for s in io.open(п, encoding='utf-8', errors='replace'):
            try:
                r = json.loads(s)
            except ValueError:
                continue
            инн = str(r.get('инн') or '')
            if r.get('тип') != 'ЮЛ' or len(инн) != 10:
                continue
            кат = ca_cel.категории(r.get('оквэд'), r.get('оквэд_доп') or [])
            v = float(r.get('доход') or 0)
            годные = {к: о for к, о in кат.items() if о == 'осн' and ca_cel.КАТ[к][1] in БРАТЬ and к not in ПОКА_НЕ
                      and v >= ca_cel.порог(к)}
            if годные:
                канд[инн] = {'r': r, 'кат': кат, 'годные': годные, 'доход': v}
    print('кандидатов', len(канд), flush=True)
    # ---------- сделки ----------
    сделки = json.load(io.open(os.path.join(ДРОП, 'sdelki-vse-1410.json'), encoding='utf-8'))
    # ---------- запреты панели ----------
    зап = {}
    try:
        c = sqlite3.connect(r'file:C:\sender\sender.db?mode=ro', uri=True, timeout=60)
        т = [r[0] for r in c.execute("select name from sqlite_master where type='table' and name like '%suppress%'")][0]
        кк = [r[1] for r in c.execute('pragma table_info(%s)' % т)]
        for r in c.execute("select * from %s where scope='inn'" % т):
            x = dict(zip(кк, r))
            зап[str(x['value'])] = '%s (панель)' % (x.get('reason') or 'запрет')
        c.close()
    except Exception as e:  # noqa: BLE001
        print('запреты панели не прочитаны:', repr(e)[:200], flush=True)
    # ---------- наши данные: имя, регион, сайт, статус, конкурент ----------
    наши = {}
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
    c.execute('create temp table t(inn text primary key)')
    c.executemany('insert or ignore into t values (?)', [(i,) for i in канд])
    for i, имя, рег, сайт, стат, конк, база in c.execute(
            "select t.inn, coalesce(nullif(c.name,''), o.name_short, ''), coalesce(nullif(c.region,''), o.region, ''), "
            "coalesce(nullif(c.site,''), o.sites, ''), coalesce(nullif(c.status_egrul,''), o.status, ''), "
            "coalesce(c.is_competitor,0), coalesce(o.base_label,'') "
            'from t left join companies c on c.inn=t.inn left join obz.obzvon o on o.inn=t.inn'):
        наши[i] = {'имя': имя or '', 'регион': рег or '', 'сайт': (re.split(r'[\s,;|]+', (сайт or '').strip()) or [''])[0],
                   'статус': стат or '', 'конкурент': конк, 'база': база}
    # страницы-источники наших контактов (свой домен и закупки) — как в poisk_otbor
    стр = collections.defaultdict(list)
    for i, url in c.execute("select inn, source_url from people where inn in (select inn from t) and coalesce(source_url,'')<>'' "
                            "union select inn, source_url from phone_contacts where inn in (select inn from t) "
                            "and coalesce(source_url,'')<>''"):
        стр[str(i)].append(url)
    c.close()
    сайт_добора = {}
    п = os.path.join(ПАПКА, 'ca-okved-dobor.jsonl')
    if os.path.exists(п):
        for s in io.open(п, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
            except ValueError:
                continue
            if з.get('сайт') and з.get('inn') in канд:
                сайт_добора[з['inn']] = з['сайт']
            if з.get('статус') and з.get('inn') in канд:
                наши.setdefault(з['inn'], {}).setdefault('статус', з['статус'])
    # ---------- отбор ----------
    итог, снято = {}, {}
    for i, x in канд.items():
        r, о = x['r'], наши.get(i) or {}
        имя = о.get('имя') or r.get('название') or ''
        запись = {'inn': i, 'имя': имя, 'регион': о.get('регион') or r.get('регион') or '',
                  'сайт': о.get('сайт') or сайт_добора.get(i, ''), 'осн': r.get('оквэд') or '',
                  'все': коды([r.get('оквэд') or ''], r.get('оквэд_доп') or []),
                  'сегм': ', '.join(sorted(x['годные'])), 'сегм_как': 'осн', 'кат_все': x['кат'],
                  'выручка': x['доход'], 'выручка_откуда': 'ФНС (доход 2025)', 'мсп': r.get('мсп') or '',
                  'ссч': r.get('ссч') or '', 'откуда': 'реестр ФНС + ca_cel', 'в_нашей_базе': о.get('база') or 'нет',
                  'огрн': ''}
        if запись['сайт'] and not о.get('сайт'):
            запись['сайт_откуда'] = 'добор ОКВЭД (checko/dadata)'
        сд = сделки.get(i) or []
        if any(d[0] == 'kc' and d[1] == 'В работе' for d in сд):
            снято[i] = dict(запись, причина='активная сделка КЦ')
            continue
        if i in зап:
            снято[i] = dict(запись, причина=зап[i])
            continue
        if ГОС.search(имя):
            снято[i] = dict(запись, причина='гос/муниципальное')
            continue
        if re.search(r'LIQUIDAT|BANKRUPT|ликвид|банкрот', о.get('статус') or '', re.I):
            снято[i] = dict(запись, причина='ликвидирована/банкрот (%s)' % о.get('статус'))
            continue
        if о.get('конкурент'):
            снято[i] = dict(запись, причина='конкурент (наша база)')
            continue
        if сд:
            запись['сделки'] = sorted({'%s: %s' % (d[0], d[1]) for d in сд})
        for url in стр.get(i, []):
            if ЗАКУПКИ.search(url):
                запись.setdefault('закупки_базы', []).append(url)
            elif запись['сайт'] and MN.домен(url) == MN.домен(запись['сайт']):
                запись.setdefault('страницы_базы', []).append(url)
        итог[i] = запись
    print('в список', len(итог), 'снято', len(снято), 'без сайта', sum(1 for к in итог.values() if not к['сайт']), flush=True)
    # ---------- сайт для тех, у кого его нет: xmlriver (чей сайт проверят шаги конвейера) ----------
    без = sorted((к for к in итог.values() if not к['сайт']), key=lambda к: -к['выручка'])[:ЛИМИТ_ПОИСКА]
    сч = collections.Counter()

    def найти(к):
        try:
            рег = re.sub(r'\b(обл|область|край|респ|республика|г)\b\.?', ' ', к['регион'] if not к['регион'].isdigit() else '').strip()
            сайт, ист, _ = EC.find_site_via_xmlriver({'name': к['имя'], 'city': рег})
            if сайт:
                к['сайт'], к['сайт_откуда'] = сайт, 'поиск по названию (%s)' % ист
                сч['найден'] += 1
            else:
                сч['не найден'] += 1
        except Exception:  # noqa: BLE001
            сч['ошибка'] += 1
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(найти, без))
    print('поиск сайта', len(без), dict(сч), flush=True)
    for имя_, данные in ((ВЫХОД, {'компании': итог, 'снято': снято, 'дата': time.strftime('%Y-%m-%d %H:%M'),
                                  'поиск_сайта': dict(сч)}),):
        with io.open(имя_ + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(данные, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(имя_ + '.tmp', имя_)
    import shutil
    shutil.copyfile(ВЫХОД, os.path.join(ДРОП, 'ca-spisok.json'))
    по_кат = collections.Counter(к for x in итог.values() for к in x['сегм'].split(', '))
    print('готово за %d мин' % ((time.time() - t0) / 60), json.dumps({'компаний': len(итог), 'снято': len(снято),
          'по_категориям': dict(по_кат), 'причины_снятия': dict(collections.Counter(x['причина'] for x in снято.values())),
          'с_сайтом': sum(1 for к in итог.values() if к['сайт'])}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
