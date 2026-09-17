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
    dict(k='ufa',         dom='www.bashgaz.ru',      region='Башкортостан',
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
    # Адреса с кириллицей и пробелами в пути: urllib отказывается их открывать
    # («URL can't contain control characters»), и это выглядело как код 0, то есть
    # как «хост не ответил». Кодируем путь сами.
    r_ = urllib.parse.urlsplit(url)
    if any(ord(c) > 127 or c == ' ' for c in r_.path + r_.query):
        url = urllib.parse.urlunsplit((
            r_.scheme, r_.netloc, urllib.parse.quote(r_.path, safe='/%'),
            urllib.parse.quote(r_.query, safe='=&%'), r_.fragment))
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
            # Ширину строки режем: одна случайная ячейка в колонке XFD превращает
            # каждую строку в список на 16 384 пустышки, и разбор трёхмегабайтного
            # файла перестаёт заканчиваться вовсе - прибор висит, а выглядит это
            # как «файл не открылся».
            stroki.append([yach.get(j, '') for j in range(min(max(yach), 600) + 1)]
                          if yach else [])
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
    # ЗАЩИТА ОТ ТИХОЙ СМЕРТИ. На архиве 2014 года разбор .xls убил процесс без
    # единого сообщения: битая запись дала номер строки 65535 и номер колонки 255,
    # а разворачивание такой сетки - это 16,7 млн ячеек и OOM. Процесс просто
    # исчезал, а лог обрывался на середине - то есть выглядело как «файл не
    # разобрался», хотя на самом деле умер прибор. Режем сетку и говорим об этом.
    maxr = min(max(r for r, _ in yach), 200000)
    maxc = min(max(c for _, c in yach), 512)
    if (maxr + 1) * (maxc + 1) > 4_000_000:
        maxr = min(maxr, 4_000_000 // (maxc + 1))
        print('   !! сетка .xls обрезана до %dx%d - файл заявляет больше'
              % (maxr + 1, maxc + 1))
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
    """Текст из pdf без сторонних библиотек. Возвращает (tekst, n_potokov).

    ПОЧЕМУ ЗДЕСЬ БОЛЬШЕ КОДА, ЧЕМ КАЖЕТСЯ НУЖНО. Формы ГРО в pdf почти всегда
    набраны встроенным шрифтом с кодировкой Identity-H: на месте букв стоят
    номера глиф, и наивный сбор строк «(...)» даёт мусор или пусто. Прошлая
    сессия на этом и остановилась («текст в CID-кодировке, без pdf-библиотек
    не читается»). Но рядом в самом файле лежит таблица перевода ToUnicode
    (`beginbfchar` / `beginbfrange`), и её достаточно: читаем её и переводим
    коды сами. Если после перевода русских слов всё равно нет - честно
    возвращаем пусто, и лист помечается «не прочитан», а не «ноль».
    """
    potoki = []
    for m in re.finditer(rb'stream\r?\n', telo):
        nach = m.end()
        kon = telo.find(b'endstream', nach)
        if kon < 0:
            continue
        try:
            potoki.append(zlib.decompress(telo[nach:kon]))
        except Exception:  # noqa: BLE001
            continue
    karta = {}
    for d in potoki:
        if b'beginbfchar' not in d and b'beginbfrange' not in d:
            continue
        t = d.decode('latin-1', 'replace')
        for blok in re.findall(r'beginbfchar(.*?)endbfchar', t, re.S):
            for src, dst in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blok):
                karta[int(src, 16)] = _iz_utf16(dst)
        for blok in re.findall(r'beginbfrange(.*?)endbfrange', t, re.S):
            for a, b, c in re.findall(
                    r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', blok):
                nach_k, kon_k, nach_u = int(a, 16), int(b, 16), int(c, 16)
                for i in range(min(kon_k - nach_k + 1, 65536)):
                    karta[nach_k + i] = chr(nach_u + i)
    kuski = []
    for d in potoki:
        t = d.decode('latin-1', 'replace')
        if 'Tj' not in t and 'TJ' not in t:
            continue
        if karta:
            # Читаем ПО ОПЕРАТОРАМ показа текста: внутри одного [ ... ] TJ куски
            # склеиваются без пробела, между операторами ставится пробел. Иначе
            # каждая глифа становится отдельным «словом» и текст выглядит как
            # «Т о ч к а в х о д а».
            for om in re.finditer(r'\[(.*?)\]\s*TJ|<([0-9A-Fa-f\s]+)>\s*Tj', t, re.S):
                syr = om.group(1) or om.group(2) or ''
                slovo = []
                for hm in re.finditer(r'<([0-9A-Fa-f\s]+)>', syr):
                    h = re.sub(r'\s', '', hm.group(1))
                    slovo.append(''.join(karta.get(int(h[i:i + 4], 16), '')
                                         for i in range(0, len(h) - 3, 4)))
                if slovo:
                    kuski.append(''.join(slovo))
            continue
        for tm in re.finditer(r'\((?:\\.|[^()\\])*\)', t):
            s = tm.group(0)[1:-1]
            kuski.append(s)
    txt = re.sub(r'\s+', ' ', ' '.join(kuski))
    return txt, len(potoki)


def _iz_utf16(h):
    try:
        return bytes.fromhex(h).decode('utf-16-be', 'ignore')
    except Exception:  # noqa: BLE001
        return ''


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
            # Обрезать перечень нельзя: на нём строится доказательство нуля. Если
            # смотреть первые 4 000 ячеек из 28 000, «колонки ИНН нет» означает
            # лишь «нет в первых 4 000» - тот же дефект, что смотреть первые строки.
            if len(out) >= 400000:
                return out
    return out


# «инн» как подстрока ловится в «фИННов», «ИННолово», «ИННовационное агентство».
# Колонка ИНН ищется ТОЛЬКО как отдельное слово - иначе ноль превращается в
# ложную единицу, и доказательство ломается в обе стороны.
RE_INN_SLOVO = re.compile(r'\b(инн|огрн)\b', re.I)


def gde_slovo(zagolovki, slova, predel=6, celikom=False):
    """Какие текстовые ячейки листа содержат искомые слова. Пусто = колонки нет."""
    if celikom:
        nash = [z for z in zagolovki if RE_INN_SLOVO.search(z)]
    else:
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

    i_inn = [i for i, k in enumerate(nizh) if RE_INN_SLOVO.search(k)]
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
    v_inn, n_inn = gde_slovo(zag, INN_KOL, celikom=True)
    v_naim, n_naim = gde_slovo(zag, NAZV_KOL)
    v_adr, n_adr = gde_slovo(zag, ADRES_KOL)
    v_ob, n_ob = gde_slovo(zag, OBEM_KOL)
    # Лист с тысячами строк и НУЛЁМ текстовых ячеек - это не форма без шапки,
    # это провал разбора (так себя ведёт старый BIFF5 и битый архив). Такой ноль
    # принадлежит прибору, и выдавать его за ноль формы нельзя.
    nechitaem = len(stroki) > 0 and len(zag) == 0
    return dict(list=imya_lista, strok_vsego=len(stroki), strok_dannyh=len(dannye),
                n_shapki=n_shapki, kolonki=kolonki, nechitaem=nechitaem,
                znakov=0, tekstovyh_yacheek=len(zag),
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
    # .zip с таблицами внутри: часть ГРО выкладывает формы архивом. Без этого
    # разбор архива давал «тип не распознан», то есть ещё один тихий ноль.
    if telo[:2] == b'PK' and not nizh.endswith(('.xlsx', '.xlsm', '.ods', '.docx')):
        try:
            z = zipfile.ZipFile(io.BytesIO(telo))
            imena = z.namelist()
        except Exception:  # noqa: BLE001
            imena = []
        if imena and not any(n.startswith('xl/') or n.startswith('word/') for n in imena):
            out = []
            for n in imena[:12]:
                if n.lower().endswith(('.xls', '.xlsx', '.csv', '.pdf', '.doc', '.docx')):
                    out += razobrat_fayl(n, z.read(n), zerna)
            return out or [dict(list='архив', oshibka='в архиве нет таблиц: %s'
                                % ', '.join(imena[:6]))]
    if nizh.endswith(('.xlsx', '.xlsm', '.ods')) or telo[:2] == b'PK':
        # ТЯЖЁЛЫЕ ФАЙЛЫ. Построчный разбор регулярками на файле 3,06 МБ
        # (P4_F6_fact_0926.xlsx, 5 187 значений) не закончился за 15 минут и был
        # убит по таймауту - дважды, и оба раза это выглядело как «файл не
        # разобрался». Для таких берём таблицу значений: она отвечает на главный
        # вопрос (назван ли потребитель) за секунды, а число СТРОК при этом
        # честно неизвестно и помечается нулём.
        if len(telo) > 1_200_000:
            r = _iz_tablicy_znacheniy(telo, zerna)
            if r:
                return [r]
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


def _iz_tablicy_znacheniy(telo, zerna):
    """Быстрый разбор тяжёлого xlsx: только xl/sharedStrings.xml."""
    try:
        z = zipfile.ZipFile(io.BytesIO(telo))
        if 'xl/sharedStrings.xml' not in z.namelist():
            return None
        x = z.read('xl/sharedStrings.xml').decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return None
    si = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m)).strip()
          for m in re.findall(r'<si>(.*?)</si>', x, re.S)]
    if not si:
        return None
    r = razobrat_tablicu('таблица значений (быстрый путь, строки не считались)',
                         [[s] for s in si], zerna)
    r['strok_vsego'] = 0
    r['bystryy_put'] = True
    return r


