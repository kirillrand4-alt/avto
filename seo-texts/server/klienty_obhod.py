# -*- coding: utf-8 -*-
r"""Обход доменов: КЛИЕНТЫ КЦ/Meyer (ИНН на сайте) + ЗАКУПКИ (страницы, внешние ЭТП, планы) — 23.10, владелец: «нужен готовый
инструмент: адаптируй свои пути поиска + поиск ИНН, при котором мы сможем найти всех клиентов и их закупки». Полный проход
зоны пока отложен (риски для основного сервера) — инструмент готов к запуску на любом списке доменов: вся зона R01
(C:\sender\_tmp\domains\delegated.txt, 6,9 млн), выгрузка панелей, домены почт базы обзвона и т. п.

Основа — комбайн тендерной сессии (репозиторий tender, server/tender_crawl_all.py: закупочные разделы, внешние ЭТП, планы
закупок, вердикт без модели) + наш поиск реквизитов (_fsa_deshevo.проверить, kc_kontakty): приоритетные страницы
реквизиты > политика > контакты > о компании, ИНН/ОГРН с проверкой контрольных сумм, телефоны и почты.

На каждом домене (бюджет DEADLINE с):
  1) DNS (нет адреса — дальше); главная: https -> http -> https без проверки сертификата;
  2) заглушка / «не похоже на сайт компании» — только главная;
  3) ИНН/ОГРН/телефоны/почты с главной; ИНН нет — до RQ_MAX страниц реквизитов (ссылки меню + типовые пути), стоп на первом ИНН;
  4) закупки: ссылки главной и уже открытых страниц -> разделы меню -> карта сайта -> типовые пути (как в комбайне); на найденной
     странице — второй уровень (внешний портал, лоты);
  5) вердикт закупок эвристикой (своя ЭТП / страница с лотами / внешняя ЭТП / ссылка на внешний портал / план закупок /
     страница закупок без лотов / не закупки).
Модели здесь нет: сопоставление ИНН -> выручка/ОКВЭД -> сегмент КЦ/Meyer делает klienty_razbor.py.

Запуск (шарды по crc32 домена; повторный запуск продолжает):
    python klienty_obhod.py K N T [файл_доменов] [--limit=M]
Durable (правило DURABILITY, CLAUDE.md): всё — на диск сервера, построчно с fsync:
    <ПАПКА>\klienty-sK.jsonl      — домены с находками (ИНН, ОГРН или закупки);
    <ПАПКА>\klienty-sK-done.txt   — все пройденные домены (резюм: и без находок не обходим второй раз);
    <ДРОП>\klienty-sK-progress.json — счётчики (done, found, с ИНН, с закупками, причины отсева, нагрузка).
Нагрузка: при памяти или ЦП >= CAP% потоки встают на паузу (на основном сервере работают панель, tendery, Зенка).
"""
import html, json, os, re, socket, ssl, sys, threading, time, zlib
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse
import httpx

WIN = os.name == 'nt'
ПАПКА = os.environ.get('KLIENTY_DIR') or (r'C:\sender\server\klienty' if WIN else os.path.join(os.getcwd(), 'klienty'))
ДРОП = os.environ.get('KLIENTY_DROP') or (r'C:\seostat\drop\drop-storage' if WIN else ПАПКА)
арг = [a for a in sys.argv[1:] if not a.startswith('--')]
K = int(арг[0]) if len(арг) > 0 else 0
N = int(арг[1]) if len(арг) > 1 else 1
T = int(арг[2]) if len(арг) > 2 else 48
SRC = арг[3] if len(арг) > 3 else r'C:\sender\_tmp\domains\delegated.txt'
LIMIT = next((int(a.split('=', 1)[1]) for a in sys.argv if a.startswith('--limit=')), 0)
CAP = int(os.environ.get('KLIENTY_CAP', '90'))
DEADLINE = int(os.environ.get('KLIENTY_DEADLINE', '45'))
RQ_MAX = 4
SUF = '-s%d' % K

