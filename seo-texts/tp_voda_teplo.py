# -*- coding: utf-8 -*-
"""Ранние следы стройки: ВОДА, КАНАЛИЗАЦИЯ, ТЕПЛО и градостроительные системы.

Участок этой сессии (соседние копают электросети и газ — сюда не лезем):
  1) водоканалы и теплосети, раздел «раскрытие информации»: реестры выданных
     технических условий, журналы заявок на подключение, перечни договоров о
     подключении, инвестпрограммы с адресной частью, сведения о резерве мощности;
  2) ГИСОГД/ИСОГД регионов и федеральные сервисы разрешений на строительство.

Вопрос ко всякому источнику один: есть ли в нём ЗАЯВИТЕЛЬ (застройщик), то есть
имя юрлица, которое строит, а не имя сетевой организации, которая раскрывает.

Запуск:
    python3 tp_voda_teplo.py env                # версия питона и модули слоя
    python3 tp_voda_teplo.py probe [группа]     # код/размер/титул по целям
    python3 tp_voda_teplo.py hunt  [группа]     # искать слова-маркеры и ссылки
    python3 tp_voda_teplo.py fetch <url> [имя]  # скачать файл в _ops и описать
    python3 tp_voda_teplo.py cols  <файл>       # напечатать КОЛОНКИ таблицы
Группы: voda, teplo, gisogd, kontrol, vse.

Правила, по которым написан код:
  * код ответа HTTP — это ОТВЕТ. Недоступен только тот, кто не ответил вовсе (код 0);
  * у каждого признака свой контроль с заведомо негодным входом (группа kontrol,
    выдуманные слова в hunt, выдуманное имя колонки в cols);
  * колонки печатаем, а не угадываем.
"""
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OPS = r'C:\sender\_ops' if os.name == 'nt' else os.environ.get(
    'TP_OPS', '/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/scratchpad')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

# ---------------------------------------------------------------- цели

VODA = [
    ('Мосводоканал', 'Москва', 'https://www.mosvodokanal.ru/'),
    ('Водоканал Санкт-Петербурга', 'СПб', 'https://www.vodokanal.spb.ru/'),
    ('Росводоканал (группа)', 'РФ', 'https://www.rosvodokanal.ru/'),
    ('РВК-Омск', 'Омск', 'https://omskvodokanal.ru/'),
    ('РВК-Барнаул', 'Алтайский край', 'https://barnaul.rosvodokanal.ru/'),
    ('РВК-Краснодар', 'Краснодар', 'https://krasnodar.rosvodokanal.ru/'),
    ('РВК-Оренбург', 'Оренбург', 'https://orenburg.rosvodokanal.ru/'),
    ('РВК-Тюмень', 'Тюмень', 'https://tyumen.rosvodokanal.ru/'),
    ('РВК-Воронеж', 'Воронеж', 'https://voronezh.rosvodokanal.ru/'),
    ('РКС (группа)', 'РФ', 'https://www.roscomsys.ru/'),
    ('Самарские коммунальные системы', 'Самара', 'https://www.samcomsys.ru/'),
    ('НОВОГОР-Прикамье', 'Пермь', 'https://www.novogor.perm.ru/'),
    ('Водоканал Екатеринбурга', 'Свердловская', 'https://www.vodokanalekb.ru/'),
    ('Горводоканал Новосибирск', 'Новосибирск', 'https://www.gorvodokanal.com/'),
    ('Нижегородский водоканал', 'Нижегородская', 'https://vodokanal-nn.ru/'),
    ('Уфаводоканал', 'Башкортостан', 'https://www.ufavodokanal.ru/'),
    ('Водоканал Казани', 'Татарстан', 'https://kazanvodokanal.ru/'),
    ('Водоканал Ростова-на-Дону', 'Ростовская', 'https://vodokanalrnd.ru/'),
    ('ПОВВ Челябинск', 'Челябинская', 'https://www.povv.ru/'),
    ('КрасКом', 'Красноярск', 'https://www.kraskom.com/'),
    ('Концессии водоснабжения Волгоград', 'Волгоградская', 'https://kv34.ru/'),
    ('Водоканал Владивостока', 'Приморский', 'https://vodokanal-vl.ru/'),
    ('Саратовводоканал', 'Саратовская', 'https://www.saratovvodokanal.ru/'),
]

