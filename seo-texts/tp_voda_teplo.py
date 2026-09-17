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

# Второй заход по градостроительным системам: адреса, найденные после того как
# первые имена не отозвались, плюс надзорные органы, которые ведут реестры
# разрешений на строительство.
GISOGD2 = [
    ('ГИСОГД РФ / Стройкомплекс', 'РФ', 'https://gisogd.gov.ru/'),
    ('РГИС Подмосковья', 'Подмосковье', 'https://rgis.mosreg.ru/v3/'),
    ('ИСОГД МО (вход)', 'Подмосковье', 'https://isogd.mosreg.ru/'),
    ('ИПП Татарстана (ГИСОГД)', 'Татарстан',
     'https://ipp.tatarstan.ru/gosudarstvennaya-informatsionnaya-sistema.htm'),
    ('Госстройнадзор Татарстана', 'Татарстан', 'https://gsn.tatarstan.ru/'),
    ('Минстрой Свердловской обл.', 'Свердловская', 'https://minstroy.midural.ru/'),
    ('Госстройнадзор Свердловской', 'Свердловская', 'https://nadzor.midural.ru/'),
    ('Минград Нижегородской обл.', 'Нижегородская', 'https://mingrad.government-nnov.ru/'),
    ('Госстройнадзор Краснодарского кр.', 'Краснодарский', 'https://gkn.krasnodar.ru/'),
    ('Минстрой Ростовской обл.', 'Ростовская', 'https://minstroy.donland.ru/'),
    ('Госкомитет РБ по жилнадзору', 'Башкортостан', 'https://gilnadzor.bashkortostan.ru/'),
    ('Мосгосстройнадзор', 'Москва', 'https://www.mos.ru/stroinadzor/'),
    ('Открытые данные Москвы', 'Москва', 'https://data.mos.ru/'),
    ('ЕИСЖС наш.дом.рф', 'РФ', 'https://наш.дом.рф/'),
    ('ЕИСЖС каталог новостроек', 'РФ', 'https://наш.дом.рф/сервисы/каталог-новостроек/'),
]

GRUPPY = {'voda': VODA, 'teplo': TEPLO, 'gisogd': GISOGD, 'kontrol': KONTROL,
          'zapas': ZAPAS, 'gisogd2': GISOGD2}
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
    """Привести адрес к тому, что понимает urllib: хост в punycode, путь и запрос
    в процентной кодировке.

    ЗДЕСЬ БЫЛА ВТОРАЯ ПОЛОМКА ПРИБОРА. Прежняя версия кодировала путь только у
    кириллических ХОСТОВ. У обычного хоста с кириллическим ИМЕНЕМ ФАЙЛА
    (а так выложены почти все формы раскрытия) urllib падал на
    «URL can't contain control characters» или «'ascii' codec can't encode»,
    и функция get() возвращала код 0. Шестнадцать файлов подряд получили «код 0»,
    что читается как «хост не ответил», хотя ЗАПРОСА НЕ БЫЛО ВОВСЕ.
    """
    try:
        p = urllib.parse.urlsplit(url.strip())
        host = p.hostname or ''
        if any(ord(c) > 127 for c in host):
            host = host.encode('idna').decode()
        netloc = host + (f':{p.port}' if p.port else '')
        if p.username:
            netloc = f'{p.username}@{netloc}'
        path = urllib.parse.quote(p.path, safe="/%:@!$&'()*+,;=~")
        query = urllib.parse.quote(p.query, safe="/%:@!$&'()*+,;=?~")
        url = urllib.parse.urlunsplit((p.scheme, netloc, path, query, ''))
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