def _iz_teksta(metka, txt, zerna):
    """Для pdf/doc: колонок нет, считаем признаки по тексту.

    ЧЕСТНОСТЬ ПРО PDF. Шрифты в формах ГРО почти всегда в CID-кодировке, и без
    pdf-библиотеки текст из них не достаётся. Тогда все счётчики честно дают 0 -
    и этот ноль означает «прибор не прочитал», а НЕ «колонки нет». Поэтому, если
    осмысленного текста не извлеклось, лист помечается `nechitaem` и в сводку
    идёт как «не прочитан», а не как доказанный ноль.
    """
    inn = [s for s in re.findall(r'\b\d{10}\b|\b\d{12}\b', txt) if kontrolnaya_inn(s)]
    yur = FORMY.findall(txt)
    n = txt.lower()
    chuzhie = len(re.findall(r'(?:ООО|ЗАО|ОАО|ИП)\s*[«"][^»"]{2,60}[»"]', txt))
    svoi = sum(n.count(z) for z in zerna)
    # Шапку в pdf колонками не достать, но её НАЗВАНИЯ в тексте есть. Ищем их
    # прямо в тексте, иначе pdf-форма с колонкой «Наименование потребителя»
    # молча числилась бы «заявитель не назван» - ещё один ложный ноль.
    def naydeno(slova):
        # «инн» как подстрока ловится в «длинный», «финн» и подобных: короткие
        # ключи ищем только как отдельное слово, иначе колонка ИНН «находится»
        # там, где её нет.
        if slova is INN_KOL:
            return [s for s in slova if re.search(r'\b%s\b' % s, n)][:6]
        return [s for s in slova if s in n][:6]
    return dict(list=metka, strok_vsego=0, strok_dannyh=0, n_shapki=-1, kolonki=[],
                est_kol_inn=bool(naydeno(INN_KOL)), est_kol_naim=bool(naydeno(NAZV_KOL)),
                est_kol_adres=bool(naydeno(ADRES_KOL)),
                est_kol_obem=bool(naydeno(OBEM_KOL)), est_kol_data=False,
                tekstovyh_yacheek=0,
                yacheyki_inn=naydeno(INN_KOL), yacheyki_inn_vsego=len(naydeno(INN_KOL)),
                yacheyki_naim=[z for z in
                               re.findall(r'[А-ЯЁ][^.;|]{0,40}(?:потребител|заявител|'
                                          r'абонент|застройщик)[а-яё]*', txt)][:6]
                or naydeno(NAZV_KOL),
                yacheyki_naim_vsego=len(naydeno(NAZV_KOL)),
                yacheyki_adres=naydeno(ADRES_KOL),
                yacheyki_adres_vsego=len(naydeno(ADRES_KOL)),
                yacheyki_obem=naydeno(OBEM_KOL),
                yacheyki_obem_vsego=len(naydeno(OBEM_KOL)),
                imena_inn=[], imena_naim=[], imena_obem=[],
                inn_po_kolonke=0, inn_gde_ugodno=len(set(inn)),
                strok_so_svoey_kompaniey=svoi, strok_s_chuzhim_yurlicom=chuzhie,
                primery_yurlic=re.findall(r'(?:ООО|ЗАО|ОАО|ИП)\s*[«"][^»"]{2,60}[»"]',
                                          txt)[:4],
                strok_s_datoy=len(re.findall(r'\d{2}[./]\d{2}[./]\d{4}', txt)),
                kontrol_slovo=n.count(KONTROL_SLOVO), znakov=len(txt),
                yurlic_upominaniy=len(yur),
                nechitaem=len(re.findall(r'[а-яА-Я]{4,}', txt)) < 20)


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
    vsego_inn, luchshiy = 0, ''
    for r in razobrat_fayl(put, telo, ['щварцкопфер-такой-компании-нет']):
        pechat_lista(r, '  ')
        n = max(r.get('inn_po_kolonke', 0), r.get('inn_gde_ugodno', 0))
        if n > vsego_inn:
            vsego_inn, luchshiy = n, str(r.get('list'))
    print('--- ИТОГ ПОЛОЖИТЕЛЬНОГО КОНТРОЛЯ: строк с ИНН найдено %d (лучший лист «%s»), '
          'порог %d -> %s'
          % (vsego_inn, luchshiy, porog,
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


# Веса отбора. Пустой БЛАНК заявки и ЗАПОЛНЕННЫЙ реестр заявок называются почти
# одинаково, и без штрафов наверх лезут типовые формы, в которых данных нет по
# определению. Поэтому: сильный плюс за имя обязательной формы раскрытия,
# сильный минус за слова пустого бланка.
VES_PLYUS = {'реестр': 6, 'reestr': 6, 'журнал': 6, 'перечень заключ': 6,
             'заявок': 5, 'zayavok': 5, 'о регистрации и ходе': 6,
             'приложение': 3, 'prilozhenie': 3, 'форма': 2, 'forma': 2,
             'свободн': 4, 'пропускн': 3, 'мощност': 2, 'грс': 2,
             'план-график': 4, 'догазифик': 1, 'заявк': 2, 'zayav': 2,
             'подключ': 1, 'присоедин': 1, 'потребител': 1, 'юридическ': 2}
VES_MINUS = {'типовая': 8, 'типовой': 8, 'бланк': 8, 'образец': 8, 'форма заявки': 8,
             'форма договора': 8, 'правила': 5, 'регламент': 5, 'постановлени': 6,
             'приказ фас': 4, 'инструкц': 5, 'памятка': 5, 'политика': 6,
             'согласие': 6, 'уведомлени': 3, 'vdgo': 4, 'вдго': 4, 'узел': 6,
             'tipovaya': 8, 'tipovoy': 8, 'rules': 5, 'заявление': 4}


def podpis_formy(a, podpis):
    """Отпечаток формы: подпись без месяцев, годов и номеров - «П6Ф2 08-2026 ...»
    и «П6Ф2 07-2026 ...» это ОДНА форма за разные месяцы, и разбирать надо свежую,
    иначе 100 копий одного отчёта съедают весь бюджет разбора."""
    s = (podpis or urllib.parse.unquote(a).split('/')[-1]).lower()
    s = re.sub(r'\d', '', s)
    s = re.sub(r'(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|'
               r'ноябр|декабр)\w*', '', s)
    s = re.sub(r'[^а-яa-z]+', ' ', s).strip()
    return s[:70]


def svezhest(a):
    """Ключ свежести по году-месяцу в адресе. Нет даты - считаем самым старым."""
    m = re.search(r'/(20\d\d)/(\d{1,2})/', a) or re.search(r'(20\d\d)[-_/](\d{2})', a)
    if m:
        return '%s%02d' % (m.group(1), int(m.group(2)))
    m = re.search(r'(\d{2})[._-](20\d\d)', urllib.parse.unquote(a))
    if m:
        return '%s%02d' % (m.group(2), int(m.group(1)))
    return '000000'


def interesnye(fayly, predel=None, na_formu=1):
    out = []
    for a, podpis in fayly.items():
        klyuch = (urllib.parse.unquote(a) + ' ' + podpis).lower()
        ball = sum(v for s, v in VES_PLYUS.items() if s in klyuch)
        ball -= sum(v for s, v in VES_MINUS.items() if s in klyuch)
        # ПП 872 требует ТАБЛИЦУ, а не текст: rtf/doc почти всегда пустой бланк
        if a.lower().split('?')[0].endswith(('.xlsx', '.xls', '.xlsm', '.csv', '.ods')):
            ball += 4
        if ball > 0:
            out.append((ball, a, podpis))
    if na_formu:
        po_forme = {}
        for ball, a, podpis in out:
            po_forme.setdefault(podpis_formy(a, podpis), []).append((ball, a, podpis))
        out = []
        for gr in po_forme.values():
            gr.sort(key=lambda x: (svezhest(x[1]), x[0]), reverse=True)
            out += gr[:na_formu]
    out.sort(key=lambda x: (-x[0], -int(svezhest(x[1])), x[1]))
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


RE_DOSTUP = re.compile(
    r'налич\w*\s*\(?отсутств|техническ\w*\s+возможност\w*\s+доступ|'
    r'prilozhenie[-_ ]*4|приложение\s*[№ ]*4|p4[_-]?f[67]|форма\s*6[._ ]*приложение\s*4',
    re.I)


def rezhim_dostup(argv):
    """Прицельно по ОДНОЙ форме - приложение 4, форма 6/7 «о наличии (отсутствии)
    технической возможности доступа». Это единственная из обязательных форм ГРО,
    где стоит НАИМЕНОВАНИЕ ПОТРЕБИТЕЛЯ. Режим находит её у каждой организации и
    читает быстрым путём.
    """
    st = chitat()
    klyuchi = [a for a in argv if a in PO_KLYUCHU] or sorted(st.get('razdely', {}))
    nashli = 0
    for k in klyuchi:
        r = st.get('razdely', {}).get(k)
        if not r:
            continue
        kand = [(svezhest(a), a, p) for a, p in r['fayly'].items()
                if RE_DOSTUP.search(urllib.parse.unquote(a) + ' ' + p)
                and a.lower().split('?')[0].endswith(('.xlsx', '.xls', '.pdf', '.ods'))]
        if not kand:
            print('%-11s %-22s форма приложение 4 не найдена среди %d файлов'
                  % (k, r['dom'], len(r['fayly'])))
            continue
        kand.sort(reverse=True)
        _, a, p = kand[0]
        kod, telo, kon = vzyat(a, timeout=240, predel=60_000_000)
        print('%-11s %-22s %s' % (k, r['dom'], urllib.parse.unquote(a).split('/')[-1][:46]))
        print('            код=%s байт=%d | «%s»' % (kod, len(telo), p[:70]))
        if kod != 200 or len(telo) < 64:
            continue
        si = []
        if telo[:2] == b'PK':
            try:
                z = zipfile.ZipFile(io.BytesIO(telo))
                if 'xl/sharedStrings.xml' in z.namelist():
                    x = z.read('xl/sharedStrings.xml').decode('utf-8', 'replace')
                    si = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m)).strip()
                          for m in re.findall(r'<si>(.*?)</si>', x, re.S)]
            except Exception:  # noqa: BLE001
                si = []
        if not si:
            listy = razobrat_fayl(kon, telo, PO_KLYUCHU[k]['zerna'])
            for l in listy:
                if l.get('nechitaem'):
                    print('            НЕ ПРОЧИТАН - ноль прибора, не формы')
                    continue
                print('            строк %d | ячеек «наименование»: %s | юрлиц %d'
                      % (l.get('strok_dannyh', 0),
                         '; '.join(x[:40] for x in (l.get('yacheyki_naim') or [])[:2])
                         or 'НЕТ', l.get('strok_s_chuzhim_yurlicom', 0)))
                if l.get('strok_s_chuzhim_yurlicom', 0) >= 5:
                    nashli += 1
            continue
        imya = [s for s in si if 'наименование' in s.lower()][:2]
        yur = [s for s in si if FORMY.search(s)]
        print('            значений %d | шапка: %s | юрлиц %d | пример: %s'
              % (len(si), '; '.join(x[:40] for x in imya) or 'НЕТ', len(yur),
                 (yur[0][:46] if yur else '-')))
        if len(yur) >= 5:
            nashli += 1
    print('--- ИТОГ: организаций, где форма приложения 4 называет потребителя: %d' % nashli)
    return 0


