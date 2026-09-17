# -*- coding: utf-8 -*-
"""Раскрытие информации газораспределительных организаций: назван ли ЗАЯВИТЕЛЬ.

ЗАЧЕМ. Заявка на подключение к газу подаётся ДО стройки. Если предприятие просит
газ под новое производство, компрессоры и азот понадобятся ему следом. Вопрос,
на который отвечает этот прибор, ровно один: **есть ли в публичных формах
раскрытия ГРО наименование и ИНН заявителя-юрлица**, или там только сеть и деньги.

ЧТО БЫЛО ИЗВЕСТНО ДО. Предыдущий замер (RANNIE-ISTOCHNIKI-OPIS.md, раздел 3.3)
сделан по ОДНОЙ организации - приложение 6 форма 1 у «Газпром газораспределение
Ставрополь» - и дал «заявитель не назван». Одна организация это не замер: формы
раскрытия у ГРО не одна, а больше десятка, и заявки ЮРЛИЦ часто лежат отдельно
от заявок населения.

ЧТО ДЕЛАЕТ ЭТОТ СКРИПТ.
  hosty     - опрос доменов ГРО с двух слоёв. Код ответа это ОТВЕТ; недоступен
              только тот, кто не ответил вовсе (код 0). Контроли встроены.
  razdely   - обход раздела раскрытия ЦЕЛИКОМ (обход в ширину по своему домену),
              сбор ВСЕХ ссылок на файлы и их подписей.
  fayl      - разбор одного файла: имена листов, число строк, ИМЕНА КОЛОНОК
              ДОСЛОВНО, и признаки заявителя (ИНН, юрлицо, адрес, объём, дата).
  razbor    - то же пакетом по всем собранным файлам организации.
  svodka    - итоговая таблица «организация -> форма -> строк -> заявитель».

ЯМЫ, которые прибор обязан обходить (все три пойманы на живых данных прошлой
сессией и проверены здесь заново):
  1. «\\d{10}» ловит хвост float в стоимости (2204394.4900000002 -> 4900000002).
     Настоящий ИНН стоит ОТДЕЛЬНЫМ полем, поэтому ИНН считается по колонке,
     а не по всему тексту, и дополнительно проверяется контрольной суммой.
  2. «наименование юрлица» в выгрузке часто оказывается САМОЙ газовой компанией
     в каждой строке. Поэтому имя организации-владельца формы вычитается.
  3. даты в сыром xlsx лежат СЕРИЙНЫМ числом Excel (46239 = 05.08.2026), поиск
     по «20\\d\\d-\\d\\d-\\d\\d» честно находит ноль при заполненных датах.
  4. Ноль надо ДОКАЗАТЬ: скрипт печатает полный список имён колонок, то есть
     показывает, что колонки нет ВОВСЕ, а не что она пуста в первых строках.

ЗАПУСК (из песочницы):
    python3 seo-texts/tp_gaz.py hosty
    python3 seo-texts/tp_gaz.py razdely 34gaz stavkraygaz
    python3 seo-texts/tp_gaz.py fayl https://.../forma.xlsx
    python3 seo-texts/tp_gaz.py razbor 34gaz
    python3 seo-texts/tp_gaz.py svodka
ЗАПУСК (на сервере владельца, российский IP - открывает то, что закрыто здесь):
    python3 seo-texts/zapusk_na_servere.py seo-texts/tp_gaz.py hosty
"""
import datetime
import io
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

# Куда складывать выгрузки. В песочнице - scratchpad, на сервере - временный каталог.
_SCRATCH = '/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/scratchpad'
KATALOG = os.environ.get('TP_GAZ_DIR') or (_SCRATCH if os.path.isdir(_SCRATCH)
                                           else os.path.join(os.path.abspath(os.sep), 'tmp'))
try:
    os.makedirs(KATALOG, exist_ok=True)
except Exception:  # noqa: BLE001
    KATALOG = '.'
SOSTOYANIE = os.path.join(KATALOG, 'tp-gaz-sostoyanie.json')

# Заведомо негодный вход для контролей. Слово не встречается ни в одной выгрузке.
KONTROL_SLOVO = 'щварцкопфер'
KONTROL_HOST = 'https://shvartskopfer-net-takogo-gaza.ru/'

# ---------------------------------------------------------------------------
# Организации. `imya` нужно, чтобы вычесть САМУ газовую компанию из «юрлиц»
# (яма 2). `zerna` - куски имени, по которым строка признаётся строкой владельца.
# ---------------------------------------------------------------------------
ORG = [
    dict(k='mosoblgaz',   dom='mosoblgaz.ru',        region='Московская обл.',
         imya='АО «Мособлгаз»', zerna=['мособлгаз']),
    dict(k='mosgaz',      dom='mosgaz.ru',           region='Москва',
         imya='АО «МОСГАЗ»', zerna=['мосгаз']),
    dict(k='gazmsk',      dom='gazmsk.ru',           region='Москва (межрегионгаз)',
         imya='ООО «Газпром межрегионгаз Москва»', zerna=['межрегионгаз', 'газпром']),
    dict(k='lenobl',      dom='gazprom-lenobl.ru',   region='Ленинградская обл.',
         imya='АО «Газпром газораспределение Ленинградская область»',
         zerna=['газораспределение', 'газпром']),
    dict(k='nn',          dom='gazprom-nn.ru',       region='Нижегородская обл.',
         imya='ПАО «Газпром газораспределение Нижний Новгород»',
         zerna=['газораспределение', 'газпром']),
    dict(k='rostov',      dom='rostovoblgaz.ru',     region='Ростовская обл.',
         imya='ПАО «Газпром газораспределение Ростов-на-Дону»',
         zerna=['газораспределение', 'газпром', 'ростовоблгаз']),
    dict(k='krasnodar',   dom='gazpromgk.ru',        region='Краснодарский край',
         imya='АО «Газпром газораспределение Краснодар»',
         zerna=['газораспределение', 'газпром']),
    dict(k='samara',      dom='svgk.ru',             region='Самарская обл.',
         imya='ООО «Газпром газораспределение Самара» (СВГК)',
         zerna=['газораспределение', 'газпром', 'свгк', 'средневолжск']),
    dict(k='kazan',       dom='kazan-tr.gazprom.ru', region='Татарстан',
         imya='ООО «Газпром трансгаз Казань» (ГРО Татарстана)',
         zerna=['трансгаз', 'газпром', 'казаньгоргаз']),
    dict(k='tatarstan2',  dom='mrg.tatar.ru',        region='Татарстан (межрегионгаз)',
         imya='АО «Газпром межрегионгаз Казань»',
         zerna=['межрегионгаз', 'газпром']),
    dict(k='nn2',         dom='ngaz.ru',             region='Нижегородская обл.',
         imya='ПАО «Газпром газораспределение Нижний Новгород»',
         zerna=['газораспределение', 'газпром', 'нижегородоблгаз']),
    dict(k='ufa',         dom='bashgaz.ru',          region='Башкортостан',
         imya='ПАО «Газпром газораспределение Уфа»',
         zerna=['газораспределение', 'газпром']),
    dict(k='gazeks',      dom='gazeks.com',          region='Свердловская обл.',
         imya='АО «ГАЗЭКС»', zerna=['газэкс', 'газекс']),
    dict(k='volgograd',   dom='34gaz.ru',            region='Волгоградская обл.',
         imya='ООО «Газпром газораспределение Волгоград»',
         zerna=['газораспределение', 'газпром']),
    dict(k='stavropol',   dom='stavkraygaz.ru',      region='Ставропольский край',
         imya='АО «Газпром газораспределение Ставрополь»',
         zerna=['газораспределение', 'газпром', 'ставрополькрайгаз']),
    dict(k='voronezh',    dom='gazpromvrn.ru',       region='Воронежская обл.',
         imya='ОАО «Газпром газораспределение Воронеж»',
         zerna=['газораспределение', 'газпром']),
    dict(k='sever',       dom='sever04.ru',          region='Тюмень/ХМАО/ЯНАО',
         imya='АО «Газпром газораспределение Север»',
         zerna=['газораспределение', 'газпром']),
    dict(k='arhangelsk',  dom='arhgpgr.ru',          region='Архангельская обл.',
         imya='ООО «Газпром газораспределение Архангельск»',
         zerna=['газораспределение', 'газпром']),
    dict(k='dv',          dom='gazdv.ru',            region='Дальний Восток',
         imya='АО «Газпром газораспределение Дальний Восток»',
         zerna=['газораспределение', 'газпром']),
    dict(k='mrg',         dom='mrg.gazprom.ru',      region='РФ (межрегионгаз)',
         imya='ООО «Газпром межрегионгаз»', zerna=['межрегионгаз', 'газпром']),
    dict(k='golovnaya',   dom='gazoraspredelenie.gazprom.ru', region='РФ (головная ГРО)',
         imya='АО «Газпром газораспределение»', zerna=['газораспределение', 'газпром']),
    dict(k='eog',         dom='connectgas.ru',       region='РФ (Единый оператор газификации)',
         imya='Единый оператор газификации', zerna=['единый оператор', 'газпром']),
]
PO_KLYUCHU = {o['k']: o for o in ORG}