ctx = ssl.create_default_context()
for n in ('russian_trusted_root_ca_pem.crt', 'russian_trusted_sub_ca_pem.crt'):  # сертификаты Минцифры (госсайты, банки)
    p = os.path.join(r'C:\sender\_tmp\tender_ca', n)
    if os.path.exists(p):
        ctx.load_verify_locations(p)
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
     'Accept-Language': 'ru-RU,ru;q=0.9'}

# --- закупки: словари комбайна tender_crawl_all.py ---
PROC = re.compile(r'закуп|тендер|поставщик|торги|конкурс\w* (закуп|на поставк|предложени)|запрос\w* (предложени|котиров|цен)|снабжен|procure|tender|'
                  r'purchas|supplier|zakup|postavsh|snab|srm|ariba|itender', re.I)
PLAN = re.compile(r'план\w*\s+закуп|гкпз|программ\w*\s+закуп|годов\w*\s+план|перечень\s+закуп|plan\w*[-_ ]?(zakup|purchas|procure)|zakupki[-_]?plan|'
                  r'procurement[-_ ]?plan', re.I)
FILEZ = re.compile(r'\.(xlsx?|xlsm|pdf|docx?|zip|rar)(\?|$)', re.I)
SECTIONS = re.compile(r'о компании|о заводе|о предприятии|о нас|компания|предприятие|контакт|документ|раскрыти|поставщик|партн[её]р|сотрудничеств|'
                      r'карта сайта|about|company|contacts?|documents?|partners?|suppliers?|disclosure', re.I)
PROC_ANCHOR = re.compile(r'закуп|тендер|поставщик|торг[иа]|снабжен|procure|tender|supplier|purchas', re.I)
SKIP = re.compile(r'(^|\.)(vk\.com|vkontakte|t\.me|telegram|youtube|youtu\.be|ok\.ru|rutube|dzen|zen\.yandex|yandex\.|google\.|apple\.com|mail\.ru|hh\.ru|'
                  r'gosuslugi|nalog\.|consultant|garant|2gis|wikipedia|facebook|instagram|twitter|x\.com|whatsapp|viber|rbc\.ru|tass\.ru|interfax|'
                  r'kremlin|government\.ru|minpromtorg|fas\.gov|cbr\.ru|sbis|kontur|rusprofile|checko|list-org|zachestnyibiznes)', re.I)
ETP = {'b2b-center': r'b2b-center\.ru', 'bidzaar': r'bidzaar', 'tektorg': r'tektorg', 'roseltorg': r'roseltorg', 'gpb': r'etpgpb|etp\.gpb',
       'fabrikant': r'fabrikant', 'tender.pro': r'tender\.pro', 'rts': r'rts-tender', 'sber': r'sberbank-ast|sberb2b', 'otc': r'otc\.ru|onlinecontract',
       'eis': r'zakupki\.gov\.ru', 'zakazrf': r'zakazrf|etprf', 'sap': r'sap-client|/sap/|nwbc|irj/portal', 'ariba': r'ariba\.com',
       'itender': r'itender', 'suppman': r'suppman'}
ETP_HOST = re.compile(r'b2b-center\.ru|bidzaar|tektorg|roseltorg|etpgpb|fabrikant|tender\.pro|rts-tender|sberbank-ast|sberb2b|otc\.ru|onlinecontract|'
                      r'zakupki\.gov\.ru|zakazrf|etprf|suppman|lot-online|torgi\.gov', re.I)
OWN_HOST = re.compile(r'^(tender|tenders|zakupki|zakupka|zakup|srm|b2b|etp|supplier|suppliers|postavshik|snab|procurement|purchase|purchasing|torgi|'
                      r'trade|supply|sourcing)\.', re.I)