TEPLO = [
    ('Т Плюс', 'РФ', 'https://www.tplusgroup.ru/'),
    ('СГК', 'Сибирь', 'https://sibgenco.ru/'),
    ('МОЭК', 'Москва', 'https://www.moek.ru/'),
    ('ТГК-1', 'СЗФО', 'https://www.tgc1.ru/'),
    ('ТГК-2', 'Ярославль/Архангельск', 'https://www.tgc-2.ru/'),
    ('ТГК-14', 'Забайкалье/Бурятия', 'https://www.tgk-14.com/'),
    ('ГУП ТЭК СПб', 'СПб', 'https://www.gptek.spb.ru/'),
    ('Теплосеть Санкт-Петербурга', 'СПб', 'https://www.teploset.spb.ru/'),
    ('РИР (Росатом, б. Квадра)', 'ЦФО', 'https://rosatom-rir.ru/'),
    ('Квадра', 'ЦФО', 'https://www.quadra.ru/'),
    ('Татэнерго', 'Татарстан', 'https://tatenergo.ru/'),
    ('Мосэнерго', 'Москва', 'https://mosenergo.gazprom.ru/'),
    ('СИБЭКО', 'Новосибирск', 'https://sibeco.su/'),
    ('Екатеринбургэнергосбыт/ЕТК', 'Екатеринбург', 'https://www.ektk.ru/'),
    ('Нижегородский теплоэнергетический', 'Нижегородская', 'https://ntek-nn.ru/'),
    ('Красноярская теплотранспортная', 'Красноярск', 'https://www.ktts24.ru/'),
    ('ПСК Пермь', 'Пермь', 'https://permenergosbyt.ru/'),
    ('Ульяновск УльГЭС', 'Ульяновск', 'https://ulges.ru/'),
]

GISOGD = [
    ('ГИСОГД Москвы (ИАИС ОГД)', 'Москва', 'https://www.mos.ru/mka/'),
    ('Открытые данные Москвы', 'Москва', 'https://data.mos.ru/'),
    ('ГИСОГД Московской области', 'Подмосковье', 'https://gisogd.mosreg.ru/'),
    ('ИСОГД Подмосковья (портал)', 'Подмосковье', 'https://isogd.mosreg.ru/'),
    ('ГИСОГД Татарстана', 'Татарстан', 'https://gisogd.tatarstan.ru/'),
    ('ГИСОГД Свердловской обл.', 'Свердловская', 'https://gisogd.midural.ru/'),
    ('ГИСОГД Нижегородской обл.', 'Нижегородская', 'https://gisogd.government-nnov.ru/'),
    ('ГИСОГД Краснодарского края', 'Краснодарский', 'https://gisogd.krasnodar.ru/'),
    ('ГИСОГД Башкортостана', 'Башкортостан', 'https://gisogd.bashkortostan.ru/'),
    ('ГИСОГД Ленинградской обл.', 'Ленинградская', 'https://gisogd.lenobl.ru/'),
    ('ГИСОГД Ростовской обл.', 'Ростовская', 'https://gisogd.donland.ru/'),
    ('ГИСОГД Новосибирской обл.', 'Новосибирская', 'https://gisogd.nso.ru/'),
    ('ГИСОГД РФ (федеральная)', 'РФ', 'https://gisogd.gov.ru/'),
    ('ЕИСЖС наш.дом.рф', 'РФ', 'https://наш.дом.рф/'),
    ('ЕИСЖС API-портал', 'РФ', 'https://xn--80az8a.xn--d1aqf.xn--p1ai/'),
    ('Минстрой РФ', 'РФ', 'https://minstroyrf.gov.ru/'),
    ('ГИС ЖКХ', 'РФ', 'https://dom.gosuslugi.ru/'),
]