# Запасные домены: если основной не отвечает, пробуем эти (имя ГРО угадать нельзя,
# поэтому кандидаты перечислены явно и каждый проверяется кодом ответа).
ZAPASNYE = {
    'nn': ['gazprom-nn.ru', 'www.gazprom-nn.ru', 'ngaz.ru', 'nnovgaz.ru'],
    'kazan': ['kazan-tr.gazprom.ru', 'tattg.gazprom.ru'],
    'tatarstan2': ['mrg.tatar.ru', 'www.mrg.tatar.ru'],
    'krasnodar': ['gazpromgk.ru', 'www.gazpromgk.ru'],
    'rostov': ['rostovoblgaz.ru', 'www.rostovoblgaz.ru', 'gazprom-rostov.ru'],
    'mosoblgaz': ['mosoblgaz.ru', 'www.mosoblgaz.ru'],
    'mosgaz': ['mosgaz.ru', 'www.mosgaz.ru'],
    'samara': ['svgk.ru', 'www.svgk.ru', 'svgc.ru'],
    'ufa': ['bashgaz.ru', 'www.bashgaz.ru'],
}

# ---------------------------------------------------------------------------
# Сеть
# ---------------------------------------------------------------------------


def vzyat(url, timeout=60, predel=40_000_000, redirect=True):
    """Возвращает (kod, telo, konechnyy_url). kod=0 значит «не ответил вовсе»."""
    klass = urllib.request.HTTPRedirectHandler if redirect else _BezRedirekta
    op = urllib.request.build_opener(klass)
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': UA, 'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9', 'Accept-Encoding': 'identity'})
        with op.open(req, timeout=timeout) as f:
            return f.status, f.read(predel), f.geturl()
    except urllib.error.HTTPError as e:
        telo = b''
        try:
            telo = e.read(4000) if e.fp else b''
        except Exception:  # noqa: BLE001
            pass
        return e.code, telo, (e.headers.get('Location') or url) if e.headers else url
    except Exception as e:  # noqa: BLE001
        # Российский корневой сертификат (НУЦ Минцифры) не лежит в нашем хранилище,
        # поэтому часть сайтов ГРО даёт CERTIFICATE_VERIFY_FAILED. Это ОТВЕТ хоста,
        # а не отсутствие хоста. Проверку TLS не отключаем - пробуем тот же адрес
        # по http, и в отчёте такой случай помечается отдельно.
        if 'CERTIFICATE_VERIFY_FAILED' in str(e) and url.startswith('https://'):
            k, t, u = vzyat('http://' + url[8:], timeout=timeout, predel=predel,
                            redirect=redirect)
            if k:
                return k, t, u
        return 0, ('%s: %s' % (type(e).__name__, e)).encode(), url


class _BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):  # noqa: D102
        return None


def v_tekst(telo):
    """HTML -> текст. Кодировку берём из мета-тега, иначе utf-8, иначе cp1251."""
    proba = telo[:3000].decode('latin-1', 'replace').lower()
    if 'charset=windows-1251' in proba or 'charset=cp1251' in proba:
        return telo.decode('cp1251', 'replace')
    try:
        return telo.decode('utf-8')
    except UnicodeDecodeError:
        return telo.decode('cp1251', 'replace')


# ---------------------------------------------------------------------------
# Обход раздела раскрытия
# ---------------------------------------------------------------------------
SLOVA_RAZDELA = ('раскрыт', 'disclos', 'raskryt', 'raskritie', 'информац', 'information',
                 'подключен', 'присоедин', 'podklyuch', 'tehprisoedinenie', 'заявк',
                 'zayav', 'реестр', 'reestr', 'договор', 'dogovor', '872', '1547',
                 'мощност', 'moshchnost', 'догазификац', 'dogazifik', 'потребител',
                 'юридическ', 'standart', 'стандарт', 'тариф')
RASSHIRENIYA = ('.xlsx', '.xls', '.xlsm', '.csv', '.pdf', '.doc', '.docx', '.rtf',
                '.zip', '.rar', '.ods')


def ssylki(html, baza):
    """Все <a href> с подписью. Подпись чистим от тегов и пробелов."""
    out = []
    for m in re.finditer(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                         html, re.S | re.I):
        adr = urllib.parse.urljoin(baza, m.group(1).strip())
        podpis = re.sub(r'<[^>]+>', ' ', m.group(2))
        podpis = re.sub(r'\s+', ' ', podpis).strip()[:220]
        out.append((adr, podpis))
    # файлы бывают и не в <a>: в data-атрибутах, в js-массивах
    for m in re.finditer(r'["\']([^"\'\s<>]+\.(?:xlsx|xls|xlsm|csv|pdf|docx?|rtf|ods))["\']',
                         html, re.I):
        out.append((urllib.parse.urljoin(baza, m.group(1)), ''))
    return out


def obhod(dom, predel_stranic=45, pauza=0.4, log=print):
    """Обход в ширину по своему домену вокруг раздела раскрытия.

    Возвращает dict: stranicy (adres -> (kod, razmer, zagolovok)), fayly (adres -> podpis).
    """
    baza = 'https://' + dom
    ochered = [baza + '/']
    for p in ('/about/disclosure/', '/raskrytie-informacii/', '/disclosure/',
              '/info/raskrytie/', '/raskrytie/', '/about/raskrytie-informatsii/',
              '/information-disclosure/', '/company/disclosure/'):
        ochered.append(baza + p)
    vidno, stranicy, fayly = set(), {}, {}
    while ochered and len(stranicy) < predel_stranic:
        adr = ochered.pop(0)
        if adr in vidno:
            continue
        vidno.add(adr)
        kod, telo, kon = vzyat(adr, timeout=45, predel=4_000_000)
        if kod != 200 or not telo:
            stranicy[adr] = (kod, len(telo), '')
            continue
        html = v_tekst(telo)
        zag = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
        zag = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', zag.group(1))).strip()[:90] if zag else ''
        stranicy[adr] = (kod, len(telo), zag)
        for a, podpis in ssylki(html, kon):
            a = a.split('#')[0]
            if not a.startswith('http'):
                continue
            hozyain = urllib.parse.urlparse(a).netloc.lower()
            if dom.lower().lstrip('www.') not in hozyain:
                continue
            nizh = urllib.parse.unquote(a).lower() + ' ' + podpis.lower()
            if a.lower().endswith(RASSHIRENIYA):
                if a not in fayly or (podpis and not fayly[a]):
                    fayly[a] = podpis
            elif (a not in vidno and len(ochered) < 400
                  and any(s in nizh for s in SLOVA_RAZDELA)):
                ochered.append(a)
        time.sleep(pauza)
    return dict(stranicy=stranicy, fayly=fayly)