SHAPKA_F6 = (
    ('tochka_vhoda_grs', ('точка входа',)),
    ('obekt_tochka_vyhoda', ('точка выхода',)),
    ('naimenovanie_potrebitelya', ('наименование потребителя',)),
    ('gruppa_gazopotrebleniya', ('группы газопотребл', 'группа газопотребл')),
    # Падежи у ГРО разные: «в соответствии с поступившими заявками» и «по
    # поступившим заявкам». Точная форма отбрасывала колонку объёма молча -
    # в выгрузке оставалось пусто, а выглядело как «в форме объёма нет».
    ('obem_po_postupivshim_zayavkam', ('поступивш',)),
    ('obem_po_udovletvorennym', ('удовлетворен', 'удовлетворён')),
    ('svobodnaya_moshchnost', ('свободная мощность',)),
)


def _period_iz(imya, stroki):
    """Период формы: из первых строк листа («на Ноябрь 2026 года», «за август 2026г.»),
    иначе из имени файла."""
    for r in stroki[:12]:
        for v in r:
            m = re.search(r'(?:за|на)\s+([А-Яа-яё]+\s*\d{4})', str(v))
            if m:
                return re.sub(r'\s+', ' ', m.group(1)).strip()
    m = re.search(r'(\d{2})[._-]?(20\d\d)', urllib.parse.unquote(imya))
    if m:
        return '%s.%s' % (m.group(1), m.group(2))
    m = re.search(r'(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|'
                  r'декабр)\w*[-_ ]*(20\d\d)', urllib.parse.unquote(imya), re.I)
    return (m.group(0) if m else '')