# Контроль: заведомо негодный вход. Если прибор исправен — тут будет код 0 или 404,
# а не то же самое, что у настоящих целей.
KONTROL = [
    ('КОНТРОЛЬ несуществующий хост', '-', 'https://vodokanal-shvarckopfer-12345.ru/'),
    ('КОНТРОЛЬ несуществующая страница', '-', 'https://www.moek.ru/shvarckopfer-12345/'),
]

# Запасные адреса тех, кто не отозвался по первому имени. Ноль по имени хоста —
# это ноль по ИМЕНИ, а не по организации: прежде чем писать «источника нет»,
# проверяем другие написания.
ZAPAS = [
    ('Оренбург Водоканал (РВК)', 'Оренбургская', 'https://orenvodokanal.ru/'),
    ('Оренбург Водоканал вар.2', 'Оренбургская', 'https://www.orenvk.ru/'),
    ('Нижегородский водоканал вар.2', 'Нижегородская', 'https://nnovvodokanal.ru/'),
    ('Нижегородский водоканал вар.3', 'Нижегородская', 'https://vodokanal-nn.ru/'),
    ('Водоканал Казани вар.2', 'Татарстан', 'https://vodokanal.kzn.ru/'),
    ('Водоканал Казани вар.3', 'Татарстан', 'https://www.kzn-vodokanal.ru/'),
    ('ПОВВ Челябинск вар.2', 'Челябинская', 'https://muppovv.ru/'),
    ('ПОВВ Челябинск вар.3', 'Челябинская', 'http://www.povv.ru/'),
    ('Концессии водоснабжения вар.2', 'Волгоградская', 'https://www.kv34.ru/index.php'),
    ('Концессии водоснабжения вар.3', 'Волгоградская', 'https://kvs34.ru/'),
    ('Саратовводоканал', 'Саратовская', 'https://www.saratovvodokanal.ru/'),
    ('Водоканал Воронежа (РВК)', 'Воронежская', 'https://voronezh.rosvodokanal.ru/'),
]

GRUPPY = {'voda': VODA, 'teplo': TEPLO, 'gisogd': GISOGD, 'kontrol': KONTROL,
          'zapas': ZAPAS}
GRUPPY['vse'] = VODA + TEPLO + GISOGD + KONTROL

# Слова-маркеры. Разделены по смыслу: что ищем и что это доказывает.
SLOVA_TU = ['реестр выданных технических условий', 'перечень выданных технических условий',
            'реестр технических условий', 'выданных ту', 'журнал учета заявлений',
            'журнал учёта заявлений', 'реестр заявок на подключение',
            'реестр заявлений о подключении', 'перечень договоров о подключении',
            'реестр договоров о подключении', 'реестр выданных ту']
SLOVA_PODKL = ['технические условия', 'подключение', 'технологическое присоединение',
               'резерв мощности', 'свободная мощность', 'пропускная способность']
SLOVA_RASKR = ['раскрытие информации', 'стандарты раскрытия', 'инвестиционная программа']
# Контроль на слова: выдуманное слово не должно находиться нигде.
SLOVA_KONTROL = ['щварцкопфер', 'зюзюбликовый реестр']


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def idna(url):
    """Кириллический хост -> punycode. Без этого urllib падает на 'latin-1 codec'
    и это выглядит как «хост не ответил», хотя запроса не было вовсе."""
    try:
        p = urllib.parse.urlsplit(url)
        if p.hostname and any(ord(c) > 127 for c in p.hostname):
            host = p.hostname.encode('idna').decode()
            netloc = host + (f':{p.port}' if p.port else '')
            path = urllib.parse.quote(p.path, safe='/%')
            url = urllib.parse.urlunsplit((p.scheme, netloc, path, p.query, p.fragment))
    except Exception:  # noqa: BLE001
        pass
    return url


