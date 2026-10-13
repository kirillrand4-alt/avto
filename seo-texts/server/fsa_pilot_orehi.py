# -*- coding: utf-8 -*-
# 13.10, владелец: «смотреть продукты, которые поставляются в торговые сети, и искать их производителей и контакты» → проба
# по реестру деклараций ФСА (pub.fsa.gov.ru, открытый API сайта) на отрасли «орехи и сухофрукты». Декларации по ключевым
# словам продукции (последние до 1000 на слово), изготовитель — юрлицо/ИП РФ (ИНН) или Беларуси; контакты (телефон/почта из
# карточки) — только где заявитель = изготовитель (иначе это посредник/импортёр). Сверка: в нашем списке meyer7 (раздел), в
# базе обзвона, активная сделка Meyer. Итог — fsa-orehi.jsonl (fsync, резюм по декларациям) + FSA-OREHI.xlsx на дроп.
# Лог: fsa_orehi_*.log.
import collections, io, json, os, re, ssl, sqlite3, sys, time, urllib.request
DIR = r'C:\sender\server'
ВЫХ = os.path.join(DIR, 'fsa-orehi.jsonl')
СЛОВА = ['орех', 'миндаль', 'фундук', 'кешью', 'арахис', 'фисташ', 'изюм', 'курага', 'чернослив', 'финик', 'сухофрукт', 'цукат',
         'семечк', 'ядро подсолнечн', 'кедров', 'грецк', 'финиковая паста', 'ореховая паста', 'урбеч']
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
H = {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json', 'Accept': 'application/json'}


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def вход():
    r = OP.open(urllib.request.Request('https://pub.fsa.gov.ru/login', data=json.dumps({'username': 'anonymous', 'password': 'hrgesf7HDR67Bd'}).encode(),
                                       headers=H), timeout=40)
    return dict(H, Authorization=r.headers.get('Authorization'))


def запрос(H2, путь, тело=None):
    for попытка in range(4):
        try:
            req = urllib.request.Request('https://pub.fsa.gov.ru' + путь, data=json.dumps(тело).encode() if тело is not None else None, headers=H2)
            return json.loads(OP.open(req, timeout=60).read())
        except Exception as e:  # noqa: BLE001
            if попытка == 3:
                п('сбой', путь[:60], repr(e)[:100])
                return None
            time.sleep(3 * (попытка + 1))


def main():
    t0 = time.time()
    H2 = вход()
    декл = {}
    if os.path.exists(ВЫХ):
        for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(s)
                декл[x['id']] = x
            except (ValueError, KeyError):
                pass
    # 1) декларации по словам
    for сл in СЛОВА:
        n = 0
        for стр in range(10):
            d = запрос(H2, '/api/v1/rds/common/declarations/get', {'size': 100, 'page': стр, 'filter': {'columnsSearch': [
                {'name': 'productFullName', 'search': сл, 'type': 1, 'translated': False}]}, 'columnsSort': [{'column': 'declDate', 'sort': 'DESC'}]})
            it = (d or {}).get('items') or []
            for x in it:
                if x['id'] in декл:
                    continue
                y = {k: x.get(k) for k in ('id', 'declNumber', 'declDate', 'declEndDate', 'idStatus', 'applicantType', 'applicantInn', 'applicantName',
                                           'manufacterInn', 'manufacterName', 'manufacterOgrn', 'manufacterAddress', 'manufacterType',
                                           'productFullName', 'productOrig', 'productIdentificationTrademark')}
                y['слово'] = сл
                декл[x['id']] = y
                with io.open(ВЫХ, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(y, ensure_ascii=False) + '\n')
                n += 1
            if len(it) < 100:
                break
            time.sleep(0.5)
        п('слово', сл, 'новых деклараций', n, '| всего', len(декл))
    # 2) изготовители РФ/РБ
    изг = {}
    for x in декл.values():
        инн = re.sub(r'\D', '', x.get('manufacterInn') or '')
        адр = x.get('manufacterAddress') or ''
        by = 'беларус' in адр.lower()
        if not (len(инн) in (10, 12) or by):
            continue
        кл = инн or ('BY:' + (x.get('manufacterName') or '')[:60])
        z = изг.setdefault(кл, {'инн': инн, 'имя': x.get('manufacterName'), 'огрн': x.get('manufacterOgrn'), 'адрес': адр[:200], 'by': by,
                                'деклараций': 0, 'продукция': [], 'последняя': '', 'марки': set(), 'сам_заявитель': [], 'слова': set()})
        z['деклараций'] += 1
        z['слова'].add(x['слово'])
        if len(z['продукция']) < 5 and (x.get('productFullName') or '')[:120] not in z['продукция']:
            z['продукция'].append((x.get('productFullName') or '')[:120])
        z['последняя'] = max(z['последняя'], x.get('declDate') or '')
        if x.get('productIdentificationTrademark'):
            z['марки'].add(str(x['productIdentificationTrademark'])[:40])
        if инн and re.sub(r'\D', '', x.get('applicantInn') or '') == инн:
            z['сам_заявитель'].append(x['id'])
    п('изготовителей РФ/РБ', len(изг), '| из них сами заявители', sum(1 for z in изг.values() if z['сам_заявитель']))
    # 3) контакты из карточки (последняя декларация, где заявитель = изготовитель)
    КЭШ_К = os.path.join(DIR, 'fsa-orehi-kontakty.jsonl')
    конт = {}
    if os.path.exists(КЭШ_К):
        for s in io.open(КЭШ_К, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(s)
                конт[x['кл']] = x
            except (ValueError, KeyError):
                pass
    for кл, z in изг.items():
        if кл in конт or not z['сам_заявитель']:
            continue
        ид = sorted(z['сам_заявитель'], key=lambda i: декл[i].get('declDate') or '')[-1]
        d = запрос(H2, '/api/v1/rds/common/declarations/%s' % ид)
        т = json.dumps(d or {}, ensure_ascii=False)
        почты = sorted(set(m.lower() for m in re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', т)))
        тел = sorted(set(re.sub(r'[^\d+]', '', m) for m in re.findall(r'"value"\s*:\s*"(\+?[78][\d\s()\-]{9,18})"', т)))
        x = {'кл': кл, 'id': ид, 'почты': почты[:5], 'телефоны': тел[:5]}
        конт[кл] = x
        with io.open(КЭШ_К, 'a', encoding='utf-8') as f:
            f.write(json.dumps(x, ensure_ascii=False) + '\n')
        time.sleep(0.4)
    # 4) сверка с нашей базой
    сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))
    раздел = {}
    for р in ('компании', 'снято', 'ниже_порога', 'на_решение', 'ждут_оквэд'):
        for i in (сп.get(р) or {}):
            раздел.setdefault(i, р)
    найд = {}
    for s in io.open(os.path.join(DIR, 'meyer7-inn-sayt.jsonl'), encoding='utf-8'):
        x = json.loads(s)
        найд.setdefault(x['инн'], x['ключ'])
    сд = {}
    for s in io.open(r'C:\seostat\drop\drop-storage\meyer7-sdelki-aktivnye.tsv', encoding='utf-8').read().splitlines()[1:]:
        ч = s.split('\t')
        if ч and ч[0].isdigit():
            сд[ч[0]] = ч[1] if len(ч) > 1 else ''
    обз = {}
    c = sqlite3.connect(r'file:C:\sender\obzvon-index.db?mode=ro', uri=True, timeout=120)
    нужны = {z['инн'] for z in изг.values() if z['инн']}
    for i, выр, тел, почт, сайт, окв in c.execute('select inn, revenue_rub, phones_base, emails_base, sites, okved_main from obzvon'):
        if str(i) in нужны:
            обз[str(i)] = (выр or 0, тел or '', почт or '', сайт or '', окв or '')
    c.close()
    строки = []
    for кл, z in изг.items():
        i = z['инн']
        в_сп = раздел.get(i) or (('компании (ИНН найден по сайту)' if i in найд else '') if i else '')
        о = обз.get(i, (0, '', '', '', ''))
        к = конт.get(кл, {})
        строки.append({'Изготовитель': z['имя'], 'ИНН': i or '', 'Страна': 'Беларусь' if z['by'] else 'Россия', 'Адрес': z['адрес'],
                       'Деклараций': z['деклараций'], 'Последняя декларация': z['последняя'], 'Продукция (примеры)': ' | '.join(z['продукция']),
                       'Торговые марки': ', '.join(sorted(z['марки']))[:150], 'Ключевые слова': ', '.join(sorted(z['слова'])),
                       'В нашем списке meyer7': в_сп or 'нет', 'Активная сделка Meyer': сд.get(i, '')[:150],
                       'В базе обзвона': 'да' if i in обз else 'нет', 'Выручка (база)': int(о[0]) if о[0] else '', 'ОКВЭД (база)': о[4],
                       'Сайт (база)': о[3][:80], 'Телефоны (база)': о[1][:120], 'Почты (база)': о[2][:150],
                       'Заявитель = изготовитель': 'да' if z['сам_заявитель'] else 'нет (посредник/импортёр)',
                       'Почты из декларации': ', '.join(к.get('почты') or []), 'Телефоны из декларации': ', '.join(к.get('телефоны') or []),
                       'Ссылка на декларацию': ('https://pub.fsa.gov.ru/rds/declaration/view/%s/common' % к['id']) if к.get('id') else ''})
    строки.sort(key=lambda r: (r['В нашем списке meyer7'] != 'нет', -r['Деклараций']))
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    w = wb.active
    w.title = 'Изготовители'
    кк = list(строки[0]) if строки else ['Изготовитель']
    w.append(кк)
    for r in строки:
        w.append([r[k] for k in кк])
    for cl in w[1]:
        cl.font = Font(bold=True)
        cl.fill = PatternFill('solid', fgColor='DDEBF7')
    w.freeze_panes = 'B2'
    вых_x = os.path.join(DIR, 'FSA-OREHI.xlsx')
    wb.save(вых_x)
    import shutil
    shutil.copyfile(вых_x, r'C:\seostat\drop\drop-storage\FSA-OREHI.xlsx')
    сч = collections.Counter()
    for r in строки:
        сч['изготовителей'] += 1
        сч['новых (нет в списке)'] += r['В нашем списке meyer7'] == 'нет'
        сч['новых с контактами из декларации'] += r['В нашем списке meyer7'] == 'нет' and bool(r['Почты из декларации'] or r['Телефоны из декларации'])
        сч['новых, есть в базе обзвона'] += r['В нашем списке meyer7'] == 'нет' and r['В базе обзвона'] == 'да'
        сч['с активной сделкой Meyer'] += bool(r['Активная сделка Meyer'])
        сч['сами заявители'] += r['Заявитель = изготовитель'] == 'да'
    п('===ИТОГ FSA===', json.dumps(dict(сч), ensure_ascii=False), '| деклараций', len(декл), '| за %.1f мин' % ((time.time() - t0) / 60))


if __name__ == '__main__':
    sys.path.insert(0, DIR)
    os.chdir(DIR)
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'fsa_orehi_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'fsa_pilot_orehi.py'), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                                 stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
        time.sleep(20)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-500:]},
                         ensure_ascii=False))
        sys.exit(0)
    main()