def stroki_formy6(imya_fayla, telo, gro):
    """Построчная выгрузка приложения 4 формы 6. Возвращает (список строк, отчёт).

    Колонки НЕ угадываются по номеру: ищется ячейка с нужным заголовком и берётся
    её номер колонки. Если заголовка «Наименование потребителя» на листе нет -
    возвращается пусто и причина, а не выдуманные столбцы.
    """
    listy = listy_xlsx(telo) if telo[:2] == b'PK' else listy_xls(telo)
    vyhod, otchet = [], []
    for imya_lista, stroki in listy:
        karta, n_shapki = {}, -1
        for i, r in enumerate(stroki[:40]):
            for j, v in enumerate(r):
                n = re.sub(r'\s+', ' ', str(v)).strip().lower()
                if not n:
                    continue
                for pole, slova in SHAPKA_F6:
                    if pole not in karta and any(s in n for s in slova):
                        karta[pole] = j
                        n_shapki = max(n_shapki, i)
        if 'naimenovanie_potrebitelya' not in karta:
            otchet.append('лист «%s»: заголовка «Наименование потребителя» нет, '
                          'строк на листе %d' % (imya_lista, len(stroki)))
            continue
        period = _period_iz(imya_fayla, stroki)
        i_pot = karta['naimenovanie_potrebitelya']
        n = 0
        for r in stroki[n_shapki + 1:]:
            if i_pot >= len(r):
                continue
            pot = re.sub(r'\s+', ' ', str(r[i_pot])).strip()
            # строка-нумерация («1 2 3 4 5») и пустые - не данные
            if not pot or re.fullmatch(r'[\d.,\s-]*', pot):
                continue
            z = dict(gro=gro, period=period, fayl=os.path.basename(
                urllib.parse.unquote(imya_fayla)), list=imya_lista)
            for pole, _ in SHAPKA_F6:
                j = karta.get(pole)
                z[pole] = (re.sub(r'\s+', ' ', str(r[j])).strip()
                           if j is not None and j < len(r) else '')
            vyhod.append(z)
            n += 1
        otchet.append('лист «%s»: шапка в строке %d, колонки %s, строк данных %d'
                      % (imya_lista, n_shapki, karta, n))
    return vyhod, otchet