ENGINE = re.compile(r'sap-client|/sap/|nwbc|irj/portal|ariba|itender|iteco|retor|fogsoft|\bb2b-?center\b', re.I)
PATHS = ['/zakupki/', '/tenders/', '/purchases/', '/procurement/', '/suppliers/', '/postavshchikam/', '/tender/', '/purchase/', '/about/procurement/',
         '/about/tenders/', '/about/zakupki/', '/company/tenders/', '/company/zakupki/', '/procurement-notices/', '/index/zakupki/', '/documents/tender/',
         '/buy/', '/zakupka/', '/torgi/', '/konkursy/', '/partners/', '/postavshikam/', '/dlya-postavshchikov/', '/info/zakupki/', '/kontragentam/',
         '/snabzhenie/']
PARKED = re.compile(r'домен\w*\s+(продается|продаётся|припаркован|зарегистрирован|свободен)|domain\s+(is\s+)?(for\s+sale|parked)|this\s+domain|'
                    r'buy\s+this\s+domain|сайт\s+(в\s+разработке|находится\s+в\s+разработке|временно\s+недоступен)|under\s+construction|coming\s+soon|'
                    r'default\s+web\s+site|index\s+of\s+/|it\s+works!|welcome\s+to\s+nginx|apache2?\s+(ubuntu\s+)?default|hosting\s+(is\s+)?(expired|suspended)|'
                    r'аккаунт\s+заблокирован|услуги\s+хостинга\s+приостановлены', re.I)
COMPANY = re.compile(r'\bООО\b|\bАО\b|\bПАО\b|\bОАО\b|\bЗАО\b|завод|комбинат|компани|предприят|производств|\bИНН\b|\bОГРН\b|холдинг|группа компаний', re.I)
LOTS = re.compile(r'(запрос\w* (предложени|котиров|цен|ткп)|лот\s*№|№\s*\d{3,}|приём заявок|прием заявок|окончани\w* (подачи|приема|приёма)|срок подачи)', re.I)

# --- реквизиты: наш порядок (_fsa_deshevo: реквизиты > политика > контакты > о компании) ---
RQ_ANCHOR = re.compile(r'реквизит|rekvizit|requisit|политик\w* (конфиденц|обработк)|персональн\w* данн|privacy|policy|politika|контакт|kontakt|contact|'
                       r'о компании|о нас|о предприятии|о заводе|about|o-kompanii|kompaniya|оферт|oferta|юридическ', re.I)
RQ_PRIO = [(re.compile(r'реквизит|rekvizit|requisit', re.I), 0), (re.compile(r'политик|персональн|privacy|policy|politika|оферт|oferta', re.I), 1),
           (re.compile(r'контакт|kontakt|contact', re.I), 2), (re.compile(r'.', re.I), 3)]
RQ_PATHS = ['/rekvizity/', '/requisites/', '/contacts/', '/kontakty/', '/about/', '/o-kompanii/', '/privacy-policy/', '/politika-konfidencialnosti/']
INN_RX = re.compile(r'ИНН(?:\s*/\s*КПП)?[\s:№.\-]{0,6}(\d{10}|\d{12})(?!\d)', re.I)
INN_KPP_RX = re.compile(r'(?<!\d)(\d{10})\s*/\s*\d{9}(?!\d)')
OGRN_RX = re.compile(r'ОГРН(?:ИП)?[\s:№.\-]{0,6}(\d{13}|\d{15})(?!\d)', re.I)
PHONE_RX = re.compile(r'(?<![\d+])(?:\+7|8)[\s\-(]*\d{3,5}[\s\-)]*\d{1,3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)')
MAIL_RX = re.compile(r'[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,120}\.[A-Za-z]{2,12}')
MAIL_SKIP = re.compile(r'\.(png|jpe?g|gif|svg|webp|css|js)$|example\.|sentry|wixpress|@2x', re.I)


