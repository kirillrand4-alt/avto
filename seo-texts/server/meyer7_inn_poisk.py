# -*- coding: utf-8 -*-
# 13.10, владелец: «запускай» (этапы 1–3 поиска ИНН для компаний «по сайту», ключ САЙТ:<домен>). Вход — замер
# meyer7-inn-zamer2.jsonl (_inn_zamer2_meyer7.py): ИНН/ОГРН/юрназвания со страниц сайта, совпадение домена с базой.
#   1) кандидаты: ИНН со страницы, ОГРН → DaData findById, ИНН из базы обзвона (сайт/почта компании), юрназвания с сайта
#      (кроме «частых» — банки, Яндекс, студии: одно имя на 3+ доменах) → DaData suggest/party (только действующие);
#   2) решение без модели: ровно один ИНН со страницы, действующий, и его название совпадает с юрназванием на сайте (или
#      с ИНН из базы); ровно один ОГРН со страницы, действующий; Беларусь — ровно один УНП со страницы;
#   3) остальное — модель (пачки по 8): какой кандидат владеет сайтом; берём только уверенность «высокая/средняя».
# Базу НЕ меняет: итог — meyer7-inn-poisk.jsonl (по компании, fsync, резюм), кэш DaData — meyer7-inn-dadata.jsonl.
# Лимит DaData (403/429) — стоп запросов, такие компании остаются «ждёт DaData» до следующего запуска.
# Лог: inn_poisk_*.log.
import collections, io, json, os, re, sys, threading, time, urllib.error, urllib.request
DIR = r'C:\sender\server'
ВЫХОД = os.path.join(DIR, 'meyer7-inn-poisk.jsonl')
КЭШ_DD = os.path.join(DIR, 'meyer7-inn-dadata.jsonl')
ПАЧКА = 8
_лок = threading.Lock()


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def писать(путь, r):
    with _лок:
        with io.open(путь, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


ОПФ = re.compile(r'\b(общество с ограниченной ответственностью|акционерное общество|публичное акционерное общество|'
                 r'закрытое акционерное общество|открытое акционерное общество|индивидуальный предприниматель|ооо|оао|зао|пао|'
                 r'ао|ип|сооо|чуп|чтуп|одо|нпп|нпо|пк|тд|фирма|компания|завод|группа)\b')


def ядро(s):
    s = (s or '').lower().replace('ё', 'е')
    s = re.sub(r'[«»"“”„\'.,()\-–]', ' ', s)
    s = ОПФ.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def кандидат(x):
    d = x.get('data') or {}
    адр = (d.get('address') or {}).get('data') or {}
    return {'инн': d.get('inn') or '', 'огрн': d.get('ogrn') or '', 'имя': (d.get('name') or {}).get('short_with_opf') or x.get('value') or '',
            'имя_полное': (d.get('name') or {}).get('full_with_opf') or '', 'статус': (d.get('state') or {}).get('status') or '',
            'регион': адр.get('region_with_type') or '', 'город': адр.get('city') or адр.get('settlement') or '',
            'оквэд': d.get('okved') or '', 'тип': d.get('type') or '',
            'руководитель': ((d.get('management') or {}).get('name') or ''), 'должность': ((d.get('management') or {}).get('post') or '')}


class DaData:
    def __init__(self):
        import enrich_contacts as EC
        self.tok = EC._read_secret('DADATA_TOKEN')
        self.прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.кэш = {}
        self.лимит = False
        self.запросов = 0
        if os.path.exists(КЭШ_DD):
            for s in io.open(КЭШ_DD, encoding='utf-8', errors='replace'):
                try:
                    x = json.loads(s)
                    self.кэш[(x['тип'], x['q'])] = x['ответ']
                except (ValueError, KeyError):
                    pass

    def _зап(self, путь, тело):
        for попытка in range(3):
            try:
                req = urllib.request.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/' + путь,
                                             data=json.dumps(тело).encode(), method='POST',
                                             headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                                      'Authorization': 'Token ' + self.tok})
                return json.loads(self.прямой.open(req, timeout=40).read()).get('suggestions') or []
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    self.лимит = True
                    return None
                time.sleep(2 * (попытка + 1))
            except Exception:  # noqa: BLE001
                time.sleep(2 * (попытка + 1))
        return None

    def найти(self, тип, q):
        if (тип, q) in self.кэш:
            return self.кэш[(тип, q)]
        if self.лимит:
            return None
        if тип == 'id':
            с = self._зап('findById/party', {'query': q, 'count': 3})
        else:
            с = self._зап('suggest/party', {'query': q, 'count': 7, 'status': ['ACTIVE']})
        if с is None:
            return None
        ответ = [кандидат(x) for x in с]
        with _лок:
            self.запросов += 1
            self.кэш[(тип, q)] = ответ
        писать(КЭШ_DD, {'тип': тип, 'q': q, 'ответ': ответ})
        return ответ