def cmd_bundle(url, limit=8):
    """Портал на JS и в HTML пусто -> адрес API лежит в его же бандле.

    Забираем <script src>, качаем скрипты и вынимаем из них пути вида /api/...
    Контроль: выдуманная основа обязана дать 0 совпадений.
    """
    k, b, h, fin = get(url, timeout=30, limit=4_000_000)
    print(f'страница код={k} байт={len(b)}')
    if k != 200:
        return
    html = dekod(b, h)
    skripty = [urllib.parse.urljoin(fin, m) for m in
               re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I)]
    vnutri = re.findall(r'["\'](/[a-z0-9_\-/]*(?:api|service|rest|odata|search)[a-z0-9_\-/]*)["\']',
                        html, re.I)
    print(f'скриптов на странице {len(skripty)}, путей прямо в HTML {len(set(vnutri))}')
    puti = set(vnutri)
    for su in skripty[:limit]:
        k2, b2, h2, _ = get(su, timeout=30, limit=12_000_000)
        if k2 != 200:
            print(f'  скрипт код={k2} {su[:90]}')
            continue
        t = b2.decode('utf-8', 'replace')
        n = re.findall(r'["\'](https?://[a-z0-9.\-]+/[^"\' ]{0,80}|/[a-z0-9_\-/]{2,60}'
                       r'(?:api|service|rest|odata|search|layers|permit|razresh)[a-z0-9_\-/]*)["\']',
                       t, re.I)
        nn = {x for x in n if len(x) > 4}
        puti |= nn
        print(f'  скрипт {len(b2):8} байт путей={len(nn):4} {su[-60:]}')
    kontrol = [x for x in puti if 'shvarckopfer' in x.lower()]
    inter = sorted({x for x in puti if any(w in x.lower() for w in
                                           ['api', 'odata', 'rest', 'search', 'razresh',
                                            'permit', 'object', 'registry', 'reestr'])})
    print(f'ВСЕГО путей {len(puti)}, интересных {len(inter)}, контроль(выдуманное)={len(kontrol)}')
    for x in inter[:45]:
        print('   ', x[:120])


def cmd_api(url, prom=''):
    """Дёрнуть JSON-эндпойнт и НАПЕЧАТАТЬ его ключи: сколько записей и какие поля."""
    k, b, h, fin = get(url, timeout=60, limit=25_000_000,
                       headers={'Accept': 'application/json'})
    ct = (h.get('Content-Type') or h.get('content-type') or '')[:40]
    print(f'код={k} байт={len(b)} тип={ct} {fin[:110]}')
    if k == 0 or not b:
        print(b[:200].decode('utf-8', 'replace'))
        return
    try:
        d = json.loads(b.decode('utf-8', 'replace'))
    except Exception as e:  # noqa: BLE001
        print('не JSON:', e, '|', b[:200].decode('utf-8', 'replace'))
        return
    def opis(x, pref='', gl=0):
        if gl > 2:
            return
        if isinstance(x, dict):
            print(f'{pref}объект, ключей {len(x)}: {list(x)[:22]}')
            for k2 in list(x)[:6]:
                if isinstance(x[k2], (dict, list)):
                    opis(x[k2], pref + f'  [{k2}] ', gl + 1)
        elif isinstance(x, list):
            print(f'{pref}список, элементов {len(x)}')
            if x:
                opis(x[0], pref + '  [0] ', gl + 1)
        else:
            print(f'{pref}{type(x).__name__} = {str(x)[:80]}')
    opis(d)
    nz = b.decode('utf-8', 'replace').lower()
    print('слова-заявитель:', [w for w in ZAYAV_SLOVA if w in nz],
          '| контроль:', [w for w in ZAYAV_KONTROL if w in nz])


EISZHS = [
    # ЕИСЖС наш.дом.рф: каталог новостроек. Открытый API портала, адреса взяты
    # из его же фронта. Вопрос к нему тот же: есть ли застройщик и ИНН.
    'https://наш.дом.рф/сервисы/api/kn/object?offset=0&limit=5&sortField=obj_publ_dt'
    '&sortType=desc&objStatus=0',
    'https://наш.дом.рф/сервисы/api/kn/top-regions',
    'https://наш.дом.рф/сервисы/api/kn/developer?offset=0&limit=5&sortField=devShortNm'
    '&sortType=asc&objStatus=0',
]


