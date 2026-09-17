# -*- coding: utf-8 -*-
"""Технологическое присоединение к ЭЛЕКТРОСЕТЯМ: есть ли где-нибудь ПОИМЁННЫЙ реестр заявок.

ЗАЧЕМ. ТП к электросетям — самый ранний след будущей стройки: заявку на мощность подают
до проектирования и задолго до закупки компрессора. Если у сетевой организации есть
публичный реестр заявок с наименованием и ИНН заявителя, это канал «предприятие + новая
мощность» за год-два до тендера. Предыдущий агент замерил ОДНУ организацию (Россети Центр,
формы ПП 24) и получил ИНН 0. Владелец: «пока 0 не доказан, я в него не верю». Этот скрипт
доказывает ноль (или опровергает) на ШИРОКОЙ выборке — 18 организаций, все формы подряд.

ЧТО ЗНАЧИТ «ДОКАЗАТЬ НОЛЬ». Не «в первых строках пусто», а: колонки с таким смыслом в файле
НЕТ. Поэтому razbor_fajla() печатает ПОЛНЫЙ список имён колонок (или, для PDF, полный набор
слов-заголовков), и признак «есть заявитель» выводится из имён колонок И из содержимого
(регулярка на 10/12 цифр по всему файлу), а не из одного.

КОНТРОЛИ (правило владельца «у каждого признака свой контроль с заведомо негодным входом»):
  * kontrol_404()  — на каждом хосте дёргается заведомо несуществующий путь
    /zzz-nesushchestvuyushchiy-put-shvarckopfer. Он ОБЯЗАН дать 404/403/410. Если такой путь
    отдаёт 200 — сайт отвечает «мягким 404», и всякий 200 на этом хосте ничего не значит.
  * kontrol_slova() — по каждому разобранному файлу ищется выдуманное слово «щварцкопфер».
    Обязано дать 0. Иначе поиск не ищет, и числу найденных ИНН верить нельзя.
  * ИНН-кандидаты чистятся: другой агент уже ловил «ИНН 348», оказавшиеся хвостами float
    в стоимости, и «юрлиц 3396», оказавшихся самой сетевой компанией в каждой строке.
    Поэтому inn_kandidaty() отбрасывает совпадения внутри более длинного числа, а
    svoi_inn() отдельно считает, сколько кандидатов — это ИНН самой сетевой организации.

ДВА СЛОЯ СЕТИ. Часть хостов закрыта из песочницы (ДРСК отдаёт 451 Unavailable For Legal
Reasons на иностранный IP), часть — с сервера. Скрипт одинаково работает и там и там:
  из песочницы:  python3 seo-texts/tp_elektroseti.py dostup
  с сервера:     python3 seo-texts/zapusk_na_servere.py tp_elektroseti.py dostup
Состояние пишется в KATALOG_SOST (в песочнице — scratchpad, на сервере — C:\\sender\\_ops),
имя файла зависит от слоя, чтобы замеры двух слоёв не затирали друг друга.

КОМАНДЫ
  dostup            — какие хосты отвечают с этого слоя + какие библиотеки есть
  obhod [org...]    — обойти разделы раскрытия, собрать ссылки на формы и файлы
  fajly [org...]    — скачать и разобрать найденные файлы (строки, колонки, ИНН)
  drsk              — раскопать закомментированную таблицу utp.drsk.ru/tpr_reestr
  lk                — публичные проверки статуса заявки на порталах ТП
  svod              — собрать итоговую таблицу из состояния обоих слоёв
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
import zipfile

# Контрольное слово: обязано давать 0 в любом чужом файле. Взято НЕ «щварцкопфер», хотя
# именно его использует наш клиент ЕГРЗ: в выгрузке KOMPRESSORNYE-STANCII-EGRZ.xlsx это
# слово встречается один раз — на листе «Как читать», где описан сам контроль. То есть на
# нашем же положительном контроле счётчик честно показал 1, и это была не поломка фильтра,
# а совпадение с нашей документацией. Чтобы контроль не спорил сам с собой, слово здесь
# своё и больше нигде в репозитории не встречается.
VYDUMANNOE = 'нипрятозаумень'
NET_PUTI = '/zzz-nesushchestvuyushchiy-put-shvarckopfer'   # контрольный путь: обязан давать не-200
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'

NA_SERVERE = os.name == 'nt'
SLOY = 'server' if NA_SERVERE else 'pesochnica'
KATALOG_SOST = (r'C:\sender\_ops' if NA_SERVERE
                else '/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/scratchpad')


def put_sost(imya):
    return os.path.join(KATALOG_SOST, 'tp_seti_%s_%s.json' % (imya, SLOY))


# ---------------------------------------------------------------- каталог организаций
# base — корень сайта; stranicy — страницы, с которых начинаем обход (раздел раскрытия,
# раздел ТП). Пути не угаданы «по смыслу», а взяты из реального обхода: те, что не
# подтвердились, помечены в отчёте своим кодом ответа.
ORGANIZACII = [
    ('rosseti-centr', 'Россети Центр', 'https://www.mrsk-1.ru', [
        '/information/standart/', '/customers/services/tp/', '/clients/fitting/']),
    ('rosseti-cp', 'Россети Центр и Приволжье', 'https://mrsk-cp.ru', [
        '/information/standart/', '/customers/services/tp/', '/clients/fitting/']),
    ('rosseti-volga', 'Россети Волга', 'https://rosseti-volga.ru', [
        '/ru/information-disclosure/', '/ru/clients/tech-connection/', '/ru/']),
    ('rosseti-yug', 'Россети Юг', 'https://rosseti-yug.ru', [
        '/informaciya/', '/tehnologicheskoe-prisoedinenie/', '/']),
    ('rosseti-sk', 'Россети Северный Кавказ', 'https://rossetisk.ru', [
        '/raskritie-informatsii/', '/customer/technical_connection/', '/customer/']),
    ('rosseti-ural', 'Россети Урал', 'https://rosseti-ural.ru', [
        '/disclosure/', '/clients/tp/', '/']),
    ('rosseti-sib', 'Россети Сибирь', 'https://rosseti-sib.ru', [
        '/disclosure/', '/clients/tehprisoedinenie/', '/']),
    ('rosseti-lenenergo', 'Россети Ленэнерго', 'https://rosseti-lenenergo.ru', [
        '/disclosure/', '/tekhnologicheskoe-prisoedinenie/', '/']),
    # Домен НЕ угадан: rosseti-moscow.ru и rosseti-tyumen.ru не резолвятся ни с одного слоя
    # (getaddrinfo failed). Верные — rossetimr.ru и te.ru, взяты со страницы ПАО «Россети»
    # /about/sites/ и подтверждены ответом 403/200 (403 — это ОТВЕТ, WAF, а не «нет хоста»).
    ('rosseti-moscow', 'Россети Московский регион', 'https://rossetimr.ru', [
        '/about/information-disclosure/', '/clients/tp/', '/']),
    ('rosseti-kuban', 'Россети Кубань', 'https://rosseti-kuban.ru', [
        '/informacziya/', '/tehprisoedinenie/', '/']),
    ('rosseti-tyumen', 'Россети Тюмень', 'https://www.te.ru', [
        '/disclosure/', '/clients/', '/']),
    ('rosseti-tomsk', 'Россети Томск', 'https://rosseti-tomsk.ru', [
        '/disclosure/', '/tp/', '/']),
    # Пути НЕ угаданы, а сняты с самой страницы раскрытия: 30 пронумерованных разделов
    # ПП 24. Нас интересуют 16 (наличие техвозможности и поданные заявки), 25 (лица,
    # намеревающиеся перераспределить мощность — та самая Форма 15 с именами),
    # 28 (этапы обработки заявок), 13/14 (перспективная нагрузка центров питания).
    ('rosseti-sz', 'Россети Северо-Запад', 'https://rosseti-sz.ru', [
        '/infodisclosure/2standartdisclosure/',
        '/infodisclosure/2standartdisclosure/16nalichiedostupa/',
        '/infodisclosure/2standartdisclosure/25faces/',
        '/infodisclosure/2standartdisclosure/28etaps/',
        '/infodisclosure/2standartdisclosure/19dogovori/',
        '/infodisclosure/2standartdisclosure/13infofact35-150/',
        '/infodisclosure/2standartdisclosure/14infonagruz35/']),
    ('drsk', 'ДРСК (Дальневосточная РСК)', 'https://www.drsk.ru', [
        '/informacziya/', '/tehprisoedinenie/', '/']),
    ('drsk-utp', 'ДРСК — портал ТП utp.drsk.ru', 'https://utp.drsk.ru', [
        '/tpr_reestr/8', '/tpr_reestr', '/']),
    ('yakutskenergo', 'Якутскэнерго', 'https://yakutskenergo.ru', [
        '/disclosure/', '/clients/', '/']),
    ('mosoblenergo', 'Мособлэнерго', 'https://mosoblenergo.ru', [
        '/disclosure/', '/tehprisoedinenie/', '/']),
    ('oblkommunenergo', 'Облкоммунэнерго (Свердловская обл.)', 'https://oblkommunenergo.ru', [
        '/disclosure/', '/tekhprisoedinenie/', '/']),
    ('iesk', 'Иркутская электросетевая компания', 'https://www.iesk.ru', [
        '/disclosure/', '/tp/', '/']),
    ('rosseti-holding', 'ПАО Россети (головная)', 'https://rosseti.ru', [
        '/investors/information/', '/clients/tp/', '/']),
]

# Порталы личных кабинетов / публичных проверок статуса заявки.
PORTALY = [
    ('portal-tp', 'портал-тп.рф', 'https://xn----7sb7akeedqd.xn--p1ai', ['/']),
    ('lk-rosseti', 'ЛК Россети', 'https://lk.rosseti.ru', ['/']),
    ('utp-mrsk1', 'Портал ТП Россети Центр', 'https://utp.mrsk-1.ru', ['/']),
    ('utp-lenenergo', 'Портал ТП Ленэнерго', 'https://utp.rosseti-lenenergo.ru', ['/']),
    ('utp-drsk', 'Портал ТП ДРСК', 'https://utp.drsk.ru', ['/tpr_reestr/8', '/']),
    ('utp-moscow', 'Портал ТП Россети Московский регион', 'https://utp.rossetimr.ru',
     ['/', '/contacts']),
    ('utp-kuban', 'Портал ТП Россети Кубань', 'https://utp.rosseti-kuban.ru', ['/']),
    ('utp-yug', 'Портал ТП Россети Юг', 'https://utp.rosseti-yug.ru', ['/']),
]

# Слова-маркеры: какие ссылки в разделе раскрытия нас интересуют.
INTERES = re.compile(
    r'реестр|журнал\s*учёт|журнал\s*учет|поданн\w*\s+заяв|заяв\w*\s+на\s+тех|перечень\s+заключ'
    r'|заключённ\w*\s+договор|заключенн\w*\s+договор|этап\w*\s+обработк|о\s+ходе\s+исполнен'
    r'|присоединен|технологическ|свободн\w*\s+.{0,20}мощност|центр\w*\s+питания|тп\b'
    # «перераспределение максимальной мощности» — Форма 15. Единственная форма ПП 24,
    # где по букве формы есть колонка «Лицо, намеревающееся осуществить перераспределение»,
    # то есть НАИМЕНОВАНИЕ. Без этих слов обход её пропускал.
    r'|перераспредел|намеревающ|мощност', re.I)
FAJL = re.compile(r'\.(xlsx?|xlsm|csv|zip|rar|pdf|docx?|ods)(\?|$)', re.I)


# ---------------------------------------------------------------- сеть
# Российский корневой УЦ Минцифры. Половина сайтов сетевых организаций (Ленэнерго, Волга,
# Томск, Якутскэнерго) выдаёт CERTIFICATE_VERIFY_FAILED не потому, что сайт битый, а потому,
# что их сертификат подписан этим УЦ, которого нет в стандартном хранилище. Лечится ДОБАВЛЕНИЕМ
# корня, а не отключением проверки: проверка остаётся включённой, просто список доверенных
# корней пополняется тем, что реально подписал эти сайты.
RU_CA_URL = 'https://gu-st.ru/content/Other/doc/russiantrustedca.pem'
_CA_PUT = os.path.join(KATALOG_SOST, 'russiantrustedca.pem')
_CTX = None


def _ctx():
    global _CTX
    if _CTX is not None:
        return _CTX
    c = ssl.create_default_context()
    put = os.environ.get('REQUESTS_CA_BUNDLE') or '/root/.ccr/ca-bundle.crt'
    if os.path.exists(put):
        try:
            c.load_verify_locations(put)
        except Exception:  # noqa: BLE001
            pass
    if not os.path.exists(_CA_PUT):
        try:
            os.makedirs(KATALOG_SOST, exist_ok=True)
            r = urllib.request.urlopen(urllib.request.Request(
                RU_CA_URL, headers={'User-Agent': UA}), timeout=40)
            d = r.read()
            if b'BEGIN CERTIFICATE' in d:
                open(_CA_PUT, 'wb').write(d)
        except Exception:  # noqa: BLE001
            pass
    if os.path.exists(_CA_PUT):
        try:
            c.load_verify_locations(_CA_PUT)
        except Exception:  # noqa: BLE001
            pass
    _CTX = c
    return c


def normalizovat(url):
    """Проценты в путь и пробелы прочь. Ссылка на реестр ДРСК содержит кириллицу и ПРОБЕЛЫ
    («/file/566/Реестр заявок на подключение ... .xlsx»), и urllib на такой ссылке падает
    с InvalidURL «URL can't contain control characters» — то есть файл выглядел как
    недоступный, хотя запрос до сервера просто не уходил."""
    c = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        c.scheme, c.netloc.encode('idna').decode('ascii') if any(ord(x) > 127 for x in c.netloc)
        else c.netloc,
        urllib.parse.quote(c.path, safe="/%:@!$&'()*+,;=~-._"),
        urllib.parse.quote(c.query, safe="=&%:@/?!$'()*+,;~-._"), c.fragment))


def dostat(url, timeout=40, maks=None):
    """Вернуть (код, байты, итоговый_url, ошибка). Код ответа — это ОТВЕТ: 403/451 значит,
    что хост ответил, и это не то же самое, что «не ответил вовсе»."""
    url = normalizovat(url)
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    })
    try:
        r = urllib.request.urlopen(req, timeout=timeout, context=_ctx())
        d = r.read(maks) if maks else r.read()
        return r.status, d, r.geturl(), ''
    except urllib.error.HTTPError as e:
        try:
            d = e.read(4096)
        except Exception:  # noqa: BLE001
            d = b''
        return e.code, d, url, ''
    except Exception as e:  # noqa: BLE001
        return 0, b'', url, '%s: %s' % (type(e).__name__, str(e)[:120])


def tekst(b):
    for k in ('utf-8', 'cp1251', 'koi8-r'):
        try:
            return b.decode(k)
        except Exception:  # noqa: BLE001
            continue
    return b.decode('utf-8', 'replace')


def kontrol_404(base):
    """Заведомо негодный путь обязан дать не-200. Иначе 200 на этом хосте ничего не значит.

    Три ИСХОДА, а не два: 'strogiy' — не-200, признакам 200 на этом хосте можно верить;
    'myagkiy404' — хост отдал 200 на заведомо несуществующий путь, значит любой его 200
    ничего не доказывает; 'ne_otvetil' — хост не ответил вовсе, контроль НЕ проведён
    (первая версия скрипта писала здесь «мягкий 404», то есть обвиняла молчащий хост в том,
    чего он не делал)."""
    k, d, _, e = dostat(base.rstrip('/') + NET_PUTI, timeout=25, maks=4000)
    if not k:
        ish = 'ne_otvetil'
    elif k == 200:
        ish = 'myagkiy404'
    else:
        ish = 'strogiy'
    return {'kod': k, 'oshibka': e, 'ishod': ish, 'godnyy': ish == 'strogiy'}


# ---------------------------------------------------------------- разбор HTML
SSYLKA = re.compile(r'<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
TEG = re.compile(r'<[^>]+>')
SUSH = {'&nbsp;': ' ', '&amp;': '&', '&quot;': '"', '&#039;': "'", '&laquo;': '«',
        '&raquo;': '»', '&mdash;': '—', '&ndash;': '–', '&lt;': '<', '&gt;': '>'}


def ochistit(s):
    s = TEG.sub(' ', s)
    for a, b in SUSH.items():
        s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip()


def ssylki(html, base_url):
    out = []
    for h, t in SSYLKA.findall(html):
        t = ochistit(t)
        if not h or h.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue
        out.append((urllib.parse.urljoin(base_url, h), t))
    return out


def kommentarii(html):
    """HTML-комментарии длиннее 200 знаков — там у ДРСК спрятана таблица реестра."""
    return [c for c in re.findall(r'<!--(.*?)-->', html, re.S) if len(c) > 200]


# ---------------------------------------------------------------- разбор файлов
INN_RE = re.compile(r'(?<!\d)(\d{10}|\d{12})(?!\d)')
IMENA_INN = re.compile(r'\bинн\b|налогоплательщик', re.I)
# КТО ТАКОЙ «ЗАЯВИТЕЛЬ» В ИМЕНИ КОЛОНКИ. Первая версия искала слово «наименован» и из-за
# этого считала заявителем «Наименование филиала» и «Наименование центра питания», то есть
# отчитывалась «имя заявителя есть» на формах, где названа САМА сетевая организация — ровно
# та ловушка, на которой уже погорел замер «юрлиц 3396». И одновременно она НЕ знала слова
# «Застройщик», поэтому на нашей же выгрузке ЕГРЗ, где застройщик назван у 465 записей из
# 495, отвечала «заявителя нет». Оба промаха поймал положительный контроль (команда
# kontrol), и оба лечатся здесь: сначала смотрим, похоже ли имя колонки на КОНТРАГЕНТА,
# потом вычёркиваем имена, которые заведомо описывают саму сетевую организацию или объект.
IMENA_ZAYAV = re.compile(
    # «потребител» само по себе НЕ годится: колонка «Категория присоединения потребителей
    # услуг по передаче электрической энергии в разбивке по мощности» — это показатель
    # качества, а не контрагент, и она давала ложное «имя заявителя есть» у Иркутской
    # электросетевой сразу на десятке файлов. Годится только «наименование потребителя».
    r'заявител|контрагент|наименовани\w*\s+потребител|абонент|Ф\.?И\.?О\b|\bфио\b'
    r'|застройщик|проектировщик'
    r'|заказчик|собственник|владелец|юридическ\w*\s*лиц|физическ\w*\s*лиц|клиент'
    r'|наименован\w*\s+(?:организац|компан|предприят|общества|юридическ|заявител|лица)'
    r'|лицо,?\s+намеревающ|наименование$|наименование\b(?!\s*(?:филиал|сетев|центр|проект|мероприят|общества|объект|услуг|документ|показател))',
    re.I)
# Заголовок ГРАФЫ, называющей контрагента, — для плоского текста (pdf).
ZAGOLOVOK_GRAFY = re.compile(
    r'наименовани[ея]\s+заявител|наименовани[ея]\s+(?:юридического\s+лица|организации|предприятия)'
    r'|ф\.?\s*и\.?\s*о\.?\s+заявител|заявитель\s*\(наименование|застройщик'
    r'|лицо,?\s+намеревающ|наименовани[ея]\s+потребител|наименовани[ея]\s+контрагент', re.I)
NE_KONTRAGENT = re.compile(
    r'филиал|сетев\w*\s+организац|наименование\s+общества|центр\w*\s+питания|подстанц'
    r'|наименование\s+проект|наименование\s+мероприят|наименование\s+объект|балансов'
    r'|наименование\s+услуг|наименование\s+показател|наименование\s+документ'
    r'|категори\w*\s+присоединен|показател|в\s+разбивке'
    # «Наименование и описание объекта инфраструктуры, к которому запрашивается доступ» —
    # это описание ЛИНИИ, а не контрагент. Исключение по «наименование объект» его не ловило,
    # потому что между словами стоит «и описание», и колонка попадала в выборку значений
    # заявителя: 12 046 «значений» вместо 6 031, половина из них — описания опор ВЛ.
    r'|описани\w*\s+объект|объект\w*\s+инфраструктур', re.I)
IMENA_ADRES = re.compile(r'адрес|местополож|кадастр|расположен|населённ|населенн|участок', re.I)
IMENA_MOSCH = re.compile(r'мощност|кВт|кВА|MW', re.I)
IMENA_DATA = re.compile(r'дата|срок|период|год\b', re.I)
IMENA_NOMER = re.compile(r'номер|№|рег\.?\s*н', re.I)


def stroki_xlsx(b, maks_strok=200000):
    """Разобрать xlsx без сторонних библиотек: это zip с XML. Возвращает {лист: [строки]}."""
    out = {}
    z = zipfile.ZipFile(io.BytesIO(b))
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        s = z.read('xl/sharedStrings.xml').decode('utf-8', 'replace')
        for si in re.findall(r'<si>(.*?)</si>', s, re.S):
            shared.append(ochistit(''.join(re.findall(r'<t[^>]*>(.*?)</t>', si, re.S))))
    wb = z.read('xl/workbook.xml').decode('utf-8', 'replace') if 'xl/workbook.xml' in z.namelist() else ''
    imena = re.findall(r'<sheet[^>]*name="([^"]*)"', wb)
    listy = sorted(n for n in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$', n))
    for i, n in enumerate(listy):
        imya = imena[i] if i < len(imena) else n
        s = z.read(n).decode('utf-8', 'replace')
        rows = []
        for rm in re.finditer(r'<row\b[^>]*>(.*?)</row>', s, re.S):
            cells = []
            for cm in re.finditer(r'<c\b([^>]*)>(.*?)</c>', rm.group(1), re.S):
                atr, inner = cm.group(1), cm.group(2)
                v = re.search(r'<v>(.*?)</v>', inner, re.S)
                if v is None:
                    it = re.findall(r'<t[^>]*>(.*?)</t>', inner, re.S)
                    cells.append(ochistit(''.join(it)) if it else '')
                    continue
                val = v.group(1)
                if 't="s"' in atr:
                    idx = int(val)
                    cells.append(shared[idx] if idx < len(shared) else '')
                else:
                    cells.append(val)
            rows.append(cells)
            if len(rows) >= maks_strok:
                break
        out[imya] = rows
    return out


def stroki_xls(b):
    try:
        import xlrd
    except ImportError:
        return None
    kn = xlrd.open_workbook(file_contents=b)
    out = {}
    for sh in kn.sheets():
        rows = []
        for i in range(sh.nrows):
            rows.append([('' if c is None else str(c)) for c in sh.row_values(i)])
        out[sh.name] = rows
    return out


def stroki_csv(b):
    import csv
    t = tekst(b)
    dial = ';' if t.count(';') > t.count(',') else ','
    return {'csv': [r for r in csv.reader(io.StringIO(t), delimiter=dial)]}


def tekst_pdf(b):
    try:
        from pdfminer.high_level import extract_text
    except Exception:  # noqa: BLE001
        return None
    try:
        return extract_text(io.BytesIO(b))
    except Exception:  # noqa: BLE001
        return None


def zagolovok(rows):
    """Найти строку заголовка: первая строка, где >=2 непустых ячейки и есть буквы."""
    for i, r in enumerate(rows[:40]):
        nep = [c for c in r if str(c).strip()]
        if len(nep) >= 2 and sum(1 for c in nep if re.search(r'[А-Яа-яA-Za-z]', str(c))) >= 2:
            return i, [str(c).strip() for c in r]
    return -1, []


def inn_kandidaty(vse_tekst):
    """10/12-значные числа, не входящие в более длинное число и не являющиеся ХВОСТОМ ДРОБИ.

    Замер, из-за которого добавлена вторая проверка: в Форме 14 «резервируемая максимальная
    мощность» стоят значения вида 834.3420000000001 — хвост двоичного округления. Наивная
    регулярка выдёргивала оттуда 10 цифр и отчитывалась «ИНН найден 1». Ровно та же ошибка
    («ИНН 348») уже ловилась другим агентом на стоимостях. Поэтому совпадение, слева от
    которого стоит точка или запятая (то есть мы внутри дробной части), — не ИНН."""
    out = []
    for m in INN_RE.finditer(vse_tekst):
        i = m.start()
        if i > 0 and vse_tekst[i - 1] in '.,':
            continue
        out.append(m.group(1))
    return out


def drop_polozhit(imya, b):
    """Положить сырой файл на дроп. Нужно для слоя СЕРВЕРА: там нет ни xlrd, ни pdfminer,
    то есть .xls и .pdf с закрытых для песочницы хостов иначе не разобрать вовсе."""
    url = os.environ.get('DROP_URL')
    tok = os.environ.get('DROP_TOKEN')
    if not url or not tok:
        return 'нет DROP_URL/DROP_TOKEN в окружении слоя %s' % SLOY
    granica = '----tpseti%d' % int(time.time())
    telo = (('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n'
             'Content-Type: application/octet-stream\r\n\r\n' % (granica, imya)).encode()
            + b + ('\r\n--%s--\r\n' % granica).encode())
    req = urllib.request.Request(url.rstrip('/') + '/upload', data=telo, headers={
        'X-Drop-Token': tok, 'User-Agent': UA,
        'Content-Type': 'multipart/form-data; boundary=%s' % granica})
    try:
        r = urllib.request.urlopen(req, timeout=180, context=_ctx())
        return 'дроп %s: %s' % (r.status, imya)
    except Exception as e:  # noqa: BLE001
        return 'дроп ошибка %s: %s' % (type(e).__name__, str(e)[:120])


def razbor_zip(url, b, svoi=()):
    """Архив: разобрать каждый вложенный лист-файл. Россети Северо-Запад кладёт помесячные
    сведения именно так — zip из xlsx по филиалам, поэтому без этого файл виден как 0 строк."""
    try:
        z = zipfile.ZipFile(io.BytesIO(b))
    except Exception as e:  # noqa: BLE001
        return None
    vnutri = []
    for i in z.infolist():
        try:
            imya = i.filename.encode('cp437').decode('cp866')
        except Exception:  # noqa: BLE001
            imya = i.filename
        if not re.search(r'\.(xlsx?|xlsm|csv|pdf)$', imya, re.I):
            continue
        try:
            vb = z.read(i.filename)
        except Exception:  # noqa: BLE001
            continue
        r = razbor_fajla(url + '!' + imya, vb, svoi)
        r['vnutri_arhiva'] = imya
        vnutri.append(r)
        if len(vnutri) >= 30:
            break
    return vnutri


def razbor_fajla(url, b, svoi=()):
    """Числа по файлу: строк, колонки, есть ли заявитель/ИНН/адрес/мощность/дата."""
    it = {'url': url, 'bajt': len(b), 'tip': '', 'listov': 0, 'strok': 0,
          'kolonki': [], 'kontrol_vydumannoe': None, 'oshibka': ''}
    sig = b[:4]
    tabl = None
    try:
        if sig[:2] == b'PK':
            # PK — это и xlsx, и docx, и обычный zip. Различаем по содержимому, а не по
            # расширению в ссылке: у Россети Северо-Запад помесячные формы лежат .zip,
            # а внутри xlsx по филиалам.
            imena = zipfile.ZipFile(io.BytesIO(b)).namelist()
            if 'xl/workbook.xml' in imena:
                it['tip'] = 'xlsx'
                tabl = stroki_xlsx(b)
            elif any(n.startswith('word/') for n in imena):
                it['tip'] = 'docx'
                tabl = None
            else:
                it['tip'] = 'zip'
                it['vnutri'] = razbor_zip(url, b, svoi)
                it['vnutri_fajlov'] = len(it['vnutri'] or [])
                it['strok'] = sum(v.get('strok') or 0 for v in (it['vnutri'] or []))
                it['inn_kandidatov'] = sum(v.get('inn_kandidatov') or 0 for v in (it['vnutri'] or []))
                it['inn_unikalnyh'] = len({x for v in (it['vnutri'] or [])
                                           for x in v.get('inn_primery') or []})
                it['ooo_vhozhdeniy'] = sum(v.get('ooo_vhozhdeniy') or 0 for v in (it['vnutri'] or []))
                it['kolonki'] = [g for v in (it['vnutri'] or []) for g in v.get('kolonki') or []]
                it['kontrol_vydumannoe'] = sum(v.get('kontrol_vydumannoe') or 0
                                               for v in (it['vnutri'] or []))
                for pr in ('imya_inn', 'imya_zayavitel', 'imya_adres', 'imya_moschnost', 'imya_data'):
                    it[pr] = any(v.get(pr) for v in (it['vnutri'] or []))
                return it
        elif sig == b'\xd0\xcf\x11\xe0':
            it['tip'] = 'xls'
            tabl = stroki_xls(b)
            if tabl is None:
                it['oshibka'] = 'нет xlrd на слое %s' % SLOY
                it['na_drop'] = drop_polozhit('tpseti_' + re.sub(r'\W+', '_', url)[-80:] + '.xls', b)
        elif sig[:4] == b'%PDF':
            it['tip'] = 'pdf'
        elif b'<html' in b[:3000].lower() or b'<!doctype html' in b[:3000].lower():
            it['tip'] = 'html'
        else:
            it['tip'] = 'csv?'
            tabl = stroki_csv(b)
    except Exception as e:  # noqa: BLE001
        it['oshibka'] = '%s: %s' % (type(e).__name__, str(e)[:150])

    if it['tip'] == 'pdf':
        t = tekst_pdf(b)
        if t is None:
            it['oshibka'] = 'pdf не разобран (нет pdfminer на слое %s)' % SLOY
            it['na_drop'] = drop_polozhit('tpseti_' + re.sub(r'\W+', '_', url)[-80:] + '.pdf', b)
            return it
        it['strok'] = t.count('\n')
        it['znakov'] = len(t)
        vse = t
        it['kolonki'] = []
        it['pdf_slova_zagolovkov'] = sorted({w for w in re.findall(r'[А-Яа-яЁё]{4,}', t[:4000])})[:40]
    elif tabl:
        it['listov'] = len(tabl)
        vsego = 0
        kol = []
        for imya, rows in tabl.items():
            vsego += max(0, len(rows))
            i, z = zagolovok(rows)
            if z:
                kol.append({'list': imya, 'strok': len(rows), 'stroka_zagolovka': i,
                            'kolonki': [c for c in z if c][:60]})
        it['strok'] = vsego
        it['kolonki'] = kol
        vse = '\n'.join('\t'.join(str(c) for c in r) for rows in tabl.values() for r in rows)
    else:
        vse = tekst(b)
        it['strok'] = vse.count('\n')

    # контроль: выдуманное слово обязано дать 0
    it['kontrol_vydumannoe'] = vse.lower().count(VYDUMANNOE)
    # Признаки считаем ПО КАЖДОЙ КОЛОНКЕ ОТДЕЛЬНО, а не по склейке всех имён в одну строку:
    # на склейке «Наименование филиала | Запрашиваемая мощность» вычёркивание не работает,
    # потому что исключающее слово и подходящее слово оказываются в одном тексте.
    kolonki = [c for gr in (it['kolonki'] or []) for c in gr.get('kolonki', [])]
    if kolonki:
        zayav = [c for c in kolonki if IMENA_ZAYAV.search(c) and not NE_KONTRAGENT.search(c)]
        it['imya_inn'] = any(IMENA_INN.search(c) for c in kolonki)
        it['imya_zayavitel'] = bool(zayav)
        it['kolonki_zayavitelya'] = zayav[:6]
        it['imya_adres'] = any(IMENA_ADRES.search(c) for c in kolonki)
        it['imya_moschnost'] = any(IMENA_MOSCH.search(c) for c in kolonki)
        it['imya_data'] = any(IMENA_DATA.search(c) for c in kolonki)
    else:
        # У pdf колонок как таковых нет — pdfminer отдаёт текст. Здесь НЕЛЬЗЯ искать просто
        # слово «заявитель»: оно стоит в любом пояснительном абзаце («заявки заявителей»),
        # и реестр Россети Кубань из-за этого помечался как «имя заявителя есть», хотя имён
        # в нём нет ни одного. Поэтому для плоского текста ищем именно ЗАГОЛОВОК ГРАФЫ.
        golova = re.sub(r'\s+', ' ', vse[:60000])
        it['imya_inn'] = bool(IMENA_INN.search(golova))
        it['imya_zayavitel'] = bool(ZAGOLOVOK_GRAFY.search(golova))
        it['imya_adres'] = bool(IMENA_ADRES.search(golova))
        it['imya_moschnost'] = bool(IMENA_MOSCH.search(golova))
        it['imya_data'] = bool(IMENA_DATA.search(golova))
        it['zagolovok_grafy_naydeno'] = [re.sub(r'\s+', ' ', m.group(0))[:80]
                                         for m in ZAGOLOVOK_GRAFY.finditer(golova)][:5]
    # Сколько разных юрлиц реально названо в файле и не одно ли это имя на все строки:
    # «ПАО "Россети Кубань"» напечатано 4550 раз, и без этого счёта оно выглядит как
    # 4550 найденных предприятий.
    # Пробелы схлопываем ВКЛЮЧАЯ ПЕРЕВОДЫ СТРОК: pdfminer рвёт «ПАО "Россети \n Кубань"»
    # пополам, и счётчик, нормализующий только пробелы и табы, насчитывал 0 юрлиц в файле,
    # где имя сетевой компании напечатано 4550 раз.
    uL = re.findall(r'(?:ООО|ОАО|ПАО|ЗАО|АО|ФГУП|ГУП|МУП)\s*[«"][^»"]{2,70}[»"]',
                    re.sub(r'\s+', ' ', vse))
    imena_ur = [re.sub(r'\s+', ' ', x).strip() for x in uL]
    it['yurlic_upominaniy'] = len(imena_ur)
    it['yurlic_unikalnyh'] = len(set(imena_ur))
    it['yurlic_primery'] = sorted(set(imena_ur))[:5]
    kand = inn_kandidaty(vse)
    it['inn_kandidatov'] = len(kand)
    it['inn_unikalnyh'] = len(set(kand))
    it['inn_svoi'] = sum(1 for k in kand if k in svoi)
    it['inn_primery'] = sorted(set(kand))[:8]
    it['ooo_vhozhdeniy'] = len(re.findall(r'\bООО\b|\bАО\b|\bПАО\b|\bЗАО\b', vse))
    return it


# ---------------------------------------------------------------- команды
def cmd_dostup(argv):
    """Кто отвечает с этого слоя. Код ответа — это ответ; ноль в колонке kod = не ответил вовсе."""
    biblio = {}
    for m in ('xlrd', 'openpyxl', 'pdfminer.high_level', 'requests'):
        try:
            __import__(m)
            biblio[m] = 'есть'
        except Exception as e:  # noqa: BLE001
            biblio[m] = type(e).__name__
    print('слой=%s python=%s библиотеки=%s' % (SLOY, sys.version.split()[0], biblio))
    res = []
    for kod_org, imya, base, _ in ORGANIZACII + [(a, b, c, d) for a, b, c, d in PORTALY]:
        k, d, u, e = dostat(base + '/', timeout=30, maks=200000)
        kk = kontrol_404(base)
        res.append({'org': kod_org, 'imya': imya, 'base': base, 'kod': k, 'bajt': len(d),
                    'oshibka': e, 'kontrol404': kk})
        print('%-22s %-4s %8d  контроль404=%s/%s  %s' % (
            kod_org, k or 'нет', len(d), kk['kod'], kk['ishod'], e[:60]))
    with open(put_sost('dostup'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    zhiv = [r for r in res if r['kod'] and r['kod'] < 400]
    print('ИТОГ dostup слой=%s: ответили 2xx/3xx %d из %d; не ответили вовсе %d'
          % (SLOY, len(zhiv), len(res), sum(1 for r in res if not r['kod'])))
    print('файл: %s' % put_sost('dostup'))


VHOD = re.compile(r'раскрыти|стандарт\s+раскрыт|технологическ\w*\s+присоединен|потребител|клиент',
                  re.I)


def sohranit_obhod(itog):
    p = put_sost('obhod')
    staroe = {}
    if os.path.exists(p):
        try:
            staroe = json.load(open(p, encoding='utf-8'))
        except Exception:  # noqa: BLE001
            staroe = {}
    staroe.update(itog)
    os.makedirs(KATALOG_SOST, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(staroe, f, ensure_ascii=False, indent=1)


def cmd_obhod(argv):
    """Обойти сайт организации вширь и собрать ссылки на формы и файлы.

    Пути разделов НЕ угадываются: обход стартует с корня и идёт по ссылкам, ТЕКСТ которых
    говорит «раскрытие» или «технологическое присоединение», на глубину 3. Стартовые пути
    из каталога добавлены как подсказка, а не как условие: если такого пути нет, он просто
    даст свой код ответа и будет виден в отчёте."""
    tolko = set(a for a in argv if not a.startswith('-'))
    predel = 120
    for a in argv:
        if a.startswith('--stranic='):
            predel = int(a.split('=', 1)[1])
    itog = {}
    for kod_org, imya, base, puti in ORGANIZACII:
        if tolko and kod_org not in tolko:
            continue
        dom = urllib.parse.urlparse(base).netloc
        zap = {'imya': imya, 'base': base, 'stranicy': [], 'kandidaty': [], 'fajly': [],
               'kontrol404': kontrol_404(base)}
        vidno = set()
        ochered = [(base + '/', 0)] + [(base + p, 0) for p in puti]
        while ochered and len(vidno) < predel:
            u, g = ochered.pop(0)
            if u in vidno:
                continue
            vidno.add(u)
            k, d, fin, e = dostat(u, timeout=35, maks=4000000)
            zap['stranicy'].append({'url': u, 'kod': k, 'bajt': len(d), 'glubina': g,
                                    'oshibka': e})
            if k != 200 or not d:
                continue
            h = tekst(d)
            kom = kommentarii(h)
            if kom:
                zap.setdefault('kommentarii', []).append(
                    {'url': u, 'shtuk': len(kom), 'znakov': sum(len(c) for c in kom),
                     'strok_tr': sum(len(re.findall(r'<tr\b', c, re.I)) for c in kom)})
            for su, st in ssylki(h, fin):
                if not su.startswith(('http://', 'https://')):
                    continue
                su = su.split('#')[0]
                if FAJL.search(su):
                    if INTERES.search(st + ' ' + urllib.parse.unquote(su)):
                        if not any(f['url'] == su for f in zap['fajly']):
                            zap['fajly'].append({'url': su, 'tekst': st[:220], 'so': u})
                    continue
                # Поддомены СВОЕГО домена — тоже свои: у Россети Северо-Запад весь раздел
                # «Потребителям» живёт на clients.rosseti-sz.ru, и строгое равенство
                # netloc отрезало его целиком.
                nl = urllib.parse.urlparse(su).netloc
                if nl != dom and not (nl.endswith('.' + dom) or dom.endswith('.' + nl)):
                    continue
                if INTERES.search(st) and len(st) > 6:
                    if not any(c['url'] == su for c in zap['kandidaty']):
                        zap['kandidaty'].append({'url': su, 'tekst': st[:220], 'so': u})
                if g < 3 and su not in vidno and (INTERES.search(st) or VHOD.search(st)):
                    ochered.append((su, g + 1))
        itog[kod_org] = zap
        print('%-22s страниц=%d (ответили 200: %d) кандидатов=%d файлов=%d' % (
            kod_org, len(zap['stranicy']), sum(1 for s in zap['stranicy'] if s['kod'] == 200),
            len(zap['kandidaty']), len(zap['fajly'])))
        sys.stdout.flush()
        # Сохраняем ПОСЛЕ КАЖДОЙ организации. Первая версия писала состояние только в самом
        # конце: прогон на восьми сайтах упёрся в таймаут и потерял всё сделанное — час
        # обхода превратился в пустой файл.
        sohranit_obhod(itog)
    sohranit_obhod(itog)
    print('ИТОГ obhod: организаций %d, файлов всего %d -> %s'
          % (len(itog), sum(len(v['fajly']) for v in itog.values()), put_sost('obhod')))


def cmd_fajly(argv):
    """Скачать и разобрать найденные файлы."""
    tolko = set(a for a in argv if not a.startswith('-'))
    p = put_sost('obhod')
    if not os.path.exists(p):
        print('нет %s — сначала obhod' % p)
        return
    obh = json.load(open(p, encoding='utf-8'))
    itog = {}
    n = 0
    for kod_org, zap in obh.items():
        if tolko and kod_org not in tolko:
            continue
        svoi = set()
        res = []
        for f in zap.get('fajly', [])[:40]:
            k, b, _, e = dostat(f['url'], timeout=90)
            if k != 200 or not b:
                res.append({'url': f['url'], 'tekst': f['tekst'], 'kod': k, 'oshibka': e})
                continue
            r = razbor_fajla(f['url'], b, svoi)
            r['tekst'] = f['tekst']
            r['kod'] = k
            res.append(r)
            n += 1
            print('  %-14s %-5s строк=%-7s ИНН-канд=%-5s ООО=%-5s контроль=%s | %s'
                  % (kod_org, r.get('tip'), r.get('strok'), r.get('inn_kandidatov'),
                     r.get('ooo_vhozhdeniy'), r.get('kontrol_vydumannoe'), f['tekst'][:60]))
            sys.stdout.flush()
        itog[kod_org] = res
    pf = put_sost('fajly')
    staroe = json.load(open(pf, encoding='utf-8')) if os.path.exists(pf) else {}
    staroe.update(itog)
    with open(pf, 'w', encoding='utf-8') as f:
        json.dump(staroe, f, ensure_ascii=False, indent=1)
    print('ИТОГ fajly: разобрано %d -> %s' % (n, pf))


def cmd_drsk(argv):
    """Откуда грузится закомментированная таблица реестра заявок ДРСК."""
    baza = 'https://utp.drsk.ru'
    out = {'kontrol404': kontrol_404(baza), 'stranicy': [], 'skripty': [], 'api': []}
    print('контроль404 utp.drsk.ru: %s' % out['kontrol404'])
    # /tpr_reestr/N — постраничная нумерация разделов «Реестры заявок на ТП». Перебираем
    # весь диапазон: заголовок «по Хабаровскому краю» на /8 значит, что соседние номера —
    # другие регионы, и брать только один — это мерить один регион вместо пяти.
    stranicy = ['/tpr_reestr/%d' % i for i in range(1, 16)] + ['/tpr_reestr', '/']
    sobrano_js = set()
    for p in stranicy:
        u = baza + p
        k, d, fin, e = dostat(u, timeout=40, maks=4000000)
        h = tekst(d)
        kom = kommentarii(h)
        zap = {'url': u, 'kod': k, 'bajt': len(d), 'oshibka': e,
               'kommentariev': len(kom),
               'znakov_v_kommentariyah': sum(len(c) for c in kom)}
        # в комментариях ищем таблицу и её заголовки
        for c in kom:
            if '<t' in c.lower() or 'тр' in c.lower():
                th = [ochistit(x) for x in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', c, re.S | re.I)]
                if th:
                    zap.setdefault('yachejki_iz_kommentariya', th[:60])
                    zap['strok_tr_v_kommentarii'] = len(re.findall(r'<tr\b', c, re.I))
        # таблицы вне комментариев
        zap['tablic_v_html'] = len(re.findall(r'<table\b', h, re.I))
        zap['strok_tr_v_html'] = len(re.findall(r'<tr\b', h, re.I))
        # ЧТО В ТАБЛИЦАХ. Печатаем ячейки, а не «таблиц 11»: заголовок реестра может
        # оказаться в любой из них, а имя колонки угадывать нельзя.
        zap['tablicy'] = []
        for tm in re.finditer(r'<table\b.*?</table>', h, re.S | re.I):
            tb = tm.group(0)
            yach = [ochistit(x) for x in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', tb, re.S | re.I)]
            yach = [y for y in yach if y]
            if yach:
                zap['tablicy'].append({'strok_tr': len(re.findall(r'<tr\b', tb, re.I)),
                                       'yacheek': len(yach), 'primery': yach[:25]})
        # ФОРМЫ: публичный поиск по реестру — это форма с полем. Печатаем action и имена полей.
        zap['formy'] = []
        for fm in re.finditer(r'<form\b([^>]*)>(.*?)</form>', h, re.S | re.I):
            zap['formy'].append({
                'atributy': re.sub(r'\s+', ' ', fm.group(1))[:200],
                'polya': re.findall(r'<(?:input|select|textarea)[^>]*name=["\']([^"\']+)', fm.group(2), re.I)})
        # Заголовок страницы и её собственные ссылки на файлы: реестр может быть выложен
        # не таблицей, а вложением.
        zt = re.search(r'<title[^>]*>(.*?)</title>', h, re.S | re.I)
        zap['title'] = ochistit(zt.group(1)) if zt else ''
        zag = [ochistit(x) for x in re.findall(r'<h[1-4][^>]*>(.*?)</h[1-4]>', h, re.S | re.I)]
        zap['zagolovki'] = [x for x in zag if x][:15]
        zap['fajly'] = [{'url': su, 'tekst': st[:120]} for su, st in ssylki(h, fin)
                        if FAJL.search(su)][:40]
        zap['ssylki_reestr'] = [{'url': su, 'tekst': st[:120]} for su, st in ssylki(h, fin)
                                if re.search(r'реестр|заяв', st, re.I)][:40]
        out['stranicy'].append(zap)
        kratko = {kk: zap[kk] for kk in ('url', 'kod', 'title', 'zagolovki', 'strok_tr_v_html',
                                         'kommentariev', 'strok_tr_v_kommentarii')}
        kratko['fajlov'] = len(zap['fajly'])
        kratko['ssylok_reestr'] = len(zap['ssylki_reestr'])
        print(json.dumps(kratko, ensure_ascii=False)[:900])
        for f in zap['fajly'][:10]:
            print('    файл: %s | %s' % (f['url'][-90:], f['tekst'][:60]))
        for f in zap['ssylki_reestr'][:10]:
            print('    рее:  %s | %s' % (f['url'][-90:], f['tekst'][:60]))
        for su, _ in ssylki(h, fin):
            pass
        for js in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', h, re.I):
            sobrano_js.add(urllib.parse.urljoin(fin, js))
        # адреса api прямо в html
        for a in re.findall(r'["\'](/[a-zA-Z0-9_\-/]*(?:api|ajax|json|data|reestr)[a-zA-Z0-9_\-/]*)["\']', h):
            out['api'].append({'iz': u, 'put': a})
    print('js-файлов найдено: %d' % len(sobrano_js))
    for js in sorted(sobrano_js)[:25]:
        k, b, _, e = dostat(js, timeout=60)
        s = tekst(b) if b else ''
        # Первая версия искала только пути, НАЧИНАЮЩИЕСЯ со слэша, и дала 0 путей на 163 КБ
        # client.js — то есть прибор молчал. Ноль путей на большом файле это повод проверить
        # прибор, а не вывод «их нет». Теперь ищем и относительные адреса, и .php/.asp/.json,
        # и значения url: в вызовах ajax.
        puti = sorted(set(
            re.findall(r'["\'](/[a-zA-Z0-9_\-/\.]*(?:api|ajax|json|reestr|tpr|data|list|search)[a-zA-Z0-9_\-/\.]*)["\']', s)
            + re.findall(r'["\']([a-zA-Z0-9_\-/\.]+\.(?:php|asp|aspx|json|ashx|do))["\']', s)
            + re.findall(r'url\s*:\s*["\']([^"\']{2,120})["\']', s)
            + re.findall(r'\$\.(?:get|post|ajax|getJSON)\s*\(\s*["\']([^"\']{2,120})["\']', s)))
        out['skripty'].append({'url': js, 'kod': k, 'bajt': len(b), 'putey': len(puti),
                               'puti': puti[:40], 'oshibka': e})
        print('  js %-70s kod=%s bajt=%d putey=%d' % (js[-70:], k, len(b), len(puti)))
        for pp in puti[:40]:
            out['api'].append({'iz': js, 'put': pp})
    # пробуем найденные пути
    probovali = set()
    for a in out['api']:
        u = urllib.parse.urljoin(baza, a['put'])
        if u in probovali:
            continue
        probovali.add(u)
        k, b, _, e = dostat(u, timeout=30, maks=200000)
        a['kod'] = k
        a['bajt'] = len(b)
        a['nachalo'] = tekst(b)[:200].replace('\n', ' ') if b else ''
        print('  api %-60s kod=%s bajt=%d %s' % (a['put'][:60], k, len(b), a['nachalo'][:80]))
    with open(put_sost('drsk'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('ИТОГ drsk: страниц %d, js %d, путей-кандидатов %d -> %s'
          % (len(out['stranicy']), len(out['skripty']), len(probovali), put_sost('drsk')))


def cmd_drsk_reestr(argv):
    """Скачать и разобрать сам файл «Реестр заявок на подключение ...» с портала ДРСК.

    Это единственный найденный на 17.09.2026 файл, который НАЗЫВАЕТСЯ реестром заявок, а не
    сводкой количеств. Разбираем его полностью: строки, ВСЕ имена колонок, ИНН, наименования.
    Сырой файл кладём на дроп, чтобы его можно было перепроверить с другого слоя."""
    baza = 'https://utp.drsk.ru'
    najdeno = {}
    for i in list(range(1, 16)) + ['']:
        u = baza + '/tpr_reestr' + ('/%d' % i if i != '' else '')
        k, d, fin, e = dostat(u, timeout=40, maks=4000000)
        if k != 200:
            continue
        h = tekst(d)
        for su, st in ssylki(h, fin):
            if FAJL.search(su) and re.search(r'реестр', st + ' ' + urllib.parse.unquote(su), re.I):
                najdeno.setdefault(su, st)
    print('файлов-реестров найдено: %d' % len(najdeno))
    itog = []
    for su, st in najdeno.items():
        k, b, _, e = dostat(su, timeout=180)
        print('== %s\n   kod=%s байт=%d %s' % (urllib.parse.unquote(su)[-110:], k, len(b), e))
        if k != 200 or not b:
            itog.append({'url': su, 'kod': k, 'oshibka': e})
            continue
        imya = 'tpseti_drsk_' + re.sub(r'\W+', '_', urllib.parse.unquote(su).split('/')[-1])[:70] + '.xlsx'
        r = razbor_fajla(su, b)
        r['tekst'] = st
        r['na_drop'] = drop_polozhit(imya, b)
        itog.append(r)
        print('   тип=%s строк=%s ИНН-кандидатов=%s уник=%s ООО/АО=%s контроль_выдуманное=%s'
              % (r.get('tip'), r.get('strok'), r.get('inn_kandidatov'), r.get('inn_unikalnyh'),
                 r.get('ooo_vhozhdeniy'), r.get('kontrol_vydumannoe')))
        print('   на дроп: %s' % r['na_drop'])
        for g in (r.get('kolonki') or [])[:4]:
            print('   лист %r строк=%d ВСЕ КОЛОНКИ:' % (g['list'], g['strok']))
            for c in g['kolonki']:
                print('      - %s' % c[:130])
        print('   примеры ИНН: %s' % (r.get('inn_primery'),))
    with open(put_sost('drsk_reestr'), 'w', encoding='utf-8') as f:
        json.dump(itog, f, ensure_ascii=False, indent=1)
    print('ИТОГ drsk_reestr: файлов %d -> %s' % (len(itog), put_sost('drsk_reestr')))


# --- СиПР: обосновывающие материалы Системного оператора -----------------------------
# ГЛАВНАЯ НАХОДКА. Сетевые организации по ПП 24 раскрывают заявки БЕЗ имён (см. отчёт).
# Но те же самые заявки, поимённо, публикует СО ЕЭС в обосновывающих материалах к СиПР —
# по файлу на субъект РФ, с таблицей, у которой колонки дословно:
#   «Наименование заявителя | Ранее присоединенная мощность, МВт |
#    Увеличение/ввод новой мощности, МВт | Напряжение, кВ | Год ввода | Центр питания»
# То есть предприятие + сколько мощности просит + к какому году. Это и есть ранний след.
SIPR_SPISOK = 'https://www.so-ups.ru/future-planning/sipr-ees/'
ZAYAVITEL_ZAG = re.compile(r'Наименовани[ея]\s+заявител', re.I)
YURLICO = re.compile(
    r'(?:ООО|ОАО|ПАО|ЗАО|АО|ФГУП|ГУП|МУП|НАО|АНО|ФКП|ФГБУ|ИП)\s*[«"]\s*([^»"\n]{2,80})\s*[»"]')
# Стоп-лист: сама сетевая организация и Системный оператор печатаются в каждой строке —
# тот самый случай, когда «юрлиц 3396» оказались одной компанией. Их считаем отдельно.
SVOI_IMENA = re.compile(r'россети|мрск|со\s*ЕЭС|системный оператор|фск|энерго$|электросет', re.I)


def cmd_sipr(argv):
    """Замерить, сколько ПОИМЕННЫХ заявителей на ТП лежит в обосновывающих материалах СиПР."""
    predel = int(next((a.split('=')[1] for a in argv if a.startswith('--regionov=')), '86'))
    k, d, fin, e = dostat(SIPR_SPISOK, timeout=60, maks=4000000)
    print('страница СиПР: kod=%s байт=%d %s' % (k, len(d), e))
    h = tekst(d)
    # ССЫЛКИ ЗДЕСЬ ОТНОСИТЕЛЬНЫЕ БЕЗ ВЕДУЩЕГО СЛЭША: href="fileadmin/files/...pdf" на
    # странице /future-planning/sipr-ees/. Обычный urljoin приклеивает их к каталогу
    # страницы и даёт /future-planning/sipr-ees/fileadmin/... — то есть 404 на ВСЕХ 86
    # регионах подряд. Ровный ряд 404 это отказ прибора, а не отсутствие файлов, поэтому
    # такие адреса склеиваем ещё и с корнем сайта и берём тот вариант, который ответил.
    koren = '%s://%s/' % (urllib.parse.urlsplit(fin).scheme, urllib.parse.urlsplit(fin).netloc)
    pdfy = []
    for syr, podpis in SSYLKA.findall(h):
        if not syr.lower().endswith('.pdf') or 'public_discussion' not in syr:
            continue
        st = ochistit(podpis)
        varianty = [urllib.parse.urljoin(fin, syr)]
        if not syr.startswith(('/', 'http')):
            varianty.append(urllib.parse.urljoin(koren, syr))
        pdfy.append((varianty, st))
    # проверяем, какой вариант отвечает, на первом же файле
    if pdfy:
        rab = None
        for v in pdfy[0][0]:
            kk, _, _, _ = dostat(v, timeout=60, maks=2000)
            print('  проба варианта адреса: %s -> %s' % (v[:110], kk))
            if kk == 200:
                rab = pdfy[0][0].index(v)
                break
        if rab is None:
            print('НИ ОДИН вариант адреса не ответил 200 — дальше мерить нечего')
            return
        pdfy = [(v[rab] if len(v) > rab else v[0], st) for v, st in pdfy]
    # берём самый свежий каталог периода
    katalogi = {}
    for su, st in pdfy:
        katalogi.setdefault(su.rsplit('/', 2)[-2], []).append((su, st))
    # Самый свежий период — по числу в имени каталога ('2025-30_final'), а не по алфавиту:
    # алфавит поставил последним каталог 'final' (период 2023-2028), то есть замер молча
    # уехал бы на два года назад.
    svezhiy = sorted(katalogi, key=lambda x: (re.sub(r'\D', '', x) or '0'))[-1]
    spisok = katalogi[svezhiy]
    print('каталогов периодов: %s; выбран %r, в нём pdf: %d'
          % (sorted(katalogi), svezhiy, len(spisok)))
    itog = []
    vse_imena = set()
    for su, st in spisok[:predel]:
        k, b, _, e = dostat(su, timeout=240)
        if k != 200 or not b:
            itog.append({'region': st, 'url': su, 'kod': k, 'oshibka': e})
            print('  %-40s kod=%s %s' % (st[:40], k, e[:60]))
            continue
        t = tekst_pdf(b) or ''
        zag = len(ZAYAVITEL_ZAG.findall(t))
        imena = set()
        for m in ZAYAVITEL_ZAG.finditer(t):
            for nm in YURLICO.findall(t[m.start():m.start() + 8000]):
                nm = re.sub(r'\s+', ' ', nm).strip()
                if nm and not SVOI_IMENA.search(nm):
                    imena.add(nm)
        vse = {re.sub(r'\s+', ' ', x).strip() for x in YURLICO.findall(t)}
        zap = {'region': st, 'url': su, 'kod': k, 'bajt': len(b), 'znakov': len(t),
               'zagolovkov_zayavitel': zag, 'imen_u_zagolovka': len(imena),
               'imen_vsego_v_fajle': len(vse), 'primery': sorted(imena)[:10],
               'kontrol_vydumannoe': t.lower().count(VYDUMANNOE)}
        itog.append(zap)
        vse_imena |= imena
        print('  %-40s заголовков «Наименование заявителя»=%-3d имён рядом=%-4d всего юрлиц=%-4d контроль=%d'
              % (st[:40], zag, len(imena), len(vse), zap['kontrol_vydumannoe']))
        sys.stdout.flush()
        with open(put_sost('sipr'), 'w', encoding='utf-8') as f:
            json.dump({'regiony': itog, 'imena': sorted(vse_imena)}, f,
                      ensure_ascii=False, indent=1)
    s_formoy = [z for z in itog if z.get('zagolovkov_zayavitel')]
    print('ИТОГ sipr: регионов разобрано %d; с таблицей «Наименование заявителя» %d;'
          ' УНИКАЛЬНЫХ заявителей всего %d; контроль (выдуманное слово, должно быть 0): %d'
          % (len(itog), len(s_formoy), len(vse_imena),
             sum(z.get('kontrol_vydumannoe') or 0 for z in itog)))
    print('файл: %s' % put_sost('sipr'))


def cmd_lk(argv):
    """Порталы ТП и личные кабинеты: есть ли ПУБЛИЧНАЯ проверка статуса заявки без входа."""
    out = []
    poisk = re.compile(r'проверить\s+статус|статус\s+заяв|узнать\s+статус|номер\s+заяв'
                       r'|проверка\s+заяв|отслеж', re.I)
    for kod_org, imya, base, puti in PORTALY:
        zap = {'org': kod_org, 'imya': imya, 'base': base, 'kontrol404': kontrol_404(base),
               'stranicy': []}
        for p in puti:
            u = base + p
            k, d, fin, e = dostat(u, timeout=40, maks=3000000)
            h = tekst(d)
            st = {'url': u, 'kod': k, 'bajt': len(d), 'oshibka': e,
                  'est_publichnyy_poisk_statusa': bool(poisk.search(h)),
                  'formy': len(re.findall(r'<form\b', h, re.I)),
                  'polya_input': sorted(set(re.findall(r'<input[^>]+name=["\']([^"\']+)', h, re.I)))[:25],
                  'upominaniya': sorted(set(x.strip()[:60] for x in poisk.findall(h)))[:10]}
            zap['stranicy'].append(st)
            print('%-14s %-45s kod=%-4s форм=%s статус-поиск=%s'
                  % (kod_org, u[:45], k, st['formy'], st['est_publichnyy_poisk_statusa']))
        out.append(zap)
    with open(put_sost('lk'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('ИТОГ lk: порталов %d -> %s' % (len(out), put_sost('lk')))


def cmd_kontrol(argv):
    """ПОЛОЖИТЕЛЬНЫЙ контроль определителя колонок: сработает ли он там, где заявитель ЕСТЬ.

    Зачем. «Ноль ИНН» на два десятка сайтов неотличим от сломанного определителя, пока не
    показано, что на заведомо ИМЕНОВАННОМ файле тот же самый код отвечает «да». Поэтому
    прогоняем razbor_fajla() по входам с известным ответом:
      1. синтетический xlsx, который мы собрали сами: колонки «ИНН», «Наименование
         заявителя», «Адрес», «Мощность, кВт», «Дата» и три строки с настоящими ИНН.
         Ожидание: все пять признаков True, ИНН-кандидатов 3.
      2. наша выгрузка ЕГРЗ (KOMPRESSORNYE-STANCII-EGRZ.xlsx): там ИНН застройщика стоит
         у подавляющего большинства записей. Ожидание: imya_inn=True и сотни ИНН.
      3. синтетический ОТРИЦАТЕЛЬНЫЙ вход: тот же файл без имён и ИНН, только номера и
         мощности. Ожидание: все признаки False, ИНН 0 — иначе определитель «находит»
         заявителя везде, и его «да» ничего не стоит.
    Путь к ЕГРЗ можно передать аргументом; по умолчанию ищем в KATALOG_SOST."""
    def sobrat_xlsx(zagolovki, stroki):
        """Собрать минимальный xlsx в памяти (без сторонних библиотек)."""
        def ryad(nomer, yach):
            c = ''.join('<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>'
                        % (chr(65 + j), nomer, str(v).replace('&', '&amp;').replace('<', '&lt;'))
                        for j, v in enumerate(yach))
            return '<row r="%d">%s</row>' % (nomer, c)
        telo = ryad(1, zagolovki) + ''.join(ryad(i + 2, r) for i, r in enumerate(stroki))
        buf = io.BytesIO()
        z = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',
                   '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="проба" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',
                   '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<sheetData>%s</sheetData></worksheet>' % telo)
        z.close()
        return buf.getvalue()

    itog = []

    def proverit(imya, b, zhdem_zayavitel, zhdem_inn, zhdem_inn_ne_menee):
        r = razbor_fajla(imya, b)
        vyvod = {'proba': imya, 'strok': r.get('strok'), 'tip': r.get('tip'),
                 'imya_zayavitel': r.get('imya_zayavitel'), 'imya_inn': r.get('imya_inn'),
                 'imya_adres': r.get('imya_adres'), 'imya_moschnost': r.get('imya_moschnost'),
                 'imya_data': r.get('imya_data'), 'inn_kandidatov': r.get('inn_kandidatov'),
                 'kontrol_vydumannoe': r.get('kontrol_vydumannoe')}
        sошlos = (vyvod['imya_zayavitel'] is zhdem_zayavitel
                  and vyvod['imya_inn'] is zhdem_inn
                  and (vyvod['inn_kandidatov'] or 0) >= zhdem_inn_ne_menee
                  and vyvod['kontrol_vydumannoe'] == 0)
        vyvod['ozhidalos'] = {'заявитель': zhdem_zayavitel, 'ИНН': zhdem_inn,
                              'ИНН не менее': zhdem_inn_ne_menee}
        vyvod['sovpalo'] = sошlos
        itog.append(vyvod)
        print('%-46s заявитель=%-5s ИНН=%-5s адрес=%-5s мощн=%-5s дата=%-5s ИНН-канд=%-5s -> %s'
              % (imya[:46], vyvod['imya_zayavitel'], vyvod['imya_inn'], vyvod['imya_adres'],
                 vyvod['imya_moschnost'], vyvod['imya_data'], vyvod['inn_kandidatov'],
                 'СОШЛОСЬ' if sошlos else 'НЕ СОШЛОСЬ'))
        return sошlos

    # 1. положительный синтетический
    polozh = sobrat_xlsx(
        ['№ п/п', 'ИНН', 'Наименование заявителя', 'Адрес объекта', 'Мощность, кВт', 'Дата заявки'],
        [['1', '7707083893', 'ООО «Пробное предприятие»', 'г. Москва, ул. Пробная, 1', '250', '01.02.2026'],
         ['2', '7736050003', 'АО «Второе пробное»', 'г. Тверь, пр. Пробный, 2', '1200', '03.02.2026'],
         ['3', '5036065113', 'ПАО «Третье пробное»', 'г. Уфа, ш. Пробное, 3', '4000', '05.02.2026']])
    proverit('СИНТЕТИКА положительная (заявитель и ИНН есть)', polozh, True, True, 3)
    # 2. отрицательный синтетический — ровно та форма, что у сетевых организаций
    otric = sobrat_xlsx(
        ['№ п/п', 'Номер договора', 'Запрашиваемая мощность, кВт', 'Стоимость без НДС'],
        [['1', '11103-21-00614368-1', '250', '834.3420000000001'],
         ['2', '10101-21-00616662-1', '1200', '427.03533333333343']])
    proverit('СИНТЕТИКА отрицательная (ни имени, ни ИНН)', otric, False, False, 0)
    # 3. наша выгрузка ЕГРЗ: заявитель там заведомо назван
    put_egrz = next((a for a in argv if a.lower().endswith(('.xlsx', '.xls'))), None)
    if not put_egrz:
        for kandidat in ('KOMPRESSORNYE-STANCII-EGRZ.xlsx',):
            p = os.path.join(KATALOG_SOST, kandidat)
            if os.path.exists(p):
                put_egrz = p
                break
    if put_egrz and os.path.exists(put_egrz):
        proverit('ЕГРЗ %s' % os.path.basename(put_egrz), open(put_egrz, 'rb').read(), True, True, 100)
    else:
        print('ЕГРЗ-файл не найден — положительный контроль на реальных данных НЕ проведён')
        itog.append({'proba': 'ЕГРЗ', 'sovpalo': None, 'zamechanie': 'файл не найден'})
    # 4. разбор ИМЁН КОЛОНОК поштучно — на реальных заголовках, встреченных в этом замере.
    # Здесь важны обе ошибки: пропустить настоящего контрагента и принять за контрагента
    # саму сетевую организацию или показатель качества.
    obrazcy = [
        ('Наименование заявителя', True),
        ('Наименование потребителя', True),
        ('Застройщик', True),
        ('Наименование юридического лица (индивидуального предпринимателя', True),
        ('Лицо, намеревающееся осуществить перераспределение максимальной мощности', True),
        ('Наименование филиала', False),
        ('Наименование Общества', False),
        ('Наименование центра питания', False),
        ('Точка присоединения (Центр питания)', False),
        ('Категория присоединения потребителей услуг по передаче электрической энергии'
         ' в разбивке по мощности', False),
        ('Установленная мощность', False),
        ('Запрашиваемая максимальная мощность (без учета ранее присоединенной), кВт', False),
    ]
    rashod = []
    for imya_k, zhdem in obrazcy:
        got = bool(IMENA_ZAYAV.search(imya_k)) and not bool(NE_KONTRAGENT.search(imya_k))
        if got != zhdem:
            rashod.append((imya_k, zhdem, got))
    print('разбор имён колонок: образцов %d, расхождений %d' % (len(obrazcy), len(rashod)))
    for imya_k, zhdem, got in rashod:
        print('   СБОЙ: ожидали %s, получили %s — %s' % (zhdem, got, imya_k[:90]))
    itog.append({'proba': 'имена колонок', 'obrazcov': len(obrazcy),
                 'rashozhdeniy': len(rashod), 'sovpalo': not rashod})
    with open(put_sost('kontrol'), 'w', encoding='utf-8') as f:
        json.dump(itog, f, ensure_ascii=False, indent=1)
    ne = [x for x in itog if x.get('sovpalo') is False]
    print('ИТОГ kontrol: проб %d, не сошлось %d. %s'
          % (len(itog), len(ne),
             'Определитель рабочий: на именованных файлах он отвечает ДА, на безымянных НЕТ.'
             if not ne else 'ОПРЕДЕЛИТЕЛЬ НЕИСПРАВЕН — числам этого прогона верить нельзя.'))


def cmd_svod(argv):
    """Собрать итоговую таблицу «организация → форма → строк → есть ли заявитель».

    Читает состояния ОБОИХ слоёв (в песочнице лежат файлы _pesochnica, снятые с сервера —
    _server), потому что ни один слой не видит всех организаций: ДРСК отвечает только
    серверу, а Россети Кубань в тот день отвечала только песочнице."""
    imena = {k: n for k, n, _, _ in ORGANIZACII}
    stroki = []
    for sloy in ('pesochnica', 'server'):
        p = os.path.join(KATALOG_SOST, 'tp_seti_fajly_%s.json' % sloy)
        if not os.path.exists(p):
            continue
        for kod_org, spisok in json.load(open(p, encoding='utf-8')).items():
            for r in spisok:
                if r.get('kod') != 200:
                    stroki.append({'org': imena.get(kod_org, kod_org), 'sloy': sloy,
                                   'forma': r.get('tekst', '')[:120], 'kod': r.get('kod'),
                                   'strok': None, 'zayavitel': 'файл не отдан'})
                    continue
                kol = ' | '.join(c for g in (r.get('kolonki') or []) for c in g.get('kolonki', []))
                stroki.append({
                    'org': imena.get(kod_org, kod_org), 'sloy': sloy,
                    'forma': r.get('tekst', '')[:120], 'tip': r.get('tip'),
                    'strok': r.get('strok'), 'inn_kand': r.get('inn_kandidatov'),
                    'imya_zayavitel': r.get('imya_zayavitel'),
                    'imya_inn': r.get('imya_inn'), 'imya_adres': r.get('imya_adres'),
                    'imya_moschnost': r.get('imya_moschnost'), 'imya_data': r.get('imya_data'),
                    'kontrol': r.get('kontrol_vydumannoe'),
                    'kolonki': kol[:600], 'url': r.get('url')})
    p = os.path.join(KATALOG_SOST, 'tp_seti_svod.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(stroki, f, ensure_ascii=False, indent=1)
    print('строк свода: %d -> %s' % (len(stroki), p))
    s_zayav = [s for s in stroki if s.get('imya_zayavitel')]
    s_inn = [s for s in stroki if s.get('imya_inn')]
    plohoy = [s for s in stroki if s.get('kontrol') not in (0, None)]
    print('форм всего %d; с именем заявителя в колонках %d; с ИНН в колонках %d'
          % (len(stroki), len(s_zayav), len(s_inn)))
    print('КОНТРОЛЬ: форм, где выдуманное слово нашлось (должно быть 0): %d' % len(plohoy))
    print('--- ВСЕ находки (колонка заявителя или ИНН) ---')
    for s in s_zayav + [x for x in s_inn if x not in s_zayav]:
        print('%-26s %-70s строк=%-7s ИНН-канд=%s' % (s['org'][:26], s['forma'][:70],
                                                      s.get('strok'), s.get('inn_kand')))
        print('    колонки: %s' % (s.get('kolonki') or '')[:400])
    ne_otdano = [s for s in stroki if s.get('zayavitel') == 'файл не отдан']
    # Итог печатаем ПОСЛЕДНИМ: вывод серверного задания возвращается ХВОСТОМ, и headline,
    # напечатанный до длинного списка, до нас просто не доезжает.
    print('--- ИТОГ svod (слой %s) ---' % SLOY)
    print('форм разобрано: %d' % len(stroki))
    print('с колонкой имени заявителя: %d' % len(s_zayav))
    print('с колонкой ИНН: %d' % len(s_inn))
    print('файлов, которые хост не отдал: %d' % len(ne_otdano))
    print('КОНТРОЛЬ, форм с выдуманным словом (должно быть 0): %d' % len(plohoy))


KOMANDY = {'dostup': cmd_dostup, 'obhod': cmd_obhod, 'fajly': cmd_fajly,
           'drsk': cmd_drsk, 'drsk_reestr': cmd_drsk_reestr, 'lk': cmd_lk,
           'sipr': cmd_sipr, 'kontrol': cmd_kontrol, 'svod': cmd_svod}

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in KOMANDY:
        print(__doc__)
        sys.exit(2)
    t0 = time.time()
    KOMANDY[sys.argv[1]](sys.argv[2:])
    print('(%s, %.0f c)' % (SLOY, time.time() - t0))
