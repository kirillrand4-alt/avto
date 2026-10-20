# -*- coding: utf-8 -*-
# 20.10, владелец: «давай порядок поменяем, чтобы удешевить: сначала чеко, потом 1 запрос "ИНН + официальный сайт компании",
# и смотрим прогоном, есть ли на сайте ИНН; если есть — тогда уже пытаемся опровергнуть, найти на нём контакты обычным
# прогоном с паспортом». Заменяет агентов глубокого поиска для второй волны (fsa120: уникальные Meyer от 120 млн без сделок,
# выручка ФНС 2025 или checko; волна fsa500 доходит агентами, по ней — досбор сайта и паспорта, как в _fsa_volny).
# Шаги fsa120 (от большей выручки к меньшей):
#   1. checko по ИНН волны заново (CHECKO_ZANOVO=1) — кандидат в сайт с карточки (бесплатно, прокси владельца);
#   2. проверка «ИНН на сайте» без модели: кандидаты — сайт из декларации/домена почты, сайт с checko; если ни один не
#      подтвердился — ОДИН запрос xmlriver «ИНН <инн> официальный сайт» и до 3 доменов выдачи (без справочников).
#      На сайте открываются главная и до 5 страниц «контакты/реквизиты/о компании»; ИНН компании в тексте — подтверждён;
#   3. подтверждённые -> набор fsa120s: обход kc_kontakty, доизвлечение, скрытые номера, дообход, роли (лесенка Meyer),
#      аудит, опровергатели kc_oproverzhenie (Luna), паспорт pilot_pasport. Проверку сайта на Sol не делаем: ИНН на сайте.
# xmlriver — до остатка 1 ₽ (владелец: «без запасов»). Durable: fsa120-sayt-inn.jsonl (fsync, резюм), наборы шагов — свои
# jsonl с резюмом. Лог: fsa_deshevo_*.log.
import io, json, os, re, shutil, subprocess, sys, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if __name__ == '__main__' and '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa_deshevo_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa_deshevo.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-700:]},
                     ensure_ascii=False))
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402  (досбор, читать, запуск, хвост, идёт; модуль без --vnutri в argv не стартует сам)
import meyer_nalichie as MN  # noqa: E402

ВОЛНА = 'fsa120'
ВЫХ = os.path.join(DIR, ВОЛНА + '-sayt-inn.jsonl')
_лок = threading.Lock()
# 20.10, ревизия (№6): справочник — только по ХОСТУ (раньше подстрока по всему URL: «ok.ru» резал omskblok.ru, «t.me» —
# любые *time*, «xn--» — все .рф в punycode); плюс площадки мини-сайтов и найденные ревизией каталоги
СПРАВОЧНИКИ = re.compile(r'(^|\.)(rusprofile|checko|list-org|zachestnyibiznes|sbis|saby|spark-interfax|audit-it|e-ecolog|rbc|'
                         r'kontur|vbankcenter|ogrn|egrul|nalog|synapsenet|orgpage|yell|2gis|zoon|spravker|avito|hh|vk|ok|'
                         r't|youtube|wikipedia|prima-inform|globas|credinform|b2b-center|tiu|pulscen|all\.biz|flagma|companium|'
                         r'ofdata|bizly|esphere|torgi|zakupki|yandex|google|mail|dzen|sravni|tbank|datanewton|meatinfo|'
                         r'agroserver|o-zavodah|sledi|kartoteka|bfo|fek|rating-ru|spr|catalog|katalog)\.[a-zа-я.]+$', re.I)
# ссылки в любых кавычках, текст ссылки — с вложенными тегами
ССЫЛКИ = re.compile(r"""href\s*=\s*["']([^"'#]+)["'][^>]*>(.{0,300}?)</a""", re.I | re.S)
НУЖНЫЕ = re.compile(r'контакт|реквизит|о компании|о нас|политик|конфиденц|about|contact|kontakt|rekvizit|requisit|politik|'
                    r'privacy|policy|company|kompan|o-nas|o_nas|info', re.I)
ПАРКОВКА = re.compile(r'домен продаётся|домен продается|shopuri|this domain is for sale|reg\.ru/domain|парковка домена', re.I)


def _приоритет(u, т):
    s = u + ' ' + т
    for k, шаблон in enumerate((r'реквизит|rekvizit|requisit', r'политик|конфиденц|politik|privacy|policy',
                                r'контакт|contact|kontakt')):
        if re.search(шаблон, s, re.I):
            return k
    return 3


def хост(u):
    h = (urllib.parse.urlsplit(u if '//' in u else 'http://' + u).hostname or '').lower()
    return h[4:] if h.startswith('www.') else h