# ---------------------------------------------------------------------------
# Чтение таблиц: xlsx (zip+xml), xls (OLE+BIFF8), csv
# ---------------------------------------------------------------------------
def _kolonka_v_nomer(ref):
    """'BC12' -> 54 (0-based индекс колонки)."""
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return max(n - 1, 0)


def listy_xlsx(telo):
    """[(imya_lista, [stroka, ...]), ...]. Позиции колонок сохраняются по r=.

    Пустые ячейки не съедаются: без учёта атрибута r= колонки съезжают и
    «колонки нет» нельзя отличить от «колонка пустая».
    """
    z = zipfile.ZipFile(io.BytesIO(telo))
    imena = z.namelist()
    obshchie = []
    if 'xl/sharedStrings.xml' in imena:
        x = z.read('xl/sharedStrings.xml').decode('utf-8', 'replace')
        for m in re.findall(r'<si>(.*?)</si>', x, re.S):
            obshchie.append(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m)).strip())
    podpisi = {}
    if 'xl/workbook.xml' in imena:
        wb = z.read('xl/workbook.xml').decode('utf-8', 'replace')
        for i, m in enumerate(re.finditer(r'<sheet\b[^>]*name="([^"]*)"', wb)):
            podpisi[i] = m.group(1)
    rezult = []
    poteri = [0]
    listy = sorted(n for n in imena if re.match(r'xl/worksheets/sheet\d+\.xml$', n))
    for i, imya in enumerate(listy):
        x = z.read(imya).decode('utf-8', 'replace')
        stroki = []
        for rm in re.findall(r'<row[^>]*>(.*?)</row>', x, re.S):
            yach = {}
            # ЯМА, из-за которой прибор врал НУЛЁМ. Было: `<c\b([^>]*)(?:/>|>(.*?)</c>)`.
            # На пустой ячейке `<c r="B11" s="67"/>` жадное `[^>]*` съедало и слэш,
            # ветка `/>` не срабатывала, и вторая ветка `>(.*?)</c>` глотала ВСЁ до
            # следующего `</c>` - то есть пачку ячеек целиком. В строке из 167 ячеек
            # разбиралось 30, колонки съезжали, шапка исчезала, и лист честно
            # показывал «колонки ИНН нет вовсе» при живой шапке в файле.
            # Лечится одним знаком: ленивое `[^>]*?`.
            yacheek_v_syrye = rm.count('<c ')
            for cm in re.finditer(r'<c\b([^>]*?)(?:/>|>(.*?)</c>)', rm, re.S):
                atr, telo_y = cm.group(1), cm.group(2) or ''
                rm2 = re.search(r'r="([A-Z]+)\d*"', atr)
                nom = _kolonka_v_nomer(rm2.group(1)) if rm2 else len(yach)
                tm = re.search(r't="(\w+)"', atr)
                tip = tm.group(1) if tm else 'n'
                if tip == 'inlineStr':
                    zn = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', telo_y)).strip()
                else:
                    v = re.search(r'<v>(.*?)</v>', telo_y, re.S)
                    zn = v.group(1) if v else ''
                    if tip == 's' and zn.isdigit() and int(zn) < len(obshchie):
                        zn = obshchie[int(zn)]
                yach[nom] = zn
            # КОНТРОЛЬ ПРИБОРА: разобранных ячеек должно быть столько же, сколько
            # их в сыром XML. Расхождение печатается, а не проглатывается.
            if yacheek_v_syrye and len(yach) < yacheek_v_syrye:
                poteri[0] += yacheek_v_syrye - len(yach)
            stroki.append([yach.get(j, '') for j in range(max(yach) + 1)] if yach else [])
        rezult.append((podpisi.get(i, imya), stroki))
    if poteri[0]:
        print('   !! ПРИБОР ПОТЕРЯЛ %d ячеек при разборе xlsx - разбору не верить'
              % poteri[0])
    return rezult