def rezhim_vygruzka(argv):
    """Построчная выгрузка формы 6 в CSV: одна строка = одна запись формы.

    python3 tp_gaz.py vygruzka <url> <ключ ГРО> [ещё url ключ ...] [--csv=имя.csv] [--drop]
    """
    import csv as _csv
    imya_csv = '3s-tp-gaz-forma6-stroki.csv'
    na_drop_li = '--drop' in argv
    pary = []
    for a in argv:
        if a.startswith('--csv='):
            imya_csv = a.split('=', 1)[1]
        elif a.startswith('--'):
            continue
        elif a.startswith('http'):
            pary.append([a, ''])
        elif pary and not pary[-1][1]:
            pary[-1][1] = a
    put = os.path.join(KATALOG, imya_csv)
    starye = []
    if os.path.exists(put):
        with open(put, encoding='utf-8-sig', newline='') as f:
            starye = list(_csv.DictReader(f, delimiter=';'))
    polya = ['gro', 'period', 'tochka_vhoda_grs', 'obekt_tochka_vyhoda',
             'naimenovanie_potrebitelya', 'gruppa_gazopotrebleniya',
             'obem_po_postupivshim_zayavkam', 'obem_po_udovletvorennym',
             'svobodnaya_moshchnost', 'fayl', 'list', 'adres_istochnika']
    vse = [{k: (s.get(k) or '') for k in polya} for s in starye]
    bylo = len(vse)
    for url, gro in pary:
        kod, telo, kon = vzyat(url, timeout=300, predel=60_000_000)
        print('== %s | %s' % (gro, urllib.parse.unquote(url).split('/')[-1][:60]))
        print('   код=%s байт=%d' % (kod, len(telo)))
        if kod != 200 or len(telo) < 64:
            continue
        stroki, otchet = stroki_formy6(url, telo, gro)
        for s in otchet:
            print('   ' + s)
        for s in stroki:
            s['adres_istochnika'] = url
            vse.append({k: s.get(k, '') for k in polya})
        print('   добавлено строк: %d' % len(stroki))
    with open(put, 'w', encoding='utf-8-sig', newline='') as f:
        w = _csv.DictWriter(f, fieldnames=polya, delimiter=';')
        w.writeheader()
        w.writerows(vse)
    print('--- ИТОГ: было %d, стало %d строк. %s (%d байт)'
          % (bylo, len(vse), put, os.path.getsize(put)))
    po_gro = {}
    for s in vse:
        po_gro[s['gro']] = po_gro.get(s['gro'], 0) + 1
    for k, v in sorted(po_gro.items(), key=lambda x: -x[1]):
        print('    %-12s %6d' % (k, v))
    if na_drop_li:
        url_d, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
        try:
            rq = urllib.request.Request(url_d.rstrip('/') + '/' + imya_csv, method='PUT',
                                        data=open(put, 'rb').read())
            rq.add_header('X-Drop-Token', tok)
            print('--- на дроп %s: код %s'
                  % (imya_csv, urllib.request.urlopen(rq, timeout=300).status))
        except Exception as e:  # noqa: BLE001
            print('--- на дроп не вышло: %s' % e)
    return 0