def п(*a):
    V.п(*a)


def записать(з):
    with _лок:
        with io.open(ВЫХ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


ЧУЖОЙ_ИНН = re.compile(r'ИНН[^\d]{0,15}(\d{10}|\d{12})(?!\d)', re.I)


def проверить(сайт, инн, телефоны=(), страница=''):
    """Найденная в выдаче страница (если есть) или главная + до 6 страниц по приоритету: реквизиты > политика > контакты >
    о компании. -> {'стр', 'как': 'ИНН' | 'телефон checko', 'чужой_инн'}. Ревизия 20.10 (№6): ИНН виден лишь на ~22%
    настоящих сайтов — второй уровень: телефон с карточки checko на сайте («вероятный», дальше опровергатели Luna);
    парковки доменов отсеиваются; чужой ИНН — «сайт группы?»."""
    out = {'стр': '', 'как': '', 'чужой_инн': ''}
    if not сайт:
        return out
    база = сайт if сайт.startswith('http') else 'https://' + сайт
    свой = re.compile(r'(?<!\d)%s(?!\d)' % инн)
    тт = {re.sub(r'\D', '', x)[-10:] for x in телефоны or () if len(re.sub(r'\D', '', x)) >= 10}
    чужие, тел_стр = [], ['']

    def смотреть(u, h):
        if свой.search(h):
            return True
        чужие.extend(x for x in ЧУЖОЙ_ИНН.findall(h) if x != инн)
        if тт and not тел_стр[0] and any(x in re.sub(r'\D', '', h) for x in тт):
            тел_стр[0] = u
        return False
    html, u = '', ''
    for u in ([страница] if страница else []) + [база, база.replace('https://', 'http://')]:
        ст, html, *_ = MN.скачать(u)
        if ст.startswith('ok') and html:
            break
        html = ''
    if not html or ПАРКОВКА.search(html[:20000]):
        return out
    if смотреть(u, html):
        return dict(out, стр=u, как='ИНН')
    дом = хост(u)
    корень = дом.split('.', 1)[-1] if дом.count('.') > 1 else дом
    урлы = set()
    for v, т in ССЫЛКИ.findall(html):
        т = re.sub(r'<[^>]+>', ' ', т)
        if НУЖНЫЕ.search(v + ' ' + т):
            полный = urllib.parse.urljoin(u, v.strip())
            if хост(полный).endswith(корень):
                урлы.add((_приоритет(v, т), полный))
    for _, v in sorted(урлы)[:6]:
        ст, h, *_ = MN.скачать(v)
        if ст.startswith('ok') and h and смотреть(v, h):
            return dict(out, стр=v, как='ИНН')
    if тел_стр[0]:
        return dict(out, стр=тел_стр[0], как='телефон checko')
    return dict(out, чужой_инн=max(set(чужие), key=чужие.count) if чужие else '')


def инн_на_сайте(сайт, инн):
    """Старый интерфейс: (страница с ИНН | '', 0)."""
    r = проверить(сайт, инн)
    return (r['стр'] if r['как'] == 'ИНН' else ''), 0


_бал = {'t': 0, 'v': None}


def xml_ok():
    with _лок:
        if time.time() - _бал['t'] > 120:
            try:
                оп = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                _бал['v'] = float(оп.open('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (
                    os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')), timeout=30).read(100))
            except Exception:  # noqa: BLE001
                pass
            _бал['t'] = time.time()
        return _бал['v'] is None or _бал['v'] >= 1.0


def поиск(q):
    U, K = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
    for попытка in range(8):
        url = ('http://xmlriver.com/search_yandex/xml?user=%s&key=%s&groupby=10&query=%s' if попытка % 2 == 0 else
               'http://xmlriver.com/search/xml?user=%s&key=%s&query=%s') % (urllib.parse.quote(U), urllib.parse.quote(K),
                                                                           urllib.parse.quote(q))
        try:
            xml = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=90).read().decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001
            time.sleep(5)
            continue
        if 'перезапрос' in xml or 'аняты все' in xml or 'свободных каналов' in xml:
            time.sleep(3 + 3 * попытка)
            continue
        # 20.10, ревизия: ответ-ошибка (кончились деньги и т.п.) — не «пустая выдача»
        if '<error' in xml or '&lt;error' in xml:
            return None
        return [re.sub(r'<[^>]+>', '', u).strip() for u in re.findall(r'<url>(.*?)</url>', xml, re.S)][:10]
    return None


def одна(к, чк):
    инн = к['inn']
    пробовали = []
    тел = (чк.get(инн) or {}).get('телефоны') or []
    сост = {'вероятный': None, 'группа': None}

    def пробовать(сайт, откуда, страница):
        r = проверить(сайт, инн, тел, страница)
        if r['как'] == 'ИНН':
            return {'inn': инн, 'сайт': хост(сайт) or сайт, 'как': откуда, 'страница_с_инн': r['стр'], 'проверено': пробовали}
        if r['как'] == 'телефон checko' and not сост['вероятный']:
            сост['вероятный'] = {'inn': инн, 'сайт': хост(сайт) or сайт, 'как': откуда + ' (вероятный: телефон checko на сайте)',
                                 'страница_с_инн': r['стр'], 'вероятный': True, 'проверено': пробовали}
        if r['чужой_инн'] and not сост['группа']:
            сост['группа'] = {'сайт_группы': хост(сайт) or сайт, 'чужой_инн': r['чужой_инн'], 'как_группы': откуда}
        return None
    for сайт, откуда in ((к.get('сайт') or '', 'декларация / домен почты'),
                         ((чк.get(инн) or {}).get('сайт_кандидат') or '', 'checko')):
        if сайт and хост(сайт) not in пробовали:
            пробовали.append(хост(сайт))
            з = пробовать(сайт, откуда, '')
            if з:
                return записать(dict(з, запрос=False))
    # 20.10, ревизия: вероятный сайт или сайт группы уже есть — запрос xmlriver не тратим
    if сост['вероятный']:
        return записать(dict(сост['вероятный'], запрос=False, **(сост['группа'] or {})))
    if сост['группа']:
        return записать(dict({'inn': инн, 'сайт': '', 'как': 'сайт группы? (чужой ИНН)', 'проверено': пробовали,
                              'запрос': False}, **сост['группа']))
    if not xml_ok():
        return записать({'inn': инн, 'сайт': '', 'как': 'xmlriver кончился', 'проверено': пробовали, 'запрос': False})
    урлы = поиск('ИНН %s официальный сайт' % инн)
    if урлы is None:
        return записать({'inn': инн, 'сайт': '', 'как': 'поиск не ответил', 'проверено': пробовали, 'запрос': True})
    выбор = []
    for u in урлы:
        д = хост(u)
        if д and not СПРАВОЧНИКИ.search(д) and д not in пробовали and д not in [x[0] for x in выбор]:
            выбор.append((д, u if '//' in u else 'http://' + u))
    for д, u in выбор[:3]:
        пробовали.append(д)
        з = пробовать(д, 'поиск «ИНН + официальный сайт»', u)
        if з:
            return записать(dict(з, запрос=True))
    if сост['вероятный']:
        return записать(dict(сост['вероятный'], запрос=True))
    if сост['группа']:
        return записать(dict({'inn': инн, 'сайт': '', 'как': 'сайт группы? (чужой ИНН)', 'проверено': пробовали,
                              'запрос': True}, **сост['группа']))
    записать({'inn': инн, 'сайт': '', 'как': 'ИНН ни на одном кандидате', 'проверено': пробовали, 'запрос': True})


def main():
    п('жду проход checko (2 876 без выручки)')
    while V.идёт('fsa_meyer_checko.py'):
        time.sleep(120)
    сп = json.load(io.open(os.path.join(ДРОП, ВОЛНА + '-spisok.json'), encoding='utf-8'))['компании']
    shutil.copyfile(os.path.join(ДРОП, ВОЛНА + '-spisok.json'), os.path.join(DIR, ВОЛНА + '-spisok.json'))
    порядок = sorted(сп, key=lambda i: -(сп[i].get('выручка') or 0))
    with open(os.path.join(ДРОП, ВОЛНА + '-inn.json'), 'w', encoding='utf-8') as f:
        json.dump(порядок, f)
    п('checko заново по волне', len(порядок))
    env = dict(os.environ, CHECKO_VHOD=ВОЛНА + '-inn.json', CHECKO_ZANOVO='1', PYTHONIOENCODING='utf-8')
    pr, лог = V.запуск('fsa_meyer_checko.py', env, ВОЛНА + '_checko')
    pr.wait()
    # fsa_meyer_checko без --vnutri отсоединяется сам — ждём его внутренний процесс
    time.sleep(60)
    while V.идёт('fsa_meyer_checko.py'):
        time.sleep(120)
    чк = {}
    for s in io.open(os.path.join(DIR, 'fsa-meyer-checko.jsonl'), encoding='utf-8', errors='replace'):
        try:
            y = json.loads(s)
        except ValueError:
            continue
        if y.get('inn') and y.get('итог') == 'ok':
            чк[y['inn']] = y
    п('checko готов: кандидатов в сайт', sum(1 for i in порядок if (чк.get(i) or {}).get('сайт_кандидат')))
    # 20.10, ревизия: «сбой», «поиск не ответил», «xmlriver кончился» после перезапуска — повторить
    уже = {i for i, x in V.читать(ВЫХ).items() if x.get('сайт') or x.get('как') in ('ИНН ни на одном кандидате', 'сайт группы? (чужой ИНН)')}
    # 20.10, ревизия (№2): неуникальные (найдены поиском в любом разделе, глубокий поиск был, сосед по группе найден
    # поиском), конкуренты, снятые владельцем ОКВЭД — не трогаем
    искл = set(json.load(io.open(os.path.join(ДРОП, 'fsa-isklyuchit.json'), encoding='utf-8')))
    очередь = [сп[i] for i in порядок if i not in уже and i not in искл]
    п('очередь проверки', len(очередь), '| исключено ревизией', len(set(порядок) & искл))
    n = [0]

    def шаг(к):
        try:
            одна(к, чк)
        except Exception as e:  # noqa: BLE001
            записать({'inn': к['inn'], 'сайт': '', 'как': 'сбой ' + repr(e)[:100]})
        with _лок:
            n[0] += 1
            if n[0] % 200 == 0:
                п('проверка ИНН на сайте', n[0], 'из', len(очередь))
    with ThreadPoolExecutor(12) as ex:
        list(ex.map(шаг, очередь))
    рез = V.читать(ВЫХ)
    подтв = {i: x for i, x in рез.items() if x.get('сайт') and i not in искл}
    п('ИНН на сайте подтверждён', len(подтв), 'из', len(рез), '| запросов xmlriver', sum(1 for x in рез.values() if x.get('запрос')))
    shutil.copyfile(ВЫХ, os.path.join(ДРОП, ВОЛНА + '-sayt-inn.jsonl'))
    набор = ВОЛНА + 's'
    нов = {i: dict(сп[i], сайт=x['сайт'], сайт_откуда='ИНН на сайте (%s): %s' % (x['как'], x.get('страница_с_инн', '')))
           for i, x in подтв.items() if i in сп}
    with open(os.path.join(DIR, набор + '-spisok.json'), 'w', encoding='utf-8') as f:
        json.dump({'компании': нов, 'снято': {}, 'ниже_порога': {}, 'на_решение': {}}, f, ensure_ascii=False)
    env = dict(os.environ, **V.ОБЩЕЕ, POISK_NABOR=набор, KC_NABOR=набор, PROVIDER_MODEL='gpt-6-luna')
    for файл, доп in (('kc_kontakty.py', {}), ('kc_doizvlech.py', {}), ('kc_doizvlech_pochty.py', {}),
                      ('kc_skrytye.py', {'KC_SKRYTYE_PROBA': '0'}), ('kc_doobhod.py', {}), ('kc_dorazmetka.py', {}),
                      ('kc_audit.py', {}), ('kc_oproverzhenie.py', {}), ('pilot_pasport.py', {})):
        питон = V.ПИТОН_ПАНЕЛИ if файл == 'pilot_pasport.py' and os.path.exists(V.ПИТОН_ПАНЕЛИ) else sys.executable
        t0 = time.time()
        pr, лог = V.запуск(файл, dict(env, **доп), набор + '_' + файл[:-3], питон)
        pr.wait()
        п(набор, файл, 'код', pr.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', V.хвост(лог))
    for ф in ('-kontakty.jsonl', '-audit.jsonl', '-oprov.jsonl', '-pasport.jsonl', '-spisok.json'):
        try:
            shutil.copyfile(os.path.join(DIR, набор + ф), os.path.join(ДРОП, набор + ф))
        except Exception as e:  # noqa: BLE001
            п('копия', набор + ф, repr(e)[:80])


def волна500():
    if os.path.exists(os.path.join(DIR, 'fsa500p-pasport.jsonl')):  # 20.10: досбор fsa500p уже сделан (перезапуск)
        return
    п('жду агентов fsa500')
    while V.идёт('_pusk_fsa500.py'):
        time.sleep(120)
    try:
        shutil.copyfile(os.path.join(DIR, 'fsa500-glubokiy.jsonl'), os.path.join(ДРОП, 'fsa500-glubokiy.jsonl'))
    except Exception as e:  # noqa: BLE001
        п('копия fsa500', repr(e)[:80])
    V.досбор('fsa500')


if __name__ == '__main__':  # 20.10: модуль импортирует _fsa_noch (проверка ИНН на сайте, поиск)
    т = threading.Thread(target=волна500)
    т.start()
    main()
    т.join()
    п('ДЁШЕВО: ГОТОВО')