ПРОМПТ = (
    'Ты определяешь, какое юрлицо (из ЕГРЮЛ) — ВЛАДЕЛЕЦ сайта. Для каждого сайта даны: домен, название с сайта, юрназвания и '
    'ИНН, найденные на страницах сайта (реквизиты/подвал/политика/контакты), куски текста страниц и КАНДИДАТЫ из ЕГРЮЛ '
    '(название, ИНН, регион, ОКВЭД, откуда взят).\n'
    'Выбери кандидата, которому принадлежит сайт: производитель/предприятие, его торговый дом или управляющая компания, '
    'указанные в реквизитах как оператор сайта. НЕ выбирай: банк, платёжный сервис, разработчика/хостинг сайта, '
    'клиента, партнёра, поставщика, упомянутую в новостях или отзывах компанию, маркетплейс, однофамильца/тёзку из '
    'другого региона без связи с сайтом. Название бренда/домена, совпадающее с юрназванием кандидата, — сильная улика; '
    'регион кандидата должен не противоречить сайту. Если уверенно выбрать нельзя — «выбор»: 0.\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер сайта,"выбор":номер кандидата или 0,"уверенность":"высокая|средняя|низкая",'
    '"почему":"до 15 слов"}}]\n\n{сайты}')


def main():
    t0 = time.time()
    import pilot_konveyer as PK
    os.environ.update(PK.Волны().env_шага('kc_kontakty.py'))
    import kc_kontakty as KK
    import _inn_zamer_meyer7 as Z  # страницы (кэш + папки Зенки), окна вокруг юрназваний/ИНН
    з = [json.loads(s) for s in io.open(os.path.join(DIR, 'meyer7-inn-zamer2.jsonl'), encoding='utf-8') if s.strip()]
    сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))['компании']
    в_списке = {i for i in сп if i.isdigit()}
    готово = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                r = json.loads(s)
            except ValueError:
                continue
            if r.get('итог') not in ('ждёт DaData', 'модель без ответа'):
                готово.add(r['ключ'])
    дом_имя = collections.defaultdict(set)
    for r in з:
        for ю in list(r['юр']) + list(r['ип']):
            дом_имя[ю.upper()].add(r['домен'])
    частые = {ю for ю, д in дом_имя.items() if len(д) >= 3}
    задачи = [r for r in з if r['ключ'] not in готово]
    п('компаний', len(з), 'уже решено', len(готово), 'к работе', len(задачи), '| частых юрназваний', len(частые))
    dd = DaData()

    def запросы(r):
        """[(тип, q, откуда)] — что спросить у DaData."""
        q = []
        for v in [v for v in r['инн'] if v not in (r.get('инн_частые') or [])][:4]:
            q.append(('id', v, 'ИНН со страницы'))
        for v in list(r['огрн'])[:2]:
            q.append(('id', v, 'ОГРН со страницы'))
        for v in (r.get('база_сильн') or [])[:3]:
            q.append(('id', v, 'база обзвона (сайт/почта)'))
        имена = [ю for ю in list(r['юр']) + list(r['ип']) if ю.upper() not in частые]
        for ю in имена[:4]:
            if ю.startswith('ИП ') and '.' in ю:
                continue  # ИП с инициалами — DaData не найдёт однозначно
            q.append(('имя', ю, 'юрназвание с сайта'))
        return q

    решения = {}
    к_модели = []
    by_дом = lambda r: r['домен'].endswith('.by') or (сп.get(r['ключ']) or {}).get('регион') == 'Беларусь'  # noqa: E731

    def собрать(r):
        if by_дом(r):
            унп = list(r.get('унп') or {})
            if len(унп) == 1:
                return {'итог': 'принят', 'ключ_новый': 'BY' + унп[0], 'как': 'УНП со страницы', 'уверенность': 'высокая'}
            return {'итог': 'Беларусь: УНП нет' if not унп else 'Беларусь: несколько УНП', 'унп': унп}
        канд, нет_ответа = {}, False
        for тип, q, откуда in запросы(r):
            ответ = dd.найти('id' if тип == 'id' else 'suggest', q)
            if ответ is None:
                нет_ответа = True
                continue
            for к in ответ:
                if not к['инн']:
                    continue
                if тип == 'id' and к['инн'] != q and к['огрн'] != q:
                    continue
                x = канд.setdefault(к['инн'], dict(к, откуда=[]))
                if откуда not in x['откуда']:
                    x['откуда'].append(откуда + ('' if тип == 'id' else ': ' + q))
        if нет_ответа and not канд:
            return {'итог': 'ждёт DaData'}
        живые = {i: к for i, к in канд.items() if к['статус'] == 'ACTIVE'}
        ядра_сайта = {ядро(ю) for ю in list(r['юр']) + list(r['ип']) if ю.upper() not in частые} - {''}
        со_стр = [i for i in живые if any(о.startswith('ИНН со страницы') for о in живые[i]['откуда'])]
        if len(со_стр) == 1:
            к = живые[со_стр[0]]
            if ядро(к['имя']) in ядра_сайта or any(о.startswith('база') for о in к['откуда']):
                return {'итог': 'принят', 'инн': к['инн'], 'как': 'ИНН со страницы + совпало юрназвание/база', 'уверенность': 'высокая',
                        'кандидат': к}
        огрн_ = [i for i in живые if any(о.startswith('ОГРН со страницы') for о in живые[i]['откуда'])]
        if len(огрн_) == 1 and not со_стр:
            к = живые[огрн_[0]]
            return {'итог': 'принят', 'инн': к['инн'], 'как': 'ОГРН со страницы', 'уверенность': 'высокая', 'кандидат': к}
        if not живые:
            мёртв = [к for к in канд.values() if к['статус'] and к['статус'] != 'ACTIVE']
            return {'итог': 'кандидатов нет' if not мёртв else 'только недействующие', 'кандидаты': мёртв[:3]}
        # к модели — до 8 кандидатов: сначала со страницы/ОГРН/базы, потом по имени (совпадение ядра — выше)
        порядок = sorted(живые.values(), key=lambda к: (not any(о.startswith(('ИНН', 'ОГРН', 'база')) for о in к['откуда']),
                                                         ядро(к['имя']) not in ядра_сайта))
        return {'итог': 'к модели', 'кандидаты': порядок[:8]}

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as ex:
        for n, (r, р) in enumerate(zip(задачи, ex.map(собрать, задачи)), 1):
            if р['итог'] == 'к модели':
                к_модели.append((r, р['кандидаты']))
            else:
                решения[r['ключ']] = р
                писать(ВЫХОД, dict(р, ключ=r['ключ'], домен=r['домен'], ts=time.strftime('%Y-%m-%d %H:%M')))
            if n % 500 == 0:
                п('DaData: компаний', n, 'из', len(задачи), '| запросов', dd.запросов, '| лимит' if dd.лимит else '')
    п('DaData готово: запросов', dd.запросов, 'лимит' if dd.лимит else 'без лимита', '| решено без модели',
      collections.Counter(р['итог'] for р in решения.values()).most_common(), '| к модели', len(к_модели))

    # модель: куски страниц вокруг юрназваний/ИНН (для понимания, чьё это)
    карта_сур = json.load(io.open(os.path.join(DIR, 'meyer7-zenno-surrogat.json'), encoding='utf-8'))
    сур = collections.defaultdict(list)
    for кл, i in карта_сур.items():
        сур[i].append(кл)
    ключи = {r['ключ'] for r, _ in к_модели} | {к for r, _ in к_модели for к in сур.get(r['ключ'], [])}
    файлы = collections.defaultdict(list)
    for пап in Z.ZENNO:
        if os.path.isdir(пап):
            for e in os.scandir(пап):
                if e.name.endswith('.html'):
                    k, _, n_ = e.name[:-5].rpartition('_')
                    if k in ключи and n_.isdigit():
                        файлы[k].append((e.path, int(n_), пап))

    def куски(r):
        стр = []
        for k in [r['ключ']] + сур.get(r['ключ'], []):
            стр += Z.страницы_кэша(k) + Z.страницы_зенки(k, файлы.get(k) or [])
        ищем = [ю.split('«')[-1].rstrip('»')[:25] for ю in list(r['юр'])[:4]] + list(r['инн'])[:3] + list(r['огрн'])[:2]
        заголовок, out, были = '', [], set()
        for x in стр:
            h = x.get('html') or ''
            if not заголовок:
                м = re.search(r'<title[^>]*>(.*?)</title>', h, re.S | re.I)
                заголовок = Z.чистый(м.group(1))[:120] if м else ''
            for кус in Z.окна(h):
                т = Z.чистый(кус).strip()
                if any(и and и in т for и in ищем) and т[:60] not in были:
                    были.add(т[:60])
                    out.append(т[:260])
                if len(out) >= 4:
                    return заголовок, out
        return заголовок, out

    def пачка(п_):
        блоки = []
        for j, (r, канд) in enumerate(п_, 1):
            заг, кус = куски(r)
            кк = '\n'.join('   %d) %s | ИНН %s | %s %s | ОКВЭД %s | откуда: %s' % (k, к['имя'], к['инн'], к['регион'], к['город'], к['оквэд'],
                                                                             '; '.join(к['откуда'])[:150])
                          for k, к in enumerate(канд, 1))
            блоки.append('%d. Сайт %s | название в списке: %s | заголовок: %s\n Юрназвания на сайте: %s | ИНН на сайте: %s | ОГРН: %s\n'
                         ' Куски страниц:\n%s\n Кандидаты:\n%s' % (
                             j, r['домен'], (сп.get(r['ключ']) or {}).get('имя', ''), заг, '; '.join(list(r['юр'])[:5] + list(r['ип'])[:2]) or '-',
                             ', '.join(r['инн']) or '-', ', '.join(r['огрн']) or '-', '\n'.join('   - ' + x for x in кус) or '   -', кк))
        ответ = KK.модель(ПРОМПТ.format(сайты='\n\n'.join(блоки)), True) or {}
        for j, (r, канд) in enumerate(п_, 1):
            x = ответ.get(j) or {}
            try:
                в = int(x.get('выбор') or 0)
            except (TypeError, ValueError):
                в = 0
            ув = x.get('уверенность') or ''
            if not x:
                р = {'итог': 'модель без ответа'}
            elif 1 <= в <= len(канд) and ув in ('высокая', 'средняя'):
                к = канд[в - 1]
                р = {'итог': 'принят', 'инн': к['инн'], 'как': 'модель: ' + '; '.join(к['откуда'])[:120], 'уверенность': ув, 'кандидат': к,
                     'почему': x.get('почему') or ''}
            else:
                р = {'итог': 'модель: не определить' if not в else 'модель: низкая уверенность', 'почему': x.get('почему') or '',
                     'кандидаты': [{'инн': к['инн'], 'имя': к['имя']} for к in канд[:4]]}
            писать(ВЫХОД, dict(р, ключ=r['ключ'], домен=r['домен'], ts=time.strftime('%Y-%m-%d %H:%M')))
            решения[r['ключ']] = р

    пачки = [к_модели[k:k + ПАЧКА] for k in range(0, len(к_модели), ПАЧКА)]
    п('к модели пачек', len(пачки))
    with ThreadPoolExecutor(8) as ex:
        for n, _ in enumerate(ex.map(пачка, пачки), 1):
            if n % 25 == 0:
                п('модель: пачек', n, 'из', len(пачки))
    # сводка по всему файлу (последняя запись на ключ)
    посл = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            r = json.loads(s)
            посл[r['ключ']] = r
        except (ValueError, KeyError):
            pass
    сч = collections.Counter(r['итог'] for r in посл.values())
    как = collections.Counter(r.get('как', '').split(':')[0] for r in посл.values() if r['итог'] == 'принят')
    дубли = sum(1 for r in посл.values() if r['итог'] == 'принят' and r.get('инн') in в_списке)
    п('===ИТОГ ПОИСКА ИНН===', json.dumps({'компаний': len(посл), 'итоги': dict(сч.most_common()), 'принят_как': dict(как.most_common()),
                                           'принят_и_уже_в_списке(дубль)': дубли, 'запросов_DaData': dd.запросов,
                                           'минут': round((time.time() - t0) / 60, 1)}, ensure_ascii=False))


if __name__ == '__main__':
    sys.path.insert(0, DIR)
    sys.path.insert(0, r'C:\sender')
    os.chdir(DIR)
    os.environ.update({'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'PILOT_MODEL': 'gpt-6-luna',
                       'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
    if '--vnutri' not in sys.argv:
        import subprocess
        лог = os.path.join(DIR, 'inn_poisk_%s.log' % time.strftime('%d%m-%H%M'))
        with open(лог, 'wb') as в:
            p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'meyer7_inn_poisk.py'), '--vnutri'], cwd=DIR,
                                 creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                                 close_fds=False)
        time.sleep(40)
        print('===ИТОГ===')
        print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-800:]},
                         ensure_ascii=False))
        sys.exit(0)
    main()