def rezhim_citata(argv):
    """ДОКАЗАТЕЛЬСТВО ЦИТАТОЙ: шапка листа дословно, десять строк данных подряд
    (не выбирая), и перечень ВСЕХ текстовых ячеек листа для доказательства нуля по ИНН.

    python3 tp_gaz.py citata <url> [--strok=10] [--ot=N] [--yacheek=80]
    """
    url = argv[0]
    skolko, ot, yacheek = 10, 0, 80
    for a in argv[1:]:
        if a.startswith('--strok='):
            skolko = int(a.split('=', 1)[1])
        if a.startswith('--ot='):
            ot = int(a.split('=', 1)[1])
        if a.startswith('--yacheek='):
            yacheek = int(a.split('=', 1)[1])
    kod, telo, kon = vzyat(url, timeout=300, predel=60_000_000)
    print('ФАЙЛ: %s' % urllib.parse.unquote(url))
    print('код=%s байт=%d' % (kod, len(telo)))
    if kod != 200:
        return 1
    listy = listy_xlsx(telo) if telo[:2] == b'PK' else listy_xls(telo)
    for imya_lista, stroki in listy:
        zag = vse_zagolovki(stroki)
        print('\n=== ЛИСТ «%s»: строк %d, различных текстовых ячеек %d'
              % (imya_lista, len(stroki), len(zag)))
        print('--- ШАПКА ДОСЛОВНО (первые %d различных текстовых ячеек листа, '
              'в порядке появления):' % yacheek)
        for i, s in enumerate(zag[:yacheek]):
            print('  %3d. %s' % (i + 1, s[:120]))
        # шапка формы 6 -> где какая колонка
        karta, n_shapki = {}, -1
        for i, r in enumerate(stroki[:40]):
            for j, v in enumerate(r):
                n = re.sub(r'\s+', ' ', str(v)).strip().lower()
                for pole, slova in SHAPKA_F6:
                    if n and pole not in karta and any(s in n for s in slova):
                        karta[pole] = j
                        n_shapki = max(n_shapki, i)
        print('--- КОЛОНКИ ФОРМЫ 6, найденные по заголовку: %s (шапка в строке %d)'
              % (karta or 'НЕ НАЙДЕНЫ', n_shapki))
        nach = n_shapki + 1 + ot
        print('--- %d СТРОК ДАННЫХ ПОДРЯД, начиная со строки %d листа (не выбирая):'
              % (skolko, nach))
        pokazano = 0
        for i in range(nach, len(stroki)):
            r = stroki[i]
            if not any(str(v).strip() for v in r):
                continue
            nep = [(j, re.sub(r'\s+', ' ', str(v)).strip())
                   for j, v in enumerate(r) if str(v).strip()]
            print('  строка %5d | %s' % (i, ' ¦ '.join('%d:%s' % (j, v[:44])
                                                       for j, v in nep[:9])))
            pokazano += 1
            if pokazano >= skolko:
                break
        # ДОКАЗАТЕЛЬСТВО НУЛЯ: ищем по ВСЕМ текстовым ячейкам, а не по первым строкам
        for metka, slova in (('ИНН/ОГРН', INN_KOL), ('НАИМЕНОВАНИЕ/ЗАЯВИТЕЛЬ', NAZV_KOL)):
            nash, n = gde_slovo(zag, slova, 8, celikom=(slova is INN_KOL))
            print('--- ПОИСК «%s» ПО ВСЕМ %d ТЕКСТОВЫМ ЯЧЕЙКАМ ЛИСТА: найдено %d%s'
                  % (metka, len(zag), n,
                     ('  ->  ' + ' / '.join(x[:60] for x in nash)) if nash
                     else '   <- КОЛОНКИ НЕТ ВОВСЕ'))
        print('--- КОНТРОЛЬ «%s» по тем же %d ячейкам: %d (обязан быть 0)'
              % (KONTROL_SLOVO, len(zag),
                 sum(1 for s in zag if KONTROL_SLOVO in s.lower())))
    return 0