def инн_ок(s):
    """Контрольные числа ИНН (10 — юрлицо, 12 — ИП/физлицо): отсекает случайные 10/12-значные числа."""
    d = [int(c) for c in s]
    if len(d) == 10:
        return d[9] == sum(k * v for k, v in zip((2, 4, 10, 3, 5, 9, 4, 6, 8), d)) % 11 % 10
    if len(d) == 12:
        c1 = sum(k * v for k, v in zip((7, 2, 4, 10, 3, 5, 9, 4, 6, 8), d)) % 11 % 10
        c2 = sum(k * v for k, v in zip((3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8), d)) % 11 % 10
        return d[10] == c1 and d[11] == c2
    return False


def огрн_ок(s):
    if len(s) == 13:
        return int(s[12]) == int(s[:12]) % 11 % 10
    if len(s) == 15:
        return int(s[14]) == int(s[:14]) % 13 % 10
    return False


def text_of(t):
    t = re.sub(r'(?is)<(script|style|noscript).*?</\1>', ' ', t)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t))).strip()


def get(cl, u, timeout=None):
    try:
        r = cl.get(u, timeout=timeout) if timeout else cl.get(u)
        return r.status_code, r.text[:600000], str(r.url)
    except Exception:
        return None, '', u


def resolves(host):
    for h in (host, 'www.' + host):
        try:
            socket.getaddrinfo(h, 443, proto=socket.IPPROTO_TCP)
            return True
        except Exception:
            pass
    return False


def реквизиты(out, h, u):
    """ИНН/ОГРН/телефоны/почты со страницы — в out (с адресом страницы, где найден ИНН)."""
    tx = text_of(h)
    for i in INN_RX.findall(tx) + INN_KPP_RX.findall(tx):
        if инн_ок(i) and i not in out['inn']:
            out['inn'].append(i)
            out['inn_page'].setdefault(i, u[:300])
    for o in OGRN_RX.findall(tx):
        if огрн_ок(o) and o not in out['ogrn']:
            out['ogrn'].append(o)
    for t in PHONE_RX.findall(tx):
        н = re.sub(r'\D', '', t)
        н = '7' + н[1:] if len(н) == 11 and н[0] == '8' else н
        if len(н) == 11 and н not in out['phones'] and len(out['phones']) < 8:
            out['phones'].append(н)
    for m in MAIL_RX.findall(h):
        m = m.lower()
        if not MAIL_SKIP.search(m) and m not in out['emails'] and len(out['emails']) < 8:
            out['emails'].append(m)


def scan(h, u, root, out, cands, ext, rq):
    """Ссылки страницы: закупки (свои / чужой портал / ЭТП / планы) и кандидаты в реквизиты."""
    for href, a in re.findall(r'(?is)<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', h):
        full = urljoin(u, html.unescape(href.strip()))
        pu = urlparse(full)
        if pu.scheme not in ('http', 'https'):
            continue
        an = text_of(a)[:80]
        low = full.lower()
        if (PLAN.search(an + ' ' + full) or (FILEZ.search(pu.path) and re.search(r'закуп|purchas|procure|zakup', an + ' ' + full, re.I))) \
                and full not in [x[0] for x in out['plans']] and len(out['plans']) < 10:
            out['plans'].append((full[:300], an))
        for k, p in ETP.items():
            if re.search(p, low):
                out['ext_etp'][k] = full[:200]
        nl = pu.netloc.lower().split(':')[0]
        if nl.endswith(root):
            if PROC.search(full + ' ' + an) and full not in [c[0] for c in cands]:
                cands.append((full, an))
            if rq is not None and pu.path not in ('', '/') and not FILEZ.search(pu.path) and RQ_ANCHOR.search(an + ' ' + pu.path) \
                    and full not in [x[1] for x in rq]:
                rq.append((next(п for rx, п in RQ_PRIO if rx.search(an + ' ' + pu.path)), full))
        elif PROC_ANCHOR.search(an) and not SKIP.search(nl) and not ETP_HOST.search(nl) and full not in [c[0] for c in ext]:
            ext.append((full, an))