def razvedka_gisogd():
    """Один заход по градостроительным системам: код, бандл, открытый API."""
    print('### 1. КОДЫ ОТВЕТА')
    cmd_probe('gisogd2')
    print('\n### 2. ЧТО В БАНДЛАХ ПОРТАЛОВ')
    for u in ['https://gisogd.gov.ru/', 'https://gisogd.nso.ru/',
              'https://rgis.mosreg.ru/v3/']:
        print('--- ' + u)
        try:
            cmd_bundle(u, 6)
        except Exception as e:  # noqa: BLE001
            print('  сбой:', type(e).__name__, e)
    print('\n### 3. ОТКРЫТЫЙ API ЕИСЖС наш.дом.рф')
    for u in EISZHS:
        print('--- ' + u[:100])
        try:
            cmd_api(u)
        except Exception as e:  # noqa: BLE001
            print('  сбой:', type(e).__name__, e)
    print('\n### 4. КОНТРОЛЬ: заведомо негодный API')
    cmd_api('https://наш.дом.рф/сервисы/api/kn/shvarckopfer?limit=5')


def cmd_tarif_spb(stranic=60):
    """Реестр актов органа тарифного регулирования (Комитет по тарифам СПб).

    Зачем он в этом участке: индивидуальная плата за подключение к воде/теплу
    устанавливается ПОД КОНКРЕТНЫЙ ОБЪЕКТ, и тогда в заголовке акта может стоять
    заявитель. Меряем: сколько актов всего, сколько про подключение, сколько
    «в индивидуальном порядке», и named ли в них юрлицо-заявитель.
    """
    vse = {}
    for n in range(1, stranic + 1):
        k, b, h, f = get(f'https://tarifspb.ru/documents/acts/?&page={n}',
                         timeout=25, limit=3_000_000)
        if k != 200:
            print(f'стр {n} код={k}')
            break
        t = dekod(b, h)
        d = [(u, tt) for u, tt in sobrat_ssylki(t, f) if re.search(r'/acts/\d+/', u)]
        novyh = sum(1 for u, _ in d if u not in vse)
        vse.update(dict(d))
        if n % 10 == 0 or novyh == 0:
            print(f'стр {n}: документов на странице {len(d)}, новых {novyh}, всего {len(vse)}')
        if novyh == 0:
            break
    nz = {u: re.sub(r'\s+', ' ', t) for u, t in vse.items()}
    def sch(w):
        return sum(1 for t in nz.values() if w in t.lower())
    print(f'ВСЕГО актов собрано: {len(nz)}')
    for w in ['плат', 'подключ', 'индивидуальн', 'водоснабж', 'теплоснабж',
              'общества с ограниченной', 'акционерного общества']:
        print(f'   «{w}»: {sch(w)}')
    print(f'   КОНТРОЛЬ «щварцкопфер»: {sch("щварцкопфер")}')
    ind = [t for t in nz.values() if 'индивидуальн' in t.lower()]
    for t in ind[:10]:
        print('   ИНД:', t[:190])
    put_json('3s_tp_tarifspb_akty.json', [{'url': u, 'text': t} for u, t in nz.items()])


def cmd_samoprover():
    """Самопроверка прибора. Отрицательный контроль показывает, что прибор не
    выдумывает; ПОЛОЖИТЕЛЬНЫЙ показывает, что он вообще срабатывает. Без второго
    ноль по всем сайтам неотличим от сломанного поиска.
    """
    obrazec = ('<html><head><title>Раскрытие</title></head><body>'
               '<h1>Реестр выданных технических условий за 2026 год</h1>'
               '<a href="/files/реестр выданных ТУ 2026.xlsx">Реестр выданных ТУ</a>'
               '<a href="/files/obrazec zayavki.doc">Образец заявки на ТУ</a>'
               '<p>Журнал учета заявлений о подключении</p></body></html>')
    nizh = obrazec.lower()
    nash = [x for x in SLOVA_TU if x in nizh]
    lozh = [x for x in SLOVA_KONTROL if x in nizh]
    print(f'ПОЛОЖИТЕЛЬНЫЙ контроль слов: найдено {len(nash)} из {len(SLOVA_TU)} -> {nash}')
    print(f'ОТРИЦАТЕЛЬНЫЙ контроль слов: найдено {len(lozh)} (должно быть 0)')
    ss = sobrat_ssylki(obrazec, 'https://primer.ru/raskrytie/')
    print(f'ссылок разобрано: {len(ss)} (ожидалось 2)')
    for u, t in ss:
        print(f'   вес={ves_ssylki(t, u)} {t!r} {u}')
    print(f'вес пустышки: {ves_ssylki("Новости компании", "https://primer.ru/news/")} (ожидалось 0)')
    kod, tel, _, _ = get('https://primer-shvarckopfer-0000.ru/')
    print(f'заведомо мёртвый хост -> код {kod} (ожидалось 0)')
    print('idna:', idna('https://a.ru/папка/файл 1.xlsx'))
    ok = (len(nash) >= 3 and not lozh and len(ss) == 2 and kod == 0)
    print('ИТОГ САМОПРОВЕРКИ:', 'прибор исправен' if ok else 'ПРИБОР НЕИСПРАВЕН')