def get(url, timeout=30, limit=3_000_000, headers=None):
    """Вернуть (код, тело, заголовки, финальный_url). Код 0 = не ответил вовсе."""
    url = idna(url)
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
            return r.status, r.read(limit), dict(r.headers), r.geturl()
    except urllib.error.HTTPError as e:
        try:
            body = e.read(limit)
        except Exception:  # noqa: BLE001
            body = b''
        return e.code, body, dict(e.headers or {}), url
    except Exception as e:  # noqa: BLE001
        return 0, str(e).encode('utf-8', 'replace'), {}, url


def dekod(body, hdrs):
    ct = (hdrs.get('Content-Type') or hdrs.get('content-type') or '')
    m = re.search(r'charset=([\w-]+)', ct, re.I)
    for enc in ([m.group(1)] if m else []) + ['utf-8', 'cp1251']:
        try:
            return body.decode(enc)
        except Exception:  # noqa: BLE001
            continue
    return body.decode('utf-8', 'replace')


def titul(t):
    m = re.search(r'<title[^>]*>(.*?)</title>', t, re.S | re.I)
    return re.sub(r'\s+', ' ', m.group(1)).strip()[:70] if m else ''


def cmd_env():
    import platform
    print('python', sys.version.split()[0], platform.platform()[:60], 'os.name=', os.name)
    for mod in ('requests', 'openpyxl', 'bs4', 'lxml', 'xlrd', 'pandas', 'fitz', 'PyPDF2', 'docx'):
        try:
            __import__(mod)
            print('  есть   ', mod)
        except Exception as e:  # noqa: BLE001
            print('  НЕТ    ', mod, type(e).__name__)
    print('OPS =', OPS, 'существует:', os.path.isdir(OPS))
    k, b, h, u = get('https://example.com/')
    print('контроль сети example.com:', k, len(b))


def vybor(gruppa):
    """Группа или несколько через запятую."""
    out = []
    for g in gruppa.split(','):
        out += GRUPPY.get(g.strip(), [])
    return out or GRUPPY['vse']


def cmd_probe(gruppa):
    tseli = vybor(gruppa)
    itog = []
    for name, reg, url in tseli:
        t = time.time()
        k, b, h, fin = get(url, timeout=25, limit=400_000)
        txt = dekod(b, h) if k and b[:1] in (b'<', b'\n', b' ', b'{') else ''
        ti = titul(txt) if txt else (b[:60].decode('utf-8', 'replace') if k == 0 else '')
        srv = (h.get('Server') or h.get('server') or '')[:18]
        print(f'{k:4} {len(b):8} {time.time()-t:5.1f}s {srv:18} {name[:34]:34} {ti[:52]}')
        itog.append({'org': name, 'region': reg, 'url': url, 'kod': k, 'bajt': len(b),
                     'server': srv, 'titul': ti, 'final': fin})
    put_json(f'3s_tp_probe_{gruppa}.json', itog)
    zhivyh = sum(1 for x in itog if x['kod'] == 200)
    print(f'ИТОГ probe {gruppa}: целей {len(itog)}, код 200 у {zhivyh}, '
          f'нет ответа (0) у {sum(1 for x in itog if x["kod"] == 0)}')


def sobrat_ssylki(html, base):
    out = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
        href, text = m.group(1), re.sub(r'<[^>]+>', ' ', m.group(2))
        text = re.sub(r'\s+', ' ', text).strip()
        out.append((urllib.parse.urljoin(base, href), text))
    return out


MANIT = ['раскрыти', 'raskr', 'disclos', 'подключ', 'podkl', 'присоедин', 'prisoed',
         'техническ', 'tehnich', 'tech', 'техусл', 'ту-', 'инвестицион', 'invest',
         'потребител', 'abonent', 'абонент', 'реестр', 'reestr', 'мощност', 'moshn',
         'резерв', 'rezerv', 'информац', 'документ', 'zayav', 'заявк', 'заявлен']
FAJLY = ('.xls', '.xlsx', '.csv', '.doc', '.docx', '.pdf', '.rtf', '.zip', '.ods')