def page(cl, cu, an):
    if FILEZ.search(urlparse(cu).path):
        return None, ''
    st, h, u = get(cl, cu)
    if not st:
        return None, ''
    tx = text_of(h)
    return {'url': u[:300], 'anchor': an, 'status': st, 'title': (re.search(r'(?is)<title>(.*?)</title>', h) or [None, ''])[1].strip()[:150],
            'marks': {k: 1 for k, p in ETP.items() if re.search(p, h.lower())}, 'lots': len(LOTS.findall(tx)), 'len': len(tx)}, h


def one(host):
    out = {'host': host, 'home': None, 'inn': [], 'inn_page': {}, 'ogrn': [], 'phones': [], 'emails': [], 'links': [], 'ext_links': [],
           'ext_etp': {}, 'pages': [], 'plans': [], 'sections': []}
    t0 = time.time()
    left = lambda: DEADLINE - (time.time() - t0)  # noqa: E731
    if not resolves(host):
        out['skip'] = 'нет DNS'
        return out
    with httpx.Client(verify=ctx, headers=H, follow_redirects=True, timeout=12) as cl:
        st, h, u = get(cl, 'https://' + host + '/')
        if not st:
            st, h, u = get(cl, 'http://' + host + '/')
        if not st:
            with httpx.Client(verify=False, headers=H, follow_redirects=True, timeout=12) as c2:
                st, h, u = get(c2, 'https://' + host + '/')
        out['home'] = [st, u[:200], (re.search(r'(?is)<title>(.*?)</title>', h) or [None, ''])[1].strip()[:150]]
        if not st:
            return out
        base = urlparse(u).netloc.lower()
        root = '.'.join(base.split('.')[-2:])
        cands, ext, rq = [], [], []
        scan(h, u, root, out, cands, ext, rq)
        реквизиты(out, h, u)
        tx_home = text_of(h)
        if PARKED.search(out['home'][2] + ' ' + tx_home[:2000]):
            out['skip'] = 'заглушка'
        elif not COMPANY.search(tx_home[:20000]) and (len(tx_home) < 800 or len(re.findall(r'(?i)<a\s', h)) < 8):
            out['skip'] = 'не похоже на сайт компании'
        deep = 'skip' not in out
        # реквизиты: ИНН с главной нет — приоритетные страницы меню, затем типовые пути; стоп на первом ИНН
        if deep and not out['inn']:
            очередь = [x[1] for x in sorted(rq)[:RQ_MAX]]
            очередь += ['https://' + base + p for p in RQ_PATHS if ('https://' + base + p) not in очередь]
            открыто = 0
            for ru in очередь:
                if out['inn'] or открыто >= RQ_MAX or left() < 8:
                    break
                st3, h3, u3 = get(cl, ru, timeout=8)
                if st3 == 200:
                    открыто += 1
                    реквизиты(out, h3, u3)
                    scan(h3, u3, root, out, cands, ext, None)
        # закупки — как в комбайне: разделы меню -> карта сайта -> типовые пути
        if not cands and deep and left() > 5:
            secs = []
            for href, a in re.findall(r'(?is)<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', h):
                full = urljoin(u, html.unescape(href.strip()))
                an = text_of(a)[:60]
                pu = urlparse(full)
                if pu.netloc.lower().split(':')[0].endswith(root) and pu.path not in ('', '/') and SECTIONS.search(an + ' ' + pu.path) \
                        and full not in [s[0] for s in secs]:
                    secs.append((full, an))
            out['sections'] = [s[1] for s in secs[:6]]
            for su, sa in secs[:6]:
                if left() < 5:
                    break
                st5, h5, u5 = get(cl, su, timeout=8)
                if st5 == 200:
                    scan(h5, u5, root, out, cands, ext, None)
                    if not out['inn']:
                        реквизиты(out, h5, u5)
                if len(cands) >= 3:
                    break
        if not cands and deep and left() > 5:
            st6, h6, _ = get(cl, 'https://' + base + '/sitemap.xml', timeout=8)
            if st6 == 200 and '<loc' in h6:
                locs = re.findall(r'<loc>\s*([^<]+?)\s*</loc>', h6)
                for sm in [x for x in locs if x.endswith('.xml')][:3]:
                    if left() < 5:
                        break
                    st7, h7, _ = get(cl, sm, timeout=8)
                    if st7 == 200:
                        locs += re.findall(r'<loc>\s*([^<]+?)\s*</loc>', h7)
                for x in locs:
                    if PROC.search(urlparse(x).path) and x not in [c[0] for c in cands]:
                        cands.append((x, 'sitemap'))
                    if len(cands) >= 5:
                        break
        if not cands and deep:
            misses = 0
            for pth in PATHS:
                if left() < 4 or misses >= 3:
                    break
                st2, h2, u2 = get(cl, 'https://' + base + pth, timeout=6)
                if st2 is None:
                    misses += 1
                    continue
                misses = 0
                if st2 == 200 and PROC.search(text_of(h2)[:3000]) and urlparse(u2).path not in ('', '/'):
                    cands.append((u2, 'path:' + pth))
                    break
        for cu, an in cands[:2]:
            if left() < 3:
                break
            pg, h3 = page(cl, cu, an)
            if pg:
                out['pages'].append(pg)
                scan(h3, pg['url'], root, out, [], ext, None)
                if not out['inn']:
                    реквизиты(out, h3, pg['url'])
        out['links'] = cands[:10]
        out['ext_links'] = ext[:10]
        for cu, an in ext[:2]:
            if left() < 3:
                break
            pg, _ = page(cl, cu, an)
            if pg:
                out.setdefault('ext_pages', []).append(pg)
    out['verdict'] = verdict(out)
    out['sec'] = round(time.time() - t0, 1)
    return out