def rezhim_slova(argv):
    """Быстрый путь для ТЯЖЁЛЫХ xlsx: только таблица строк (sharedStrings).

    ПОЧЕМУ ОН НУЖЕН. Построчный разбор регулярками не справился с файлом
    `P4_F6_fact_0926.xlsx` (3,06 МБ): 15 минут и ни строки вывода, процесс убит
    по таймауту. Это ограничение прибора, а не отсутствие данных, и молчать о нём
    нельзя. Но на вопрос «назван ли заявитель» отвечает уже одна таблица строк:
    все имена потребителей лежат в ней, и читается она за секунды.
    """
    url = argv[0]
    kod, telo, kon = vzyat(url, timeout=300, predel=60_000_000)
    print('файл: код=%s байт=%d' % (kod, len(telo)))
    if kod != 200 or telo[:2] != b'PK':
        print('не xlsx или не открылся')
        return 1
    z = zipfile.ZipFile(io.BytesIO(telo))
    if 'xl/sharedStrings.xml' not in z.namelist():
        print('sharedStrings нет - значения хранятся в ячейках, быстрый путь не годится')
        return 1
    x = z.read('xl/sharedStrings.xml').decode('utf-8', 'replace')
    si = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m)).strip()
          for m in re.findall(r'<si>(.*?)</si>', x, re.S)]
    print('строк в таблице значений: %d' % len(si))
    for metka, slova in (('ИНН/ОГРН', INN_KOL), ('НАИМЕНОВАНИЕ/ЗАЯВИТЕЛЬ', NAZV_KOL),
                         ('АДРЕС/ОБЪЕКТ', ADRES_KOL), ('ОБЪЁМ/МОЩНОСТЬ', OBEM_KOL)):
        est = ([s for s in si if RE_INN_SLOVO.search(s)][:5] if slova is INN_KOL
               else [s for s in si if any(w in s.lower() for w in slova)][:5])
        print('  %-23s %s' % (metka, ' / '.join(e[:52] for e in est) or
                              '<- слова нет ни в одной строке'))
    yur = [s for s in si if FORMY.search(s)]
    inn = [s for s in si if kontrolnaya_inn(s.strip())]
    print('  строк-юрлиц: %d | строк-ИНН (с контрольной суммой): %d' % (len(yur), len(inn)))
    for s in yur[:8]:
        print('    юрлицо: %s' % s[:80])
    print('  КОНТРОЛЬ «%s»: %d (обязан быть 0)'
          % (KONTROL_SLOVO, sum(1 for s in si if KONTROL_SLOVO in s.lower())))
    print('--- ИТОГ: значений %d, из них юрлиц %d' % (len(si), len(yur)))
    return 0