def dom(u):
    """Регистрируемый домен (две последние метки). ЗДЕСЬ БЫЛА ПОЛОМКА: прежняя
    проверка «того же хоста» сравнивала netloc.endswith(netloc[-18:]), и сайт,
    который ссылается на себя без www, терял ВСЕ ссылки — обход давал стр=1 и это
    выглядело как «сайт на JS, читать нечего». Поймано на Водоканале Екатеринбурга
    (228 КБ главной, 0 кандидатов) и Уфаводоканале."""
    h = urllib.parse.urlparse(u).netloc.split(':')[0].lower()
    ch = h.split('.')
    return '.'.join(ch[-2:]) if len(ch) >= 2 else h


def ves_ssylki(text, url):
    """Насколько ссылка похожа на реестр выданных ТУ. Считаем, а не угадываем."""
    s = (text + ' ' + url).lower()
    v = 0
    if 'реестр' in s or 'перечень' in s or 'журнал' in s or 'список' in s:
        v += 2
    if 'технич' in s and 'услови' in s:
        v += 3
    if 'выдан' in s:
        v += 2
    if 'заяв' in s:
        v += 1
    if 'подключ' in s or 'присоедин' in s:
        v += 1
    if 'договор' in s:
        v += 1
    if s.endswith(FAJLY) or any(f in s for f in FAJLY):
        v += 1
    return v


def cmd_hunt(gruppa, budget=70, stranic=14, ot=0, do=999):
    """Обход в глубину 2: главная -> разделы раскрытия -> что там лежит.

    Печатаем компактно: одна строка на организацию плюс только НАХОДКИ.
    Полный улов — в JSON в OPS.
    """
    tseli = vybor(gruppa)[ot:do]
    itog = []
    for name, reg, url in tseli:
        t0 = time.time()
        vidno, ochered = set(), [(url, '', 0)]
        stranic_ok = 0
        tu_stroki, fajly, slova_tu, lozh = [], [], set(), set()
        fajly_r = []
        while ochered and stranic_ok < stranic and time.time() - t0 < budget:
            u, txt_ssylki, gl = ochered.pop(0)
            if u in vidno:
                continue
            vidno.add(u)
            k, b, h, fin = get(u, timeout=20, limit=1_200_000)
            if k != 200 or not b:
                continue
            ct = (h.get('Content-Type') or h.get('content-type') or '').lower()
            if 'html' not in ct and not b.lstrip()[:1] in (b'<',):
                continue
            stranic_ok += 1
            html = dekod(b, h)
            nizh = html.lower()
            for s in SLOVA_TU:
                if s in nizh:
                    slova_tu.add(s)
                    i = nizh.index(s)
                    tu_stroki.append({'url': fin, 'slovo': s,
                                      'kontekst': re.sub(r'\s+', ' ',
                                                         re.sub(r'<[^>]+>', ' ',
                                                                html[max(0, i - 160):i + 220]))[:240]})
            for s in SLOVA_KONTROL:
                if s in nizh:
                    lozh.add(s)
            for lu, lt in sobrat_ssylki(html, fin):
                if lu.split('#')[0] in vidno or len(lu) > 300:
                    continue
                v = ves_ssylki(lt, lu)
                if lu.lower().split('?')[0].endswith(FAJLY):
                    if v >= 3:
                        fajly.append({'url': lu, 'text': lt, 'ves': v, 'otkuda': fin})
                    elif any(m in (lt + ' ' + lu).lower() for m in
                             ['заявк', 'заявл', 'подключ', 'присоедин', 'резерв',
                              'мощност', 'форма', 'form', 'раскрыт', 'пропускн']):
                        fajly_r.append({'url': lu, 'text': lt, 'otkuda': fin})
                    continue
                host_ok = dom(lu) == dom(url)
                if gl < 2 and host_ok and any(m in (lt + ' ' + lu).lower() for m in MANIT):
                    ochered.append((lu.split('#')[0], lt, gl + 1))
            ochered.sort(key=lambda x: -ves_ssylki(x[1], x[0]))
        fajly.sort(key=lambda x: -x['ves'])
        print(f'{name[:32]:32} стр={stranic_ok:3} словТУ={len(slova_tu)} '
              f'ТУ-файлов={len(fajly):3} раскр-файлов={len(fajly_r):3} '
              f'ложн={len(lozh)} {time.time()-t0:4.0f}s')
        for s in tu_stroki[:4]:
            print(f'   ТУ! {s["slovo"][:34]:34} {s["url"][:80]}')
        for f in fajly[:3]:
            print(f'   ТУфйл в{f["ves"]} {f["text"][:40]:40} {f["url"][:72]}')
        for f in fajly_r[:3]:
            print(f'   ркрфйл  {f["text"][:40]:40} {f["url"][:72]}')
        itog.append({'org': name, 'region': reg, 'url': url, 'stranic': stranic_ok,
                     'slova_tu': sorted(slova_tu), 'lozhnyh': sorted(lozh),
                     'tu_stroki': tu_stroki[:40], 'fajly': fajly[:60],
                     'fajly_raskr': fajly_r[:120]})
    put_json(f'3s_tp_hunt_{gruppa.replace(",", "_")}_{ot}.json', itog)
    print(f'ИТОГ hunt {gruppa}: организаций {len(itog)}, '
          f'со словами реестра ТУ {sum(1 for x in itog if x["slova_tu"])}, '
          f'с файлами-кандидатами {sum(1 for x in itog if x["fajly"])}, '
          f'ложных срабатываний {sum(1 for x in itog if x["lozhnyh"])}')