# --- .xls: составной файл OLE2 + записи BIFF8 -------------------------------
def _ole_potok(telo, imya_potoka='Workbook'):
    """Достаёт поток из составного документа OLE2 (CFB). None, если не вышло."""
    if telo[:8] != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return None
    razm = 1 << struct.unpack('<H', telo[30:32])[0]
    mrazm = 1 << struct.unpack('<H', telo[32:34])[0]
    n_fat = struct.unpack('<I', telo[44:48])[0]
    dir_start = struct.unpack('<I', telo[48:52])[0]
    mini_start = struct.unpack('<I', telo[60:64])[0]
    difat_start, n_difat = struct.unpack('<II', telo[68:76])
    def sektor(i):
        n = 512 + i * razm
        return telo[n:n + razm]
    # DIFAT -> номера секторов FAT
    fat_sekt = [struct.unpack('<I', telo[76 + 4 * i:80 + 4 * i])[0] for i in range(109)]
    s = difat_start
    for _ in range(n_difat):
        if s in (0xFFFFFFFE, 0xFFFFFFFF):
            break
        blok = sektor(s)
        fat_sekt += [struct.unpack('<I', blok[4 * i:4 * i + 4])[0]
                     for i in range((razm // 4) - 1)]
        s = struct.unpack('<I', blok[-4:])[0]
    fat = []
    for i in fat_sekt[:max(n_fat, 1) + 200]:
        if i >= 0xFFFFFFFA:
            continue
        b = sektor(i)
        fat += [struct.unpack('<I', b[4 * j:4 * j + 4])[0] for j in range(razm // 4)]
    def cepochka(nach, fat_tabl):
        out, cur, shchit = [], nach, 0
        while cur < 0xFFFFFFFA and shchit < 1_000_000:
            out.append(cur)
            cur = fat_tabl[cur] if cur < len(fat_tabl) else 0xFFFFFFFE
            shchit += 1
        return out
    katalog = b''.join(sektor(i) for i in cepochka(dir_start, fat))
    nayden = None
    zapisi = []
    for i in range(0, len(katalog) - 127, 128):
        z = katalog[i:i + 128]
        dlina = struct.unpack('<H', z[64:66])[0]
        imya = z[:max(dlina - 2, 0)].decode('utf-16-le', 'replace')
        nach = struct.unpack('<I', z[116:120])[0]
        razmer = struct.unpack('<I', z[120:124])[0]
        zapisi.append((imya, nach, razmer, z[66]))
        if imya.strip('\x05 ').lower() == imya_potoka.lower():
            nayden = (nach, razmer)
    if not nayden:
        for imya, nach, razmer, _t in zapisi:
            if 'book' in imya.lower():
                nayden = (nach, razmer)
                break
    if not nayden:
        return None
    nach, razmer = nayden
    if razmer >= 4096:
        return b''.join(sektor(i) for i in cepochka(nach, fat))[:razmer]
    # мини-поток: для файлов меньше 4096 байт данные лежат в mini-FAT
    mini_fat = []
    for i in cepochka(mini_start, fat):
        b = sektor(i)
        mini_fat += [struct.unpack('<I', b[4 * j:4 * j + 4])[0] for j in range(razm // 4)]
    koren = zapisi[0]
    mini_potok = b''.join(sektor(i) for i in cepochka(koren[1], fat))
    return b''.join(mini_potok[i * mrazm:(i + 1) * mrazm]
                    for i in cepochka(nach, mini_fat))[:razmer]


def listy_xls(telo):
    """BIFF8: возвращает [(imya_lista, [stroka,...])]. Один лист на весь файл,
    если BOUNDSHEET не разобрался (для нашей задачи этого достаточно)."""
    pot = _ole_potok(telo)
    if pot is None:
        return []
    sst, i, n = [], 0, len(pot)
    yach = {}
    listy_gr = []
    while i + 4 <= n:
        kod, dlina = struct.unpack('<HH', pot[i:i + 4])
        dan = pot[i + 4:i + 4 + dlina]
        sled = i + 4 + dlina
        # склейка CONTINUE для SST
        if kod == 0x00FC:
            polnoe = bytearray(dan)
            j = sled
            while j + 4 <= n:
                k2, d2 = struct.unpack('<HH', pot[j:j + 4])
                if k2 != 0x003C:
                    break
                polnoe += pot[j + 4:j + 4 + d2]
                j = j + 4 + d2
            sst = _razobrat_sst(bytes(polnoe))
            i = j
            continue
        if kod == 0x0085 and len(dan) >= 8:          # BOUNDSHEET
            dl = dan[6]
            fl = dan[7]
            syr = dan[8:8 + (dl * 2 if fl & 1 else dl)]
            listy_gr.append(syr.decode('utf-16-le' if fl & 1 else 'cp1251', 'replace'))
        elif kod == 0x00FD and len(dan) >= 10:       # LABELSST
            r, c, idx = struct.unpack('<HHxxI', dan[:10])
            yach[(r, c)] = sst[idx] if idx < len(sst) else ''
        elif kod == 0x0204 and len(dan) >= 8:        # LABEL
            r, c = struct.unpack('<HH', dan[:4])
            dl = struct.unpack('<H', dan[6:8])[0]
            fl = dan[8] if len(dan) > 8 else 0
            syr = dan[9:9 + (dl * 2 if fl & 1 else dl)]
            yach[(r, c)] = syr.decode('utf-16-le' if fl & 1 else 'cp1251', 'replace')
        elif kod == 0x0203 and len(dan) >= 14:       # NUMBER
            r, c = struct.unpack('<HH', dan[:4])
            yach[(r, c)] = _chislo(struct.unpack('<d', dan[6:14])[0])
        elif kod == 0x027E and len(dan) >= 10:       # RK
            r, c = struct.unpack('<HH', dan[:4])
            yach[(r, c)] = _chislo(_rk(struct.unpack('<I', dan[6:10])[0]))
        elif kod == 0x00BD and len(dan) >= 6:        # MULRK
            r, c1 = struct.unpack('<HH', dan[:4])
            k = 4
            cc = c1
            while k + 6 <= len(dan) - 2:
                yach[(r, cc)] = _chislo(_rk(struct.unpack('<I', dan[k + 2:k + 6])[0]))
                k += 6
                cc += 1
        i = sled
    if not yach:
        return [(listy_gr[0] if listy_gr else 'лист', [])]
    maxr = max(r for r, _ in yach)
    maxc = max(c for _, c in yach)
    stroki = [[yach.get((r, c), '') for c in range(maxc + 1)] for r in range(maxr + 1)]
    imya = ' + '.join(listy_gr) if listy_gr else 'лист'
    return [(imya, stroki)]


def _chislo(x):
    return ('%d' % x) if float(x).is_integer() and abs(x) < 1e15 else repr(x)


def _rk(v):
    celoe = v & 2
    sotka = v & 1
    if celoe:
        x = float(struct.unpack('<i', struct.pack('<I', v & 0xFFFFFFFC))[0] >> 2)
    else:
        x = struct.unpack('<d', struct.pack('<Q', (v & 0xFFFFFFFC) << 32))[0]
    return x / 100.0 if sotka else x


def _razobrat_sst(dan):
    out = []
    if len(dan) < 8:
        return out
    kol = struct.unpack('<I', dan[4:8])[0]
    i = 8
    for _ in range(min(kol, 300000)):
        if i + 3 > len(dan):
            break
        dl = struct.unpack('<H', dan[i:i + 2])[0]
        fl = dan[i + 2]
        i += 3
        rich = phon = 0
        if fl & 8:
            rich = struct.unpack('<H', dan[i:i + 2])[0]
            i += 2
        if fl & 4:
            phon = struct.unpack('<I', dan[i:i + 4])[0]
            i += 4
        if fl & 1:
            s = dan[i:i + dl * 2].decode('utf-16-le', 'replace')
            i += dl * 2
        else:
            s = dan[i:i + dl].decode('cp1251', 'replace')
            i += dl
        i += rich * 4 + phon
        out.append(re.sub(r'\s+', ' ', s).strip())
    return out


def listy_csv(telo):
    txt = v_tekst(telo)
    razd = ';' if txt.count(';') > txt.count(',') else ','
    stroki = [l.split(razd) for l in txt.splitlines() if l.strip()]
    return [('csv', stroki)]


def tekst_pdf(telo):
    """Текст из pdf без сторонних библиотек. Возвращает (tekst, n_potokov)."""
    kuski, n = [], 0
    for m in re.finditer(rb'stream\r?\n', telo):
        nach = m.end()
        kon = telo.find(b'endstream', nach)
        if kon < 0:
            continue
        syr = telo[nach:kon]
        try:
            raspak = zlib.decompress(syr)
        except Exception:  # noqa: BLE001
            continue
        n += 1
        t = raspak.decode('latin-1', 'replace')
        for tm in re.finditer(r'\((?:\\.|[^()\\])*\)', t):
            kuski.append(tm.group(0)[1:-1])
    return ' '.join(kuski), n


def tekst_docx(telo):
    z = zipfile.ZipFile(io.BytesIO(telo))
    for imya in ('word/document.xml', 'content.xml'):
        if imya in z.namelist():
            x = z.read(imya).decode('utf-8', 'replace')
            return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', x))
    return ''


# ---------------------------------------------------------------------------
# Признаки: заявитель назван или нет
# ---------------------------------------------------------------------------
INN_RE = re.compile(r'^\d{10}$|^\d{12}$')
FORMY = re.compile(r'\bООО\b|\bОАО\b|\bЗАО\b|\bПАО\b|\bАО\b|\bИП\b|\bГУП\b|\bМУП\b|'
                   r'\bФГУП\b|\bНАО\b|\bАКЦИОНЕРНОЕ\b|\bОБЩЕСТВО\b|\bКФХ\b', re.I)
NAZV_KOL = ('наименование', 'заявител', 'потребител', 'абонент', 'застройщик',
            'организац', 'юридическ', 'фио', 'ф.и.о', 'контрагент', 'клиент',
            'собственник', 'владелец', 'заказчик')
INN_KOL = ('инн', 'огрн')
ADRES_KOL = ('адрес', 'местонахожд', 'место нахожд', 'расположен', 'объект')
OBEM_KOL = ('объем', 'объём', 'расход', 'м3', 'м³', 'куб', 'мощност', 'нагрузк')
DATA_KOL = ('дата', 'срок', 'период')


def kontrolnaya_inn(s):
    """Настоящий ИНН проходит контрольную сумму. Хвост float её не проходит."""
    if not INN_RE.match(s):
        return False
    c = [int(x) for x in s]
    if len(s) == 10:
        w = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return sum(a * b for a, b in zip(w, c[:9])) % 11 % 10 == c[9]
    w1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    w2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    return (sum(a * b for a, b in zip(w1, c[:10])) % 11 % 10 == c[10]
            and sum(a * b for a, b in zip(w2, c[:11])) % 11 % 10 == c[11])


def shapka(stroki, glubina=12):
    """Ищем строку-шапку: ту, где больше всего непустых текстовых ячеек."""
    luchshaya, ball = -1, -1
    for i, r in enumerate(stroki[:glubina]):
        b = sum(1 for v in r if v and not re.fullmatch(r'[\d.,\s-]*', str(v)))
        if b > ball:
            luchshaya, ball = i, b
    return luchshaya if ball > 0 else -1


def vse_zagolovki(stroki, predel=40):
    """ВСЕ текстовые ячейки листа, без привязки к номеру строки.

    Зачем отдельно от шапки: шапка в формах раскрытия почти всегда разнесена на
    3-6 объединённых строк, и «строка с колонками» не существует как одна строка.
    Утверждение «колонки ИНН нет ВОВСЕ» доказывается только просмотром всех
    текстовых ячеек листа, а не первой подходящей строки.
    """
    vidno, out = set(), []
    for r in stroki:
        for v in r:
            s = re.sub(r'\s+', ' ', str(v)).strip()
            if len(s) < 3 or re.fullmatch(r'[\d.,%\s*x-]*', s):
                continue
            n = s.lower()
            if n in vidno:
                continue
            vidno.add(n)
            out.append(s)
            if len(out) >= 4000:
                return out
    return out


def gde_slovo(zagolovki, slova, predel=6):
    """Какие текстовые ячейки листа содержат искомые слова. Пусто = колонки нет."""
    nash = [z for z in zagolovki if any(s in z.lower() for s in slova)]
    return nash[:predel], len(nash)


def razobrat_tablicu(imya_lista, stroki, zerna):
    """Числа и признаки по одному листу."""
    n_shapki = shapka(stroki)
    kolonki = [re.sub(r'\s+', ' ', str(v)).strip()
               for v in (stroki[n_shapki] if n_shapki >= 0 else [])]
    # шапка часто разнесена на 2-3 строки: склеиваем соседние
    if n_shapki >= 0:
        for r in stroki[n_shapki + 1:n_shapki + 3]:
            for j, v in enumerate(r):
                v = re.sub(r'\s+', ' ', str(v)).strip()
                if not v or re.fullmatch(r'[\d.,\s-]*', v):
                    continue
                if j < len(kolonki):
                    if v.lower() not in kolonki[j].lower():
                        kolonki[j] = (kolonki[j] + ' / ' + v).strip(' /')
                else:
                    kolonki += [''] * (j - len(kolonki)) + [v]
    nizh = [k.lower() for k in kolonki]
    dannye = stroki[n_shapki + 1:] if n_shapki >= 0 else stroki
    dannye = [r for r in dannye if any(str(v).strip() for v in r)]

    def kol_indeksy(slova):
        return [i for i, k in enumerate(nizh) if any(s in k for s in slova)]

    i_inn = kol_indeksy(INN_KOL)
    i_nazv = kol_indeksy(NAZV_KOL)
    i_adr = kol_indeksy(ADRES_KOL)
    i_ob = kol_indeksy(OBEM_KOL)
    i_dat = kol_indeksy(DATA_KOL)

    # ИНН строго по своей колонке + контрольная сумма (яма 1)
    inn_po_kolonke = 0
    for r in dannye:
        for i in i_inn:
            if i < len(r) and kontrolnaya_inn(str(r[i]).strip()):
                inn_po_kolonke += 1
                break
    # ИНН где угодно в строке, но с контрольной суммой - страховка, если шапка не нашлась
    inn_gde_ugodno = 0
    for r in dannye:
        if any(kontrolnaya_inn(str(v).strip()) for v in r):
            inn_gde_ugodno += 1

    # Юрлица: вычитаем саму газовую компанию (яма 2)
    svoi = 0
    chuzhie = 0
    primery = []
    for r in dannye:
        ploskaya = ' '.join(str(v) for v in r)
        if not FORMY.search(ploskaya):
            continue
        n = ploskaya.lower()
        if any(z in n for z in zerna):
            svoi += 1
        else:
            chuzhie += 1
            if len(primery) < 4:
                primery.append(re.sub(r'\s+', ' ', ploskaya)[:110])
    # Даты: и строкой, и серийным числом Excel (яма 3)
    dat = 0
    for r in dannye:
        for i in i_dat:
            if i < len(r):
                v = str(r[i]).strip()
                if re.search(r'\d{2}[./-]\d{2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}', v) or \
                        re.fullmatch(r'4\d{4}(\.0)?', v):
                    dat += 1
                    break
    # Главное доказательство нуля: поиск слова по ВСЕМ текстовым ячейкам листа.
    zag = vse_zagolovki(stroki)
    v_inn, n_inn = gde_slovo(zag, INN_KOL)
    v_naim, n_naim = gde_slovo(zag, NAZV_KOL)
    v_adr, n_adr = gde_slovo(zag, ADRES_KOL)
    v_ob, n_ob = gde_slovo(zag, OBEM_KOL)
    return dict(list=imya_lista, strok_vsego=len(stroki), strok_dannyh=len(dannye),
                n_shapki=n_shapki, kolonki=kolonki,
                tekstovyh_yacheek=len(zag),
                pervye_stroki=[' ¦ '.join(str(v)[:24] for v in r)[:230]
                               for r in stroki[:10]],
                yacheyki_inn=v_inn, yacheyki_inn_vsego=n_inn,
                yacheyki_naim=v_naim, yacheyki_naim_vsego=n_naim,
                yacheyki_adres=v_adr, yacheyki_adres_vsego=n_adr,
                yacheyki_obem=v_ob, yacheyki_obem_vsego=n_ob,
                est_kol_inn=bool(i_inn), est_kol_naim=bool(i_nazv),
                est_kol_adres=bool(i_adr), est_kol_obem=bool(i_ob),
                est_kol_data=bool(i_dat),
                imena_inn=[kolonki[i] for i in i_inn],
                imena_naim=[kolonki[i] for i in i_nazv],
                imena_obem=[kolonki[i] for i in i_ob],
                inn_po_kolonke=inn_po_kolonke, inn_gde_ugodno=inn_gde_ugodno,
                strok_so_svoey_kompaniey=svoi, strok_s_chuzhim_yurlicom=chuzhie,
                primery_yurlic=primery, strok_s_datoy=dat,
                kontrol_slovo=sum(1 for r in dannye
                                  if KONTROL_SLOVO in ' '.join(str(v) for v in r).lower()))


def razobrat_fayl(url, telo, zerna):
    """Разбор одного скачанного файла -> список результатов по листам."""
    nizh = url.lower().split('?')[0]
    if nizh.endswith(('.xlsx', '.xlsm', '.ods')) or telo[:2] == b'PK':
        try:
            listy = listy_xlsx(telo)
        except Exception as e:  # noqa: BLE001
            return [dict(list='ОШИБКА', oshibka='%s: %s' % (type(e).__name__, e))]
    elif nizh.endswith('.xls') or telo[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        try:
            listy = listy_xls(telo)
        except Exception as e:  # noqa: BLE001
            return [dict(list='ОШИБКА', oshibka='%s: %s' % (type(e).__name__, e))]
    elif nizh.endswith('.csv'):
        listy = listy_csv(telo)
    elif nizh.endswith('.pdf') or telo[:4] == b'%PDF':
        txt, n = tekst_pdf(telo)
        return [_iz_teksta('pdf (потоков %d)' % n, txt, zerna)]
    elif nizh.endswith(('.docx', '.rtf', '.doc')):
        try:
            txt = tekst_docx(telo) if telo[:2] == b'PK' else v_tekst(telo)
        except Exception:  # noqa: BLE001
            txt = ''
        return [_iz_teksta('документ', txt, zerna)]
    else:
        return [dict(list='не таблица', oshibka='тип не распознан, %d байт' % len(telo))]
    return [razobrat_tablicu(im, st, zerna) for im, st in listy]


def _iz_teksta(metka, txt, zerna):
    """Для pdf/doc: колонок нет, считаем признаки по тексту."""
    inn = [s for s in re.findall(r'\b\d{10}\b|\b\d{12}\b', txt) if kontrolnaya_inn(s)]
    yur = FORMY.findall(txt)
    n = txt.lower()
    chuzhie = len(re.findall(r'(?:ООО|ЗАО|ОАО|ИП)\s*[«"][^»"]{2,60}[»"]', txt))
    svoi = sum(n.count(z) for z in zerna)
    return dict(list=metka, strok_vsego=0, strok_dannyh=0, n_shapki=-1, kolonki=[],
                est_kol_inn=False, est_kol_naim=False, est_kol_adres=False,
                est_kol_obem=False, est_kol_data=False,
                imena_inn=[], imena_naim=[], imena_obem=[],
                inn_po_kolonke=0, inn_gde_ugodno=len(set(inn)),
                strok_so_svoey_kompaniey=svoi, strok_s_chuzhim_yurlicom=chuzhie,
                primery_yurlic=re.findall(r'(?:ООО|ЗАО|ОАО|ИП)\s*[«"][^»"]{2,60}[»"]',
                                          txt)[:4],
                strok_s_datoy=len(re.findall(r'\d{2}[./]\d{2}[./]\d{4}', txt)),
                kontrol_slovo=n.count(KONTROL_SLOVO), znakov=len(txt),
                yurlic_upominaniy=len(yur))


# ---------------------------------------------------------------------------
# Состояние
# ---------------------------------------------------------------------------
def chitat():
    if os.path.exists(SOSTOYANIE):
        with open(SOSTOYANIE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def pisat(d):
    with open(SOSTOYANIE, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def na_drop(imya, dannye):
    """Положить результат на дроп (работает и с сервера, и из песочницы)."""
    url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    if not (url and tok):
        return 'нет DROP_URL/DROP_TOKEN'
    try:
        rq = urllib.request.Request(url.rstrip('/') + '/' + imya, method='PUT',
                                    data=json.dumps(dannye, ensure_ascii=False).encode())
        rq.add_header('X-Drop-Token', tok)
        return 'код %s' % urllib.request.urlopen(rq, timeout=180).status
    except Exception as e:  # noqa: BLE001
        return 'сбой %s' % e


# ---------------------------------------------------------------------------
# Режимы
# ---------------------------------------------------------------------------
def rezhim_hosty(argv):
    print('=== опрос доменов ГРО. код 0 = не ответил вовсе, всё прочее = ОТВЕТ ===')
    st = chitat()
    st.setdefault('hosty', {})
    kk, kt, _ = vzyat(KONTROL_HOST, timeout=20)
    print('КОНТРОЛЬ выдуманный домен: код=%s  %s' % (kk, kt[:48].decode('utf-8', 'replace')))
    zhivyh = 0
    for o in ORG:
        if argv and o['k'] not in argv:
            continue
        varianty = ZAPASNYE.get(o['k'], [o['dom']])
        nashli = None
        stroka = []
        for d in varianty:
            kod, telo, kon = vzyat('https://' + d + '/', timeout=30, predel=2_000_000)
            stroka.append('%s=%s/%d' % (d, kod, len(telo)))
            if kod == 200 and len(telo) > 2000 and not nashli:
                nashli = (d, kod, len(telo), kon)
            if nashli:
                break
        if nashli:
            zhivyh += 1
            st['hosty'][o['k']] = dict(dom=nashli[0], kod=nashli[1], bayt=nashli[2])
        else:
            st['hosty'][o['k']] = dict(dom=varianty[0], kod=0, bayt=0)
        print('%-11s %-30s %s' % (o['k'], o['region'][:30], ' | '.join(stroka)))
    # КОНТРОЛЬ 2: заведомо несуществующий путь на живом домене обязан дать не-200
    for o in ORG:
        h = st['hosty'].get(o['k'], {})
        if h.get('kod') == 200:
            k2, _, _ = vzyat('https://%s/shvartskopfer-net-takoy-stranicy' % h['dom'],
                             timeout=25)
            print('КОНТРОЛЬ несуществующий путь на %s: код=%s (200 = прибор врёт)'
                  % (h['dom'], k2))
            break
    pisat(st)
    print('--- ИТОГ: ответили 200 из %d организаций: %d' % (len(ORG), zhivyh))
    return 0


def rezhim_razdely(argv):
    st = chitat()
    st.setdefault('razdely', {})
    hosty = st.get('hosty', {})
    predel = int(os.environ.get('TP_GAZ_STRANIC', 45))
    imya_drop = ''
    for a in argv:
        if a.startswith('--stranic='):
            predel = int(a.split('=', 1)[1])
        if a.startswith('--vyhod='):
            imya_drop = a.split('=', 1)[1]
    klyuchi = [a for a in argv if a in PO_KLYUCHU] or [o['k'] for o in ORG]
    for k in klyuchi:
        o = PO_KLYUCHU[k]
        dom = (hosty.get(k) or {}).get('dom') or o['dom']
        if (hosty.get(k) or {}).get('kod') not in (200, None):
            print('%-11s пропуск: домен %s не ответил' % (k, dom))
            continue
        t0 = time.time()
        r = obhod(dom, predel_stranic=predel)
        st['razdely'][k] = dict(dom=dom, stranicy={a: list(v) for a, v in r['stranicy'].items()},
                                fayly=r['fayly'])
        ok = sum(1 for v in r['stranicy'].values() if v[0] == 200)
        print('%-11s %-26s страниц %3d (200: %3d) файлов %3d  %.0fс'
              % (k, dom, len(r['stranicy']), ok, len(r['fayly']), time.time() - t0))
        pisat(st)
    vsego = sum(len(v['fayly']) for v in st['razdely'].values())
    print('--- ИТОГ: организаций обойдено %d, файлов найдено %d'
          % (len(st['razdely']), vsego))
    if imya_drop:
        print('--- на дроп %s: %s' % (imya_drop, na_drop(imya_drop, st)))
    return 0


def rezhim_kontrol(argv):
    """ПОЛОЖИТЕЛЬНЫЙ КОНТРОЛЬ: доказать, что определитель срабатывает, когда
    заявитель В ВЫГРУЗКЕ ЕСТЬ.

    Отрицательный контроль («щварцкопфер» даёт 0, выдуманный файл даёт не-200)
    ловит только прибор, который видит лишнее. Он НЕ ловит прибор, который слеп:
    сломанный разбор xlsx у меня давал «колонки ИНН нет вовсе» и на форме ГРО,
    и на любом файле вообще. Поэтому нужен вход, где ответ заведомо НЕ ноль.

    Годный вход - выгрузка ЕГРЗ (`KOMPRESSORNYE-STANCII-EGRZ.xlsx` на дропе):
    там ИНН застройщика стоит отдельной колонкой у 465 записей из 495.
    Если на этом входе определитель даёт 0 - верить его нулям по газу нельзя.

        python3 seo-texts/tp_gaz.py kontrol <путь к xlsx или csv> [ожидаемый минимум ИНН]
    """
    if not argv:
        print('нужен путь к файлу-эталону (выгрузка ЕГРЗ)')
        return 1
    put = argv[0]
    porog = int(argv[1]) if len(argv) > 1 else 1
    with open(put, 'rb') as f:
        telo = f.read()
    print('эталон: %s, %d байт' % (os.path.basename(put), len(telo)))
    vsego_inn = 0
    for r in razobrat_fayl(put, telo, ['щварцкопфер-такой-компании-нет']):
        pechat_lista(r, '  ')
        vsego_inn = max(vsego_inn, r.get('inn_po_kolonke', 0), r.get('inn_gde_ugodno', 0))
    print('--- ИТОГ ПОЛОЖИТЕЛЬНОГО КОНТРОЛЯ: строк с ИНН найдено %d, порог %d -> %s'
          % (vsego_inn, porog,
             'ПРИБОР ВИДИТ ЗАЯВИТЕЛЯ' if vsego_inn >= porog else
             'ПРИБОР СЛЕП, его нулям по газу верить НЕЛЬЗЯ'))
    return 0 if vsego_inn >= porog else 1


def rezhim_slit(argv):
    """Влить состояние, снятое на другом слое (скачано с дропа), в своё."""
    st = chitat()
    for put in argv:
        with open(put, encoding='utf-8') as f:
            chuzhoe = json.load(f)
        for razdel in ('hosty', 'razdely', 'razbor'):
            st.setdefault(razdel, {})
            for k, v in (chuzhoe.get(razdel) or {}).items():
                if razdel == 'razbor' and k in st[razdel]:
                    st[razdel][k].update(v)
                else:
                    st[razdel][k] = v
        print('влито из %s: %s' % (os.path.basename(put),
                                   {r: len(chuzhoe.get(r) or {}) for r in
                                    ('hosty', 'razdely', 'razbor')}))
    pisat(st)
    print('--- ИТОГ: организаций с разделом %d, с разбором %d'
          % (len(st.get('razdely', {})), len(st.get('razbor', {}))))
    return 0


INTERES = ('заявк', 'zayav', 'реестр', 'reestr', 'журнал', 'договор', 'dogovor',
           'подключен', 'присоедин', 'свободн', 'мощност', 'пропускн', 'грс',
           'план-график', 'догазифик', 'технолог', '872', '1547', 'регистрац',
           'юридическ', 'потребител', 'техническ услов', 'ту ')


def interesnye(fayly, predel=None):
    out = []
    for a, podpis in fayly.items():
        klyuch = (urllib.parse.unquote(a) + ' ' + podpis).lower()
        ball = sum(1 for s in INTERES if s in klyuch)
        if ball:
            out.append((ball, a, podpis))
    out.sort(key=lambda x: -x[0])
    return out[:predel] if predel else out


def rezhim_spisok(argv):
    """Печать найденных файлов с подписями - чтобы имена форм читались глазами."""
    st = chitat()
    klyuchi = [a for a in argv if a in PO_KLYUCHU] or sorted(st.get('razdely', {}))
    for k in klyuchi:
        r = st.get('razdely', {}).get(k)
        if not r:
            continue
        sp = interesnye(r['fayly'])
        print('\n=== %s (%s) файлов всего %d, по теме %d' % (k, r['dom'], len(r['fayly']), len(sp)))
        for ball, a, podpis in sp[:40]:
            print('  [%d] %-70s | %s' % (ball, a[-70:], podpis[:90]))
    return 0


def rezhim_stranica(argv):
    """Одна страница целиком: все ссылки и все файлы с подписями.

    ЯМА, пойманная на mosoblgaz.ru: несуществующий путь отдаёт **код 200** и
    120 КБ с заголовком «Страница не найдена». Код ответа тут не доказывает, что
    страница есть, - поэтому режим печатает <title> и размер, а контроль сравнивает
    страницу с заведомо выдуманным путём на том же домене.
    """
    url = argv[0]
    kod, telo, kon = vzyat(url, timeout=90, predel=8_000_000)
    html = v_tekst(telo) if telo else ''
    zag = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
    zag = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', zag.group(1))).strip() if zag else ''
    print('страница: код=%s байт=%d title=«%s»' % (kod, len(telo), zag[:90]))
    baza = '%s://%s' % (urllib.parse.urlparse(kon).scheme, urllib.parse.urlparse(kon).netloc)
    k2, t2, _ = vzyat(baza + '/shvartskopfer-net-takoy-stranicy', timeout=40, predel=4_000_000)
    h2 = v_tekst(t2) if t2 else ''
    z2 = re.search(r'<title[^>]*>(.*?)</title>', h2, re.S | re.I)
    z2 = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', z2.group(1))).strip() if z2 else ''
    print('КОНТРОЛЬ выдуманный путь: код=%s байт=%d title=«%s»' % (k2, len(t2), z2[:60]))
    if kod == 200 and zag and zag == z2:
        print('!! title совпал с выдуманным путём - страницы, скорее всего, НЕТ')
    vse = ssylki(html, kon)
    fayly = [(a, p) for a, p in vse if a.lower().split('?')[0].endswith(RASSHIRENIYA)]
    print('ссылок всего %d, из них на файлы %d' % (len(vse), len(fayly)))
    print('--- ФАЙЛЫ:')
    for a, p in fayly:
        print('  %-58s | %s' % (urllib.parse.unquote(a)[-58:], p[:100]))
    print('--- ССЫЛКИ С ПОДПИСЬЮ ПО ТЕМЕ:')
    vidno = set()
    for a, p in vse:
        klyuch = (urllib.parse.unquote(a) + ' ' + p).lower()
        if p and any(s in klyuch for s in INTERES) and a not in vidno:
            vidno.add(a)
            print('  %-58s | %s' % (urllib.parse.unquote(a)[-58:], p[:100]))
    print('--- ИТОГ: файлов %d, тематических ссылок %d' % (len(fayly), len(vidno)))
    # --razobrat=N: тут же скачать и разобрать N самых тематических файлов
    skolko = 0
    zerna = ['газпром', 'газораспределение', 'мособлгаз', 'мосгаз', 'газэкс']
    otbor = None
    for a in argv[1:]:
        if a.startswith('--razobrat='):
            skolko = int(a.split('=', 1)[1])
        if a.startswith('--org='):
            zerna = PO_KLYUCHU[a.split('=', 1)[1]]['zerna']
        if a.startswith('--otbor='):
            otbor = a.split('=', 1)[1].lower()
    if not skolko:
        return 0
    if otbor:
        # --otbor применяется ко ВСЕМ файлам страницы, а не только к «тематическим»:
        # имя «Prilozhenie-4-Forma-6-avgust.xlsx» не содержит ни одного слова из
        # INTERES, то есть тематический отбор его молча выбрасывал.
        sp = [(1, a, p) for a, p in fayly
              if otbor in urllib.parse.unquote(a).lower() or otbor in p.lower()]
    else:
        sp = interesnye({a: p for a, p in fayly})
    print('\n=== РАЗБОР %d файлов из %d тематических' % (min(skolko, len(sp)), len(sp)))
    sobrano = {}
    imya_drop = ''
    tiho = '--tiho' in argv
    for a in argv[1:]:
        if a.startswith('--vyhod='):
            imya_drop = a.split('=', 1)[1]
    for ball, a, podpis in sp[:skolko]:
        kod, telo, kon = vzyat(a, timeout=180, predel=25_000_000)
        print('-- %s | %s' % (podpis[:60] or '—', urllib.parse.unquote(a)[-55:]))
        print('   код=%s байт=%d' % (kod, len(telo)))
        if kod != 200 or len(telo) < 64:
            continue
        listy = razobrat_fayl(kon, telo, zerna)
        sobrano[a] = dict(kod=kod, bayt=len(telo), podpis=podpis, listy=listy)
        if not tiho:
            for x in listy:
                pechat_lista(x, '   ')
    if imya_drop:
        print('--- на дроп %s: %s' % (imya_drop, na_drop(imya_drop, sobrano)))
    print('--- ИТОГ разбора: файлов %d' % len(sobrano))
    return 0


def rezhim_fayl(argv):
    """Разбор одного файла по адресу."""
    url = argv[0]
    zerna = ['газпром', 'газораспределение', 'мособлгаз', 'мосгаз', 'газэкс']
    for a in argv[1:]:
        if a in PO_KLYUCHU:
            zerna = PO_KLYUCHU[a]['zerna']
    kod, telo, kon = vzyat(url, timeout=180)
    print('файл: код=%s байт=%d %s' % (kod, len(telo), url[-90:]))
    if kod != 200 or not telo:
        print(telo[:200].decode('utf-8', 'replace'))
        return 1
    for r in razobrat_fayl(kon, telo, zerna):
        pechat_lista(r)
    return 0


def pechat_lista(r, otstup='  '):
    if r.get('oshibka'):
        print(otstup + 'лист %s: %s' % (r.get('list'), r['oshibka']))
        return
    print(otstup + 'лист «%s»: строк всего %d, строк данных %d, текстовых ячеек %d'
          % (r['list'], r['strok_vsego'], r['strok_dannyh'], r.get('tekstovyh_yacheek', 0)))
    for s in r.get('pervye_stroki', [])[:8]:
        if s.strip(' ¦'):
            print(otstup + '  > ' + s)
    for metka, klyuch in (('ИНН/ОГРН', 'inn'), ('НАИМЕНОВАНИЕ/ЗАЯВИТЕЛЬ', 'naim'),
                          ('АДРЕС/ОБЪЕКТ', 'adres'), ('ОБЪЁМ/МОЩНОСТЬ', 'obem')):
        vsego = r.get('yacheyki_%s_vsego' % klyuch, 0)
        obr = r.get('yacheyki_%s' % klyuch, [])
        print(otstup + '  %-23s ячеек с этим словом на листе: %d%s'
              % (metka, vsego, ('  ->  ' + ' / '.join(x[:52] for x in obr)) if obr else
                 '   <- КОЛОНКИ НЕТ ВОВСЕ'))
    print(otstup + 'ИНН по колонке: %d | ИНН где угодно (с контрольной суммой): %d | '
                   'строк со своей компанией: %d | строк с ЧУЖИМ юрлицом: %d | с датой: %d'
          % (r['inn_po_kolonke'], r['inn_gde_ugodno'], r['strok_so_svoey_kompaniey'],
             r['strok_s_chuzhim_yurlicom'], r['strok_s_datoy']))
    for p in r.get('primery_yurlic', []):
        print(otstup + '  пример юрлица: ' + p)
    print(otstup + 'КОНТРОЛЬ «%s»: %d (обязан быть 0)' % (KONTROL_SLOVO, r['kontrol_slovo']))


def rezhim_razbor(argv):
    """Скачать и разобрать интересные файлы организаций."""
    st = chitat()
    st.setdefault('razbor', {})
    predel = int(os.environ.get('TP_GAZ_FAYLOV', 14))
    imya_drop = '3s-tp-gaz-sostoyanie.json'
    for a in argv:
        if a.startswith('--faylov='):
            predel = int(a.split('=', 1)[1])
        if a.startswith('--vyhod='):
            imya_drop = a.split('=', 1)[1]
    klyuchi = [a for a in argv if a in PO_KLYUCHU] or sorted(st.get('razdely', {}))
    for k in klyuchi:
        r = st.get('razdely', {}).get(k)
        if not r:
            print('%s: раздел не обойден' % k)
            continue
        o = PO_KLYUCHU[k]
        sp = interesnye(r['fayly'], predel)
        print('\n=== %s (%s): разбираю %d файлов' % (k, r['dom'], len(sp)))
        st['razbor'].setdefault(k, {})
        for ball, a, podpis in sp:
            if a in st['razbor'][k]:
                continue
            kod, telo, kon = vzyat(a, timeout=180, predel=25_000_000)
            print('-- %s | %s' % (podpis[:80] or os.path.basename(a)[:80], a[-60:]))
            print('   код=%s байт=%d' % (kod, len(telo)))
            if kod != 200 or len(telo) < 64:
                st['razbor'][k][a] = dict(kod=kod, bayt=len(telo), podpis=podpis, listy=[])
                continue
            listy = razobrat_fayl(kon, telo, o['zerna'])
            for x in listy:
                pechat_lista(x, '   ')
            st['razbor'][k][a] = dict(kod=kod, bayt=len(telo), podpis=podpis, listy=listy)
            pisat(st)
    pisat(st)
    print('\n--- ИТОГ разбора: на дроп %s: %s' % (imya_drop, na_drop(imya_drop, st)))
    return 0


def rezhim_svodka(argv):
    st = chitat()
    print('%-11s %-34s %6s %6s %5s %5s %5s %5s' %
          ('орг', 'форма (подпись/файл)', 'строк', 'данных', 'ИНН', 'наим', 'объём', 'дата'))
    itogo = dict(fayl=0, s_inn=0, s_naim=0, strok=0)
    for k, fayly in sorted(st.get('razbor', {}).items()):
        for a, v in fayly.items():
            for l in v.get('listy', []):
                if l.get('oshibka'):
                    continue
                itogo['fayl'] += 1
                itogo['strok'] += l.get('strok_dannyh', 0)
                if l.get('inn_po_kolonke'):
                    itogo['s_inn'] += 1
                if l.get('strok_s_chuzhim_yurlicom'):
                    itogo['s_naim'] += 1
                print('%-11s %-34s %6d %6d %5d %5d %5s %5d'
                      % (k, (v.get('podpis') or os.path.basename(a))[:34],
                         l.get('strok_vsego', 0), l.get('strok_dannyh', 0),
                         l.get('inn_po_kolonke', 0), l.get('strok_s_chuzhim_yurlicom', 0),
                         l.get('est_kol_obem'), l.get('strok_s_datoy', 0)))
    print('--- ИТОГ: листов %d, строк данных %d, листов с ИНН заявителя %d, '
          'листов с чужим юрлицом %d' % (itogo['fayl'], itogo['strok'],
                                         itogo['s_inn'], itogo['s_naim']))
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    r = sys.argv[1]
    a = sys.argv[2:]
    if r == 'hosty':
        return rezhim_hosty(a)
    if r == 'razdely':
        return rezhim_razdely(a)
    if r == 'spisok':
        return rezhim_spisok(a)
    if r == 'fayl':
        return rezhim_fayl(a)
    if r == 'razbor':
        return rezhim_razbor(a)
    if r == 'svodka':
        return rezhim_svodka(a)
    if r == 'slit':
        return rezhim_slit(a)
    if r == 'stranica':
        return rezhim_stranica(a)
    if r == 'kontrol':
        return rezhim_kontrol(a)
    print('неизвестный режим: %s' % r)
    return 1


if __name__ == '__main__':
    sys.exit(main())