def rezhim_syroy(argv):
    """Сырой показ файла: N первых строк ДОСЛОВНО и все колонки шапки.

    Нужен, когда сводка показала «заявитель назван» - прежде чем радоваться,
    строки надо увидеть глазами, а не поверить счётчику.
    """
    url = argv[0]
    skolko = 18
    for a in argv[1:]:
        if a.startswith('--strok='):
            skolko = int(a.split('=', 1)[1])
    kod, telo, kon = vzyat(url, timeout=300, predel=60_000_000)
    print('файл: код=%s байт=%d' % (kod, len(telo)))
    if kod != 200:
        return 1
    nizh = kon.lower().split('?')[0]
    listy = (listy_xls(telo) if (nizh.endswith('.xls') and telo[:2] != b'PK')
             else listy_xlsx(telo))
    for imya, stroki in listy:
        print('=== лист «%s»: строк %d' % (imya, len(stroki)))
        for i, r in enumerate(stroki[:skolko]):
            nep = [(j, str(v)) for j, v in enumerate(r) if str(v).strip()]
            print(' %3d |%s' % (i, ' ¦ '.join('%d:%s' % (j, v[:40]) for j, v in nep[:14])))
        print(' ... середина листа:')
        for i in range(len(stroki) // 2, min(len(stroki) // 2 + 4, len(stroki))):
            nep = [(j, str(v)) for j, v in enumerate(stroki[i]) if str(v).strip()]
            print(' %3d |%s' % (i, ' ¦ '.join('%d:%s' % (j, v[:40]) for j, v in nep[:14])))
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
    if r.get('nechitaem'):
        print(otstup + 'лист «%s»: ФАЙЛ НЕ ПРОЧИТАН (текста извлечено %d знаков, '
                       'русских слов < 20). Это ноль ПРИБОРА, а не ноль формы.'
              % (r['list'], r.get('znakov', 0)))
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
            # --zanovo: перемерить уже разобранное. Нужно после КАЖДОЙ починки
            # прибора: числа, снятые сломанным разбором, недействительны, а тихо
            # пропущенный файл выглядит как подтверждённый.
            if a in st['razbor'][k] and '--zanovo' not in argv:
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


KOL_ZAYAVITEL = ('наименование потребителя', 'наименование заявителя',
                 'наименование абонента', 'наименование организации',
                 'наименование юридического', 'заявитель', 'потребитель',
                 'застройщик', 'абонент', 'контрагент')


def nazvan_li_zayavitel(l):
    """Назван ли заявитель ПОИМЁННО. Два условия вместе, а не любое из двух.

    Одной колонки мало: «Категория заявителей» тоже содержит слово «заявител»,
    но за ней стоит «Физическое лицо / Юридическое лицо», а не имя. И одних
    юрлиц в строках мало: сама газовая компания печатается в каждой строке.
    Поэтому: нужна колонка ИМЕНИ (не «категория») И не меньше 5 строк с чужим
    юрлицом.
    """
    zag = [z.lower() for z in (l.get('yacheyki_naim') or [])]
    est_imya = any(any(s in z for s in KOL_ZAYAVITEL) and 'категор' not in z
                   for z in zag)
    chuzhih = l.get('strok_s_chuzhim_yurlicom', 0)
    return bool(est_imya and chuzhih >= 5), est_imya, chuzhih


def rezhim_svodka(argv):
    st = chitat()
    import csv as _csv
    put = os.path.join(KATALOG, 'tp-gaz-svodka.csv')
    f = open(put, 'w', encoding='utf-8-sig', newline='')
    w = _csv.writer(f, delimiter=';')
    w.writerow(['organizaciya', 'dom', 'forma', 'adres_fayla', 'list', 'strok_vsego',
                'strok_dannyh', 'kolonka_imeni_zayavitelya', 'strok_s_chuzhim_yurlicom',
                'inn_po_kolonke', 'yacheek_so_slovom_INN', 'est_obem', 'strok_s_datoy',
                'zayavitel_nazvan'])
    print('%-11s %-40s %7s %7s %4s %6s %5s %5s  %s' %
          ('орг', 'форма', 'строк', 'данных', 'ИНН', 'юрлиц', 'объём', 'дата', 'ЗАЯВИТЕЛЬ'))
    itogo = dict(list=0, strok=0, s_imenem=0, s_inn=0, nechitaem=0)
    nashli = []
    for k, fayly in sorted(st.get('razbor', {}).items()):
        dom = (st.get('razdely', {}).get(k) or {}).get('dom', '')
        for a, v in sorted(fayly.items()):
            for l in v.get('listy', []):
                if l.get('oshibka'):
                    continue
                if l.get('nechitaem'):
                    itogo['nechitaem'] += 1
                    print('%-11s %-40s   НЕ ПРОЧИТАН (ноль прибора, не формы)'
                          % (k, (v.get('podpis') or os.path.basename(a))[:40]))
                    continue
                nazvan, est_imya, chuzhih = nazvan_li_zayavitel(l)
                itogo['list'] += 1
                itogo['strok'] += l.get('strok_dannyh', 0)
                if nazvan:
                    itogo['s_imenem'] += 1
                    nashli.append((k, v.get('podpis') or os.path.basename(a), a,
                                   l.get('strok_dannyh', 0), chuzhih))
                if l.get('inn_po_kolonke'):
                    itogo['s_inn'] += 1
                podpis = (v.get('podpis') or os.path.basename(a))[:40]
                print('%-11s %-40s %7d %7d %4d %6d %5s %5d  %s'
                      % (k, podpis, l.get('strok_vsego', 0), l.get('strok_dannyh', 0),
                         l.get('inn_po_kolonke', 0), chuzhih,
                         'да' if l.get('est_kol_obem') or l.get('yacheyki_obem') else 'нет',
                         l.get('strok_s_datoy', 0),
                         'НАЗВАН' if nazvan else ('колонка есть, строк мало'
                                                  if est_imya else 'нет')))
                w.writerow([k, dom, v.get('podpis', ''), a, l.get('list'),
                            l.get('strok_vsego', 0), l.get('strok_dannyh', 0),
                            '; '.join(l.get('yacheyki_naim') or []),
                            chuzhih, l.get('inn_po_kolonke', 0),
                            l.get('yacheyki_inn_vsego', 0),
                            l.get('yacheyki_obem_vsego', 0), l.get('strok_s_datoy', 0),
                            'да' if nazvan else 'нет'])
    f.close()
    print('\n=== ФОРМЫ, ГДЕ ЗАЯВИТЕЛЬ НАЗВАН ПОИМЁННО (%d):' % len(nashli))
    for k, podpis, a, strok, chuzhih in sorted(nashli, key=lambda x: -x[4]):
        print('  %-11s строк %6d, юрлиц %6d | %s' % (k, strok, chuzhih, podpis[:70]))
        print('      %s' % a)
    print('\n--- ИТОГ: листов разобрано %d, строк данных %d, листов с ИМЕНЕМ заявителя %d, '
          'листов с ИНН заявителя %d, не прочитано %d'
          % (itogo['list'], itogo['strok'], itogo['s_imenem'], itogo['s_inn'],
             itogo['nechitaem']))
    print('--- таблица: %s (%d байт)' % (put, os.path.getsize(put)))
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
    if r == 'vygruzka':
        return rezhim_vygruzka(a)
    if r == 'citata':
        return rezhim_citata(a)
    if r == 'dostup':
        return rezhim_dostup(a)
    if r == 'slova':
        return rezhim_slova(a)
    if r == 'syroy':
        return rezhim_syroy(a)
    if r == 'kontrol':
        return rezhim_kontrol(a)
    print('неизвестный режим: %s' % r)
    return 1


if __name__ == '__main__':
    sys.exit(main())