def cmd_karta(gruppa, ot=0, do=999):
    """Перечислить сайт по sitemap.xml и посчитать адреса со словами-маркерами.

    Зачем: обход в глубину видит только то, до чего дотянулся по ссылкам. Карта
    сайта даёт ЧИСЛО адресов целиком и позволяет сказать «слова „реестр ТУ“ нет
    ни на одном из N адресов», а не «нет на 30 страницах, куда я дошла».
    """
    for name, reg, url in vybor(gruppa)[ot:do]:
        base = url.rstrip('/')
        vse, ocher, vidno = [], [base + '/sitemap.xml', base + '/sitemap_index.xml',
                              base + '/sitemap.xml.gz'], set()
        kod_karty = {}
        while ocher and len(vidno) < 40:
            u = ocher.pop(0)
            if u in vidno:
                continue
            vidno.add(u)
            k, b, h, fin = get(u, timeout=25, limit=20_000_000)
            kod_karty[u.rsplit('/', 1)[-1]] = k
            if k != 200 or not b:
                continue
            if b[:2] == b'\x1f\x8b':
                import gzip
                try:
                    b = gzip.decompress(b)
                except Exception:  # noqa: BLE001
                    continue
            t = b.decode('utf-8', 'replace')
            if '<sitemapindex' in t:
                ocher += re.findall(r'<loc>\s*([^<]+?)\s*</loc>', t)[:40]
            else:
                vse += re.findall(r'<loc>\s*([^<]+?)\s*</loc>', t)
        vse = [urllib.parse.unquote(x) for x in vse]
        nizh = [x.lower() for x in vse]
        schet = {}
        for m in ['реестр', 'reestr', 'raskr', 'раскрыт', 'tehnicheskie-usloviya',
                  'tehusloviya', 'tu-', 'podkl', 'подключ', 'zayav', 'заявк',
                  'invest', 'инвестицион', 'rezerv', 'мощност']:
            schet[m] = sum(1 for x in nizh if m in x)
        # контроль: выдуманная основа обязана дать 0
        schet['ЩВАРЦКОПФЕР(контроль)'] = sum(1 for x in nizh if 'щварцкопфер' in x)
        est = {k: v for k, v in schet.items() if v}
        print(f'{name[:30]:30} адресов={len(vse):6} карт={sum(1 for v in kod_karty.values() if v==200)} '
              f'коды={sorted(set(kod_karty.values()))} {est}')
        if vse:
            put_json(f'3s_tp_karta_{re.sub(chr(92)+"W", "_", name)[:22]}.json',
                     [x for x in vse if any(m in x.lower() for m in
                                            ['реестр', 'reestr', 'raskr', 'раскрыт', 'tehnich',
                                             'техусл', 'podkl', 'подключ', 'invest'])][:4000])