def verdict(r):
    pages = r.get('pages') or []
    ext = set(r.get('ext_etp') or {})
    lots = max([p.get('lots', 0) for p in pages] or [0])
    hosts = [urlparse(p['url']).netloc.lower() for p in pages] + [urlparse(l[0]).netloc.lower() for l in r.get('links') or []]
    own_host = any(OWN_HOST.match(x[4:] if x.startswith('www.') else x) for x in hosts)
    engine = any(ENGINE.search(p.get('url', '') + ' ' + ''.join(p.get('marks') or {})) for p in pages) or \
        any(ENGINE.search(v) for v in (r.get('ext_etp') or {}).values())
    if not r.get('links') and not r.get('ext_links'):
        return 'план закупок' if r.get('plans') else 'не закупки'
    if own_host or engine:
        return 'кандидат: своя ЭТП'
    if lots >= 3:
        return 'кандидат: страница с лотами'
    if r.get('ext_links') and not r.get('links'):
        return 'ссылка на внешний портал'
    if ext:
        return 'внешняя ЭТП'
    return 'страница закупок без лотов'


# --- сторож нагрузки (Windows — как в комбайне; Linux — /proc) ---
LOAD = {'mem': 0, 'cpu': 0, 'busy': False}


def watch():
    if WIN:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32

        class MEM(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong)] + \
                [(n, ctypes.c_ulonglong) for n in ('tp', 'ap', 'tpf', 'apf', 'tv', 'av', 'aev')]

        def times():
            i, k, u = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            k32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
            f = lambda t: (t.dwHighDateTime << 32) | t.dwLowDateTime  # noqa: E731
            return f(i), f(k) + f(u)

        def mem():
            m = MEM()
            m.dwLength = ctypes.sizeof(m)
            k32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.dwMemoryLoad
    else:
        def times():
            ч = [int(x) for x in open('/proc/stat').readline().split()[1:]]
            return ч[3] + ч[4], sum(ч)

        def mem():
            м = dict((s.split(':')[0], int(s.split()[1])) for s in open('/proc/meminfo'))
            return round(100 * (1 - м['MemAvailable'] / м['MemTotal']))
    a = times()
    while True:
        time.sleep(2)
        b = times()
        tot = b[1] - a[1]
        LOAD['cpu'] = round(100 * (1 - (b[0] - a[0]) / tot), 1) if tot else 0
        a = b
        LOAD['mem'] = mem()
        LOAD['busy'] = LOAD['mem'] >= CAP or LOAD['cpu'] >= CAP