EGRZ_FAJL = os.path.join(
    '/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/scratchpad',
    'KOMPRESSORNYE-EGRZ.jsonl')


def est_zayavitel(shapka_slova, telo=''):
    """ОДИН определитель заявителя на все источники. Вход — имена колонок (и при
    желании тело). Выход — какие признаки заявителя найдены."""
    n = (' '.join(shapka_slova) + ' ' + telo).lower()
    return [w for w in ZAYAV_SLOVA if w in n]


def cmd_kontrol_zayavitelya(put=None):
    """Два контроля ОДНИМ определителем.

    ПОЛОЖИТЕЛЬНЫЙ: выгрузка ЕГРЗ, где застройщик и его ИНН заведомо есть.
    ОТРИЦАТЕЛЬНЫЙ: шапка формы раскрытия по ПП 6/570 (количества заявок и
    мощность), где заявителя заведомо нет.
    Без первого ноль на порталах неотличим от сломанного определителя.
    """
    put = put or EGRZ_FAJL
    zapisi = []
    with open(put, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                zapisi.append(json.loads(line))
    kl = sorted({k for z in zapisi for k in z})
    nash = est_zayavitel(kl)
    imya_ok = sum(1 for z in zapisi if (z.get('zastroyshchik') or '').strip())
    inn_syroj = sum(1 for z in zapisi if str(z.get('zastroyshchik_inn') or '').strip())
    inn_god = sum(1 for z in zapisi
                  if re.fullmatch(r'\d{10}|\d{12}', str(z.get('zastroyshchik_inn') or '').strip()))
    # ловушка из чужого опыта: ИНН, ставший хвостом float
    inn_float = sum(1 for z in zapisi if '.' in str(z.get('zastroyshchik_inn') or ''))
    adres = sum(1 for z in zapisi if (z.get('adres_obekta') or '').strip())
    data = sum(1 for z in zapisi if (z.get('data') or '').strip())
    # не является ли «застройщик» одним и тем же лицом во всех строках
    raznyh = len({(z.get('zastroyshchik') or '').strip().lower() for z in zapisi} - {''})
    print('=== ПОЛОЖИТЕЛЬНЫЙ КОНТРОЛЬ: выгрузка ЕГРЗ')
    print(f'  записей {len(zapisi)}, колонок {len(kl)}')
    print(f'  колонки: {kl}')
    print(f'  определитель заявителя нашёл: {nash}')
    print(f'  наименование застройщика непусто: {imya_ok}  РАЗНЫХ имён: {raznyh}')
    print(f'  ИНН непуст: {inn_syroj}, из них годных (10/12 цифр): {inn_god}, '
          f'с точкой (хвост float): {inn_float}')
    print(f'  адрес объекта: {adres}, дата: {data}')
    print('=== ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: шапка формы раскрытия ПП 6 / ПП 570')
    forma = ['Количество поданных заявок на подключение',
             'Количество исполненных заявок на подключение',
             'Количество заявок с отказом в подключении',
             'Резерв мощности системы теплоснабжения, Гкал/ч',
             'Наименование регулируемой организации', 'Отчётный период']
    n2 = est_zayavitel(forma)
    print(f'  колонки: {forma}')
    print(f'  определитель заявителя нашёл: {n2}')
    print('=== ИТОГ')
    ok = bool(nash) and imya_ok > 400 and inn_god > 400 and raznyh > 100
    print('определитель заявителя ' + ('РАБОТАЕТ' if ok else 'НЕ ДОКАЗАН') +
          f'; на заведомо негодной шапке он даёт {len(n2)} признак(ов) '
          f'({"наименование организации" if n2 else "ничего"}) — '
          'и это ровно та ловушка, о которой предупреждали: «наименование юрлица» '
          'в форме раскрытия это САМА сетевая компания, одна и та же в каждой строке.')


BRAUZER = {
    'User-Agent': UA,
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    'Referer': 'https://xn--80az8a.xn--d1aqf.xn--p1ai/',
    'Origin': 'https://xn--80az8a.xn--d1aqf.xn--p1ai',
    'X-Requested-With': 'XMLHttpRequest',
    'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'empty',
}


def razvedka_gisogd2():
    """Второй заход: три конкретных вопроса, у каждого свой контроль."""
    print('### A. Стройкомплекс.РФ (gisogd.gov.ru) — что на странице и в бандле')
    for popytka in (1, 2):
        k, b, h, f = get('https://gisogd.gov.ru/', timeout=60, limit=6_000_000)
        print(f'  попытка {popytka}: код={k} байт={len(b)}')
        if k == 200 and len(b) > 1000:
            html = dekod(b, h)
            nizh = html.lower()
            for w in ['разрешени на строительств', 'разрешение на строительство', 'застройщик',
                      'реестр', 'поиск', 'ввод в эксплуатац', 'открытые данные', 'щварцкопфер']:
                print(f'    «{w}»: {nizh.count(w)}')
            ss = sobrat_ssylki(html, f)
            print(f'    ссылок {len(ss)}')
            for u, t in ss:
                if any(w in (t + u).lower() for w in ['разреш', 'razresh', 'реестр', 'reestr',
                                                      'открыт', 'opendata', 'api', 'поиск']):
                    print(f'      -> {t[:46]:46} {u[:90]}')
            try:
                cmd_bundle('https://gisogd.gov.ru/', 6)
            except Exception as e:  # noqa: BLE001
                print('    бандл сбой:', type(e).__name__)
            break
    print('\n### B. ЕИСЖС наш.дом.рф с браузерными заголовками')
    proby = [
        ('главная портала', 'https://наш.дом.рф/', {}),
        ('каталог новостроек (HTML)', 'https://наш.дом.рф/сервисы/каталог-новостроек/', {}),
        ('api объектов', 'https://наш.дом.рф/сервисы/api/kn/object?offset=0&limit=5'
         '&sortField=obj_publ_dt&sortType=desc&objStatus=0', BRAUZER),
        ('api застройщиков', 'https://наш.дом.рф/сервисы/api/kn/developer?offset=0&limit=5'
         '&sortField=devShortNm&sortType=asc&objStatus=0', BRAUZER),
        ('КОНТРОЛЬ выдуманный путь', 'https://наш.дом.рф/сервисы/api/kn/shvarckopfer', BRAUZER),
    ]
    for imya, u, hh in proby:
        k, b, h, f = get(u, timeout=45, limit=8_000_000, headers=hh or None)
        ct = (h.get('Content-Type') or h.get('content-type') or '')[:30]
        waf = b'<!-- waf -->' in b[:400]
        print(f'  {imya[:28]:28} код={k:4} байт={len(b):7} тип={ct:28} waf={waf}')
        if k == 200 and b[:1] in (b'{', b'['):
            try:
                d = json.loads(b.decode('utf-8', 'replace'))
                print('    ключи:', list(d)[:14] if isinstance(d, dict) else f'список {len(d)}')
                nz = b.decode('utf-8', 'replace').lower()
                print('    заявитель-слова:', [w for w in ZAYAV_SLOVA if w in nz][:8])
            except Exception as e:  # noqa: BLE001
                print('    не JSON:', type(e).__name__)
    print('\n### C. Открытые данные Москвы: есть ли набор про разрешения на строительство')
    for imya, u in [
        ('поиск «разрешение на строительство»',
         'https://data.mos.ru/opendata?search=%D1%80%D0%B0%D0%B7%D1%80%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D0%B5%20%D0%BD%D0%B0%20%D1%81%D1%82%D1%80%D0%BE%D0%B8%D1%82%D0%B5%D0%BB%D1%8C%D1%81%D1%82%D0%B2%D0%BE'),
        ('КОНТРОЛЬ поиск «щварцкопфер»',
         'https://data.mos.ru/opendata?search=%D1%89%D0%B2%D0%B0%D1%80%D1%86%D0%BA%D0%BE%D0%BF%D1%84%D0%B5%D1%80'),
    ]:
        k, b, h, f = get(u, timeout=45, limit=6_000_000)
        t = dekod(b, h) if k == 200 else ''
        print(f'  {imya[:40]:40} код={k} байт={len(b)} '
              f'«разрешен»={t.lower().count("разрешен")} «набор»={t.lower().count("набор")}')


GISOGD3 = [
    ('РИСОГД Пермского края', 'Пермский', 'https://isogd.permkrai.ru/'),
    ('ИСОГД Курганской обл.', 'Курганская', 'https://isogd.gov45.ru/'),
    ('Стройкомплекс.РФ', 'РФ', 'https://xn--e1ahdbdflckekkc.xn--p1ai/'),
    ('ГИСОГД Пермского края (публ.)', 'Пермский', 'https://isogd.permkrai.ru/publicservices/'),
    ('ИСОГД Курганской (публ. сервисы)', 'Курганская', 'https://isogd.gov45.ru/publicservices/'),
    ('КОНТРОЛЬ несуществующий ИСОГД', '-', 'https://isogd-shvarckopfer-999.ru/'),
]


def razvedka_gisogd3():
    """Третий заход: публичные градостроительные порталы, где по описанию
    производителя есть СЕРВИС РАЗРЕШЕНИЙ НА СТРОИТЕЛЬСТВО со связанным застройщиком.
    Проверяем, виден ли застройщик БЕЗ входа.
    """
    for name, reg, url in GISOGD3:
        k, b, h, f = get(url, timeout=45, limit=6_000_000)
        if k != 200 or not b:
            print(f'{name[:34]:34} код={k:4} байт={len(b)} {b[:60].decode("utf-8", "replace")}')
            continue
        t = dekod(b, h)
        nizh = t.lower()
        slova = {w: nizh.count(w) for w in
                 ['разрешени на строительство', 'разрешение на строительство', 'застройщик',
                  'ввод в эксплуатац', 'реестр', 'авторизац', 'войти', 'есиа', 'щварцкопфер']
                 if nizh.count(w)}
        print(f'{name[:34]:34} код=200 байт={len(b):7} титул={titul(t)[:40]:40} {slova}')
        ss = sobrat_ssylki(t, f)
        interes = [(u, x) for u, x in ss
                   if any(w in (x + u).lower() for w in
                          ['разреш', 'razresh', 'permit', 'реестр', 'reestr', 'сервис',
                           'service', 'поиск', 'search', 'публичн', 'public', 'данн'])]
        print(f'   ссылок {len(ss)}, интересных {len(interes)}')
        for u, x in interes[:10]:
            print(f'      -> {x[:42]:42} {u[:86]}')
        # один шаг вглубь по самой похожей ссылке
        for u, x in interes[:3]:
            k2, b2, h2, f2 = get(u, timeout=40, limit=6_000_000)
            if k2 != 200:
                print(f'      вглубь код={k2} {u[:70]}')
                continue
            t2 = dekod(b2, h2).lower()
            print(f'      вглубь 200 байт={len(b2):7} застройщик={t2.count("застройщик")} '
                  f'разрешен={t2.count("разрешен")} инн={t2.count("инн")} '
                  f'контроль={t2.count("щварцкопфер")} {u[:60]}')
    print('\n### Стройкомплекс.РФ (gisogd.gov.ru) с коротким чтением')
    for lim in (150_000, 400_000):
        k, b, h, f = get('https://gisogd.gov.ru/', timeout=90, limit=lim)
        print(f'  предел чтения {lim}: код={k} байт={len(b)}')
        if k == 200 and len(b) > 2000:
            t = dekod(b, h).lower()
            print('   ', {w: t.count(w) for w in
                          ['разрешени', 'застройщик', 'реестр', 'витрин', 'открытые данные',
                           'щварцкопфер'] if t.count(w)})
            break
    print('\n### Открытые данные Москвы: сам API, а не страница поиска')
    for imya, u in [
        ('apidata без ключа', 'https://apidata.mos.ru/v1/datasets?$top=3'),
        ('apidata счёт наборов', 'https://apidata.mos.ru/v1/datasets/count'),
        ('КОНТРОЛЬ выдуманный путь', 'https://apidata.mos.ru/v1/shvarckopfer'),
    ]:
        k, b, h, f = get(u, timeout=45, limit=2_000_000,
                         headers={'Accept': 'application/json'})
        print(f'  {imya[:26]:26} код={k:4} байт={len(b):7} '
              f'тело={b[:90].decode("utf-8", "replace")!r}')


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


# Слова, по которым узнаём ЗАЯВИТЕЛЯ в шапке. Латиница здесь не для красоты:
# положительный контроль на выгрузке ЕГРЗ ПРОВАЛИЛСЯ именно потому, что там
# колонки транслитом (`zastroyshchik`, `zastroyshchik_inn`), а список был только
# кириллический. То есть определитель молча не видел бы заявителя в любой
# выгрузке с латинскими именами полей.
ZAYAV_SLOVA = ['заявител', 'застройщик', 'наименование юридического',
               'наименование заявителя', 'наименование организации', 'инн',
               'объект капитального', 'наименование объекта', 'адрес объекта',
               'правообладател', 'фио', 'ф.и.о', 'контрагент', 'абонент',
               'zayavitel', 'zastroyshchik', 'zastroishchik', 'inn', 'obekt',
               'adres', 'kontragent', 'abonent', 'developer', 'applicant']
ZAYAV_KONTROL = ['щварцкопфер', 'зюзюблик']


def shapka_fajla(b, imya):
    """Вернуть (тип, число_записей, список_колонок, сырой_текст_для_поиска)."""
    n = imya.lower()
    if b[:2] == b'PK' and (n.endswith(('.xlsx', '.xlsm')) or True):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
            kol, zap, syr = [], 0, []
            for ws in wb.worksheets:
                # ЗДЕСЬ БЫЛА ЧЕТВЁРТАЯ ПОЛОМКА ПРИБОРА. Считалось ws.max_row —
                # ОБЪЯВЛЕННЫЙ размер листа. Файл «Форма 22» ГУП ТЭК СПб получил
                # «записей 1 048 638», потому что один лист объявляет предел Excel
                # (1 048 576), а непустых строк в книге РЕАЛЬНО 70. Крупное число
                # оказалось свойством прибора, а не источника.
                n = 0
                try:
                    for row in ws.iter_rows(values_only=True):
                        if any(c not in (None, '') for c in row):
                            n += 1
                        if n > 20000:
                            break
                except Exception:  # noqa: BLE001
                    n = 0
                zap += n
                for i, row in enumerate(ws.iter_rows(max_row=14, values_only=True)):
                    vals = [('' if c is None else str(c)) for c in row]
                    syr += vals
                    if sum(1 for v in vals if v.strip()) >= 2 and len(kol) < 40:
                        kol.append(f'[{ws.title[:12]} r{i}] ' +
                                   ' | '.join(v[:34] for v in vals if v.strip())[:300])
            return 'xlsx', zap, kol, ' '.join(syr)
        except Exception as e:  # noqa: BLE001
            return 'xlsx-сбой:' + type(e).__name__, 0, [], ''
    if b[:4] == b'%PDF':
        try:
            import fitz
            d = fitz.open(stream=b, filetype='pdf')
            t = '\n'.join(d[i].get_text() for i in range(min(6, d.page_count)))
            return 'pdf', d.page_count, [re.sub(r'\s+', ' ', x)[:160]
                                         for x in t.split('\n') if x.strip()][:25], t
        except Exception as e:  # noqa: BLE001
            return 'pdf-сбой:' + type(e).__name__, 0, [], ''
    if b[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        t = b.decode('cp1251', 'ignore')
        return 'doc/xls-ole', 0, [], t
    t = b.decode('utf-8', 'replace')
    if '<' in t[:200]:
        t2 = re.sub(r'<[^>]+>', ' ', t)
        return 'html', t.lower().count('<tr'), [re.sub(r'\s+', ' ', t2)[:200]], t2
    return 'txt', t.count(chr(10)), [t[:200]], t


def cmd_razbor(imya_json, limit=14, tolko=''):
    """Скачать найденные файлы и НАПЕЧАТАТЬ КОЛОНКИ. Ключевой вопрос — есть ли
    в шапке заявитель/застройщик/ИНН, или там только числа сетевой организации."""
    put = imya_json if os.path.isabs(imya_json) else os.path.join(OPS, imya_json)
    dan = json.load(open(put, encoding='utf-8'))
    kand = []
    for o in dan:
        for f in (o.get('fajly') or []) + (o.get('fajly_raskr') or []):
            s_ = (f.get('text', '') + ' ' + f['url']).lower()
            v = 0
            if any(w in s_ for w in ['реестр', 'журнал', 'перечень', 'форма', 'свод',
                                     'информац', 'сведени']):
                v += 2
            if any(w in s_ for w in ['заявк', 'заявлен', 'подключ', 'присоедин']):
                v += 2
            if any(w in s_ for w in ['резерв', 'мощност', 'пропускн']):
                v += 2
            if any(w in s_ for w in ['инвестицион', 'адресн', 'мероприят']):
                v += 2
            if s_.split('?')[0].endswith(('.xlsx', '.xls', '.csv', '.ods')):
                v += 3
            if 'образец' in s_ or 'бланк' in s_ or 'пример' in s_ or 'типов' in s_:
                v -= 3
            if tolko and tolko.lower() not in o['org'].lower():
                continue
            kand.append((v, o['org'], f.get('text', '')[:44], f['url']))
    kand.sort(key=lambda x: -x[0])
    vidno, n = set(), 0
    for v, org, text, u in kand:
        if u in vidno or n >= limit:
            continue
        vidno.add(u)
        n += 1
        k, b, h, fin = get(u, timeout=60, limit=25_000_000)
        if k != 200 or not b:
            print(f'в{v} {org[:20]:20} код={k} {text[:30]:30} {u[:56]} '
                  f'|{b[:70].decode("utf-8", "replace")}|')
            continue
        tip, zap, kol, syr = shapka_fajla(b, urllib.parse.unquote(u))
        nz = syr.lower()
        est = [w for w in ZAYAV_SLOVA if w in nz]
        kontr = [w for w in ZAYAV_KONTROL if w in nz]
        print(f'в{v} {org[:18]:18} {tip:10} байт={len(b):8} записей={zap:5} '
              f'заявитель-слова={est} контроль={kontr} :: {text[:34]}')
        for c in kol[:5]:
            print('      ' + c[:150])
    print(f'ИТОГ razbor {imya_json}: кандидатов {len(kand)}, разобрано {n}')


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
    elif a[0] == 'kontrol':
        cmd_kontrol_zayavitelya(a[1] if len(a) > 1 else None)
    elif a[0] == 'samoprover':
        cmd_samoprover()
    elif a[0] == 'tarifspb':
        cmd_tarif_spb(int(a[1]) if len(a) > 1 else 60)
    elif a[0] == 'gisogd3':
        razvedka_gisogd3()
    elif a[0] == 'gisogd2':
        razvedka_gisogd2()
    elif a[0] == 'gisogd':
        razvedka_gisogd()
    elif a[0] == 'bundle':
        cmd_bundle(a[1], int(a[2]) if len(a) > 2 else 8)
    elif a[0] == 'api':
        cmd_api(a[1])
    elif a[0] == 'razbor':
        cmd_razbor(a[1], int(a[2]) if len(a) > 2 else 14, a[3] if len(a) > 3 else '')
    elif a[0] == 'cols':
        cmd_cols(a[1])
    else:
        sys.exit(__doc__)