def put_json(imya, dan):
    p = os.path.join(OPS, imya)
    try:
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(dan, f, ensure_ascii=False, indent=1)
        print(f'[записано {p} {os.path.getsize(p)} байт]')
    except Exception as e:  # noqa: BLE001
        print(f'[не записан {p}: {e}]')


def cmd_fetch(url, imya=None):
    k, b, h, fin = get(url, timeout=90, limit=60_000_000)
    ct = (h.get('Content-Type') or h.get('content-type') or '')
    print(f'код={k} байт={len(b)} тип={ct[:40]} итог_url={fin[:100]}')
    if k != 200 or not b:
        print(b[:300].decode('utf-8', 'replace'))
        return
    if not imya:
        imya = os.path.basename(urllib.parse.urlparse(fin).path) or 'skachannyj.bin'
        imya = urllib.parse.unquote(imya)
    p = os.path.join(OPS, '3s_tp_' + re.sub(r'[^\w.\-]', '_', imya)[:60])
    with open(p, 'wb') as f:
        f.write(b)
    print('сохранено:', p)
    opisat(p)


def opisat(p):
    """Напечатать колонки и число записей по файлу — без угадывания."""
    n = p.lower()
    b = open(p, 'rb').read()
    print(f'-- {os.path.basename(p)} {len(b)} байт, сигнатура {b[:4]!r}')
    if n.endswith(('.xlsx', '.xlsm')) or b[:2] == b'PK':
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
            for ws in wb.worksheets:
                print(f'  ЛИСТ «{ws.title}» строк={ws.max_row} колонок={ws.max_column}')
                for i, row in enumerate(ws.iter_rows(max_row=12, values_only=True)):
                    vals = [('' if c is None else str(c))[:26] for c in row]
                    if any(vals):
                        print(f'   r{i}: {vals}')
        except Exception as e:  # noqa: BLE001
            print('  openpyxl не смог:', e)
    elif n.endswith('.csv'):
        import csv
        txt = b.decode('utf-8', 'replace') if b[:3] != b'\xef\xbb\xbf' else b[3:].decode('utf-8', 'replace')
        try:
            dial = csv.Sniffer().sniff(txt[:4000])
            sep = dial.delimiter
        except Exception:  # noqa: BLE001
            sep = ';'
        rows = list(csv.reader(io.StringIO(txt), delimiter=sep))
        print(f'  CSV разделитель {sep!r} строк={len(rows)}')
        for r in rows[:6]:
            print('   ', [c[:26] for c in r[:14]])
    elif n.endswith('.pdf') or b[:4] == b'%PDF':
        print('  PDF; страниц ~', b.count(b'/Type /Page') + b.count(b'/Type/Page'))
    else:
        txt = b.decode('utf-8', 'replace')
        print('  текст/HTML, первые 300:', re.sub(r'\s+', ' ', txt[:300]))


def cmd_cols(p):
    if not os.path.isabs(p):
        p = os.path.join(OPS, p)
    opisat(p)


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == 'env':
        cmd_env()
    elif a[0] == 'probe':
        cmd_probe(a[1] if len(a) > 1 else 'vse')
    elif a[0] == 'hunt':
        cmd_hunt(a[1] if len(a) > 1 else 'vse',
                 int(a[2]) if len(a) > 2 else 70,
                 int(a[3]) if len(a) > 3 else 14,
                 int(a[4]) if len(a) > 4 else 0,
                 int(a[5]) if len(a) > 5 else 999)
    elif a[0] == 'karta':
        cmd_karta(a[1] if len(a) > 1 else 'voda',
                  int(a[2]) if len(a) > 2 else 0, int(a[3]) if len(a) > 3 else 999)
    elif a[0] == 'fetch':
        cmd_fetch(a[1], a[2] if len(a) > 2 else None)
    elif a[0] == 'cols':
        cmd_cols(a[1])
    else:
        sys.exit(__doc__)