def main():
    os.makedirs(ПАПКА, exist_ok=True)
    ВЫХ = os.path.join(ПАПКА, 'klienty%s.jsonl' % SUF)
    СДЕЛАНО = os.path.join(ПАПКА, 'klienty%s-done.txt' % SUF)
    ПРОГ = os.path.join(ДРОП, 'klienty%s-progress.json' % SUF)
    seen = set()
    if os.path.exists(СДЕЛАНО):
        seen = {s.strip() for s in open(СДЕЛАНО, encoding='utf-8', errors='replace') if s.strip()}
    jobs = []
    with open(SRC, encoding='utf-8', errors='replace') as f:
        for line in f:
            d = line.strip().lower().split()[0] if line.strip() else ''
            if not d or '.' not in d:
                continue
            d = re.sub(r'^https?://', '', d).split('/')[0]
            d = d[4:] if d.startswith('www.') else d
            if zlib.crc32(d.encode()) % N == K and d not in seen:
                jobs.append(d)
                if LIMIT and len(jobs) >= LIMIT:
                    break
    threading.Thread(target=watch, daemon=True).start()
    lock = threading.Lock()
    fout, fdone = open(ВЫХ, 'a', encoding='utf-8'), open(СДЕЛАНО, 'a', encoding='utf-8')
    st = {'src': SRC, 'shard': '%d/%d' % (K, N), 'threads': T, 'queued': len(jobs), 'done_before': len(seen), 'done': 0, 'found': 0,
          'с_ИНН': 0, 'с_закупками': 0, 'с_планом': 0, 'by': {}, 'verdict': {}, 'started': time.strftime('%Y-%m-%d %H:%M:%S')}

    def прогресс(final=False):
        st['load'] = dict(LOAD)
        if final:
            st['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
        tmp = ПРОГ + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False)
        os.replace(tmp, ПРОГ)

    def run(host):
        while LOAD['busy']:
            time.sleep(1)
        try:
            r = one(host)
        except Exception as e:  # noqa: BLE001
            r = {'host': host, 'error': repr(e)[:100], 'inn': []}
        with lock:
            st['done'] += 1
            why = r.get('skip') or r.get('error') and 'сбой' or ('не открылся' if not (r.get('home') or [None])[0] else 'открылся')
            st['by'][why] = st['by'].get(why, 0) + 1
            закупки = r.get('links') or r.get('ext_links') or r.get('plans') or r.get('ext_etp')
            if r.get('inn') or r.get('ogrn') or закупки:
                fout.write(json.dumps(r, ensure_ascii=False) + '\n')
                st['found'] += 1
                st['с_ИНН'] += bool(r.get('inn'))
                st['с_закупками'] += bool(закупки)
                st['с_планом'] += bool(r.get('plans'))
                st['verdict'][r.get('verdict', '')] = st['verdict'].get(r.get('verdict', ''), 0) + 1
            fdone.write(host + '\n')
            if st['done'] % 200 == 0:
                for f in (fout, fdone):
                    f.flush()
                    os.fsync(f.fileno())
                прогресс()

    socket.setdefaulttimeout(12)
    прогресс()
    with ThreadPoolExecutor(T) as pool:
        list(pool.map(run, jobs))
    with lock:
        for f in (fout, fdone):
            f.flush()
            os.fsync(f.fileno())
        прогресс(final=True)


if __name__ == '__main__':
    main()
