# -*- coding: utf-8 -*-
"""Карта компании: одна оболочка над готовыми модулями проекта — по ОДНОМУ ИНН.

ЗАЧЕМ ОНА ЕСТЬ. Десятки скриптов проекта написаны под пачки: на вход файл со списком, на
выход общий CSV. Владельцу нужно наоборот — вбить одну компанию и получить всё, что о ней
известно и добывается. Переписывать сорок скриптов нельзя (они рабочие и обкатанные),
поэтому здесь оболочка: она ВЫЗЫВАЕТ их функции, ничего в них не правя.

ГЛАВНОЕ УСТРОЙСТВО — КРУГИ, А НЕ ОДИН ПРОХОД. Указание владельца: «недоступный модуль может
стать доступным по информации от других модулей». Значит доступность модуля — не свойство
среды, а функция от того, что мы уже знаем. Реальные цепочки в наших данных:

    ЕГРЮЛ/реестр ЭПБ дал НАЗВАНИЕ  ->  открылись Тендер.Про, новости, патенты
    корпус или ЕГРЮЛ дал САЙТ      ->  открылся обход сайта и справочник подразделений
    любой модуль дал ФИО + домен   ->  открылся генератор корпоративной почты

Поэтому запуск идёт кругами до неподвижной точки: выполнить всё, чьи входы уже есть,
собрать новые факты, пересчитать доступность, повторить. Останов — когда круг не добавил
ни одного нового факта (тогда ожидающие модули не откроются никогда) или кончились модули.
Один модуль на одну компанию запускается РОВНО ОДИН РАЗ за прогон — иначе круги не сойдутся.

ПОЧЕМУ ПРИЧИНА НЕДОСТУПНОСТИ РАЗДЕЛЕНА НА ТРИ ВИДА. Если писать просто «пропущен», отчёт
врёт: «нет ключа XMLRIVER» и «ждёт название, его даст ЕГРЮЛ» — это разные вещи, первое
чинится владельцем, второе чинится следующим кругом. Виды:
    нет_среды   — не будет доступен в этом прогоне вообще (нет ключа, нет сервера);
    ждёт_факта  — назван КАКОЙ факт нужен и КТО его даёт;
    открылся    — назван круг и модуль с фактом, который его открыл.

ПРОВЕНАНС НАКАПЛИВАЕТСЯ (правило владельца). Один и тот же факт из двух источников — это
ОДНА запись с двумя источниками и числом 2, а не две записи и не последний победивший.
Ключ склейки: раздел + что + значение + человек. Ничего не выбрасывается: неличный номер
это путь к человеку через коммутатор, поэтому вид контакта пишется явно, а не отсеивается.

ЗАПУСК:
    python3 karta_kompanii.py --inn 2124009521
    python3 karta_kompanii.py --spisok inns.txt
    python3 karta_kompanii.py --inn 2124009521 --tolko korpus,egrul,epb
    python3 karta_kompanii.py --spisok-moduley
    python3 karta_kompanii.py --inn 2124009521 --kuda /home/user/work/karta --krugov 5

ВЫХОД: на каждую компанию karta-<инн>.json (всё, включая порядок кругов и причины
пропусков) и karta-<инн>.csv (плоская таблица фактов с источниками и ссылками).
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SEO = '/home/user/avto/seo-texts'
RAB = '/home/user/work'
for p in (SEO, RAB, os.path.join(SEO, 'server')):
    if p not in sys.path:
        sys.path.insert(0, p)

csv.field_size_limit(10 ** 7)

# Ключницы владельца. Читаем, но НЕ правим: run_on_server сам умеет добрать JOB_SECRET с
# дропа, однако локальный файл быстрее и не тратит запрос.
KLYUCHNICY = (os.path.join(RAB, 'sec', 'runner-secrets.env'),
              os.path.join(RAB, 'sec', 'rs.env'),
              os.path.join(SEO, 'server', 'runner-secrets.env'))

SVOBODNAYA_POCHTA = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru',
                     'inbox.ru', 'rambler.ru', 'mail.com', 'internet.ru', 'outlook.com',
                     'icloud.com', 'yahoo.com'}

RX_POCHTA = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
RX_DOMEN = re.compile(r'^(?:https?://)?(?:www\.)?([A-Za-z0-9.-]+\.[A-Za-z]{2,})')


def klyuchi_iz_klyuchnicy():
    """Подставить в окружение недостающие ключи из ключниц раннера.

    Зачем не «просто env»: в песочнице заданы DROP_* и PROVIDER_*, а DADATA_TOKEN и
    JOB_SECRET лежат только в файле. Без этого два рабочих модуля выглядели бы
    «недоступными насовсем», хотя ключ есть — а это ровно тот врущий отчёт, против
    которого всё и строится.
    """
    nuzhno = ('DADATA_TOKEN', 'JOB_SECRET', 'XMLRIVER_USER', 'XMLRIVER_KEY',
              'PROVIDER_API_KEY', 'PROVIDER_BASE_URL', 'DROP_URL', 'DROP_TOKEN')
    for put in KLYUCHNICY:
        if not os.path.exists(put):
            continue
        for stroka in open(put, encoding='utf-8', errors='replace'):
            stroka = stroka.strip()
            if not stroka or stroka.startswith('#') or '=' not in stroka:
                continue
            k, v = stroka.split('=', 1)
            k, v = k.strip(), v.strip().strip('"').strip()
            if k in nuzhno and v and not os.environ.get(k):
                os.environ[k] = v


klyuchi_iz_klyuchnicy()


# ═════════════════════════════════════════════════════════════════ факты о компании
# Факт — это не «данные», а КЛЮЧ, который открывает следующий модуль. Список маленький
# нарочно: чем он длиннее, тем труднее объяснить владельцу, почему модуль ждёт.
FAKTY_OPIS = {
    'inn': 'ИНН — дан на входе',
    'nazvanie': 'название организации (по нему ищут в выдаче, на площадках, в патентах)',
    'sayt': 'сайт компании (по нему идёт обход и справочник подразделений)',
    'domen': 'домен почты (по нему достраиваются корпоративные адреса)',
    'fio': 'ФИО хотя бы одного человека (по нему идёт обратный ход и подбор почты)',
    'id_zakupki': 'идентификатор закупки или тендера (по нему тянутся вложения)',
}


# Насколько модулю можно верить как ИСТОЧНИКУ ЗНАЧЕНИЯ факта. Это не «качество данных»
# вообще, а ответ на узкий вопрос: если название пришло из четырёх мест, какое подставлять
# в поисковый запрос. Реестр ЕГРЮЛ тут выше наших сводов не потому, что своды плохи, а
# потому что в них имя пережило десяток перекладываний между CSV и местами обрезано.
PRIORITET_MODULEY = {'egrul': 6, 'epb': 5, 'snimok_paneli': 4, 'baza_servera': 3,
                     'tenderpro': 2, 'korpus': 1}


class Nabor:
    """Всё, что известно о компании: факты, записи с провенансом и журнал кругов."""

    def __init__(self, inn):
        self.inn = inn
        self.fakty = {'inn': {inn}}
        # кто и на каком круге впервые дал факт — это и есть «что открыло модуль»
        self.otkuda_fakt = {'inn': ('вход', 0)}
        self.luchshiy = {'inn': (99, inn)}
        self.zapisi = {}
        self.zhurnal = []

    # ---- факты -------------------------------------------------------------------
    def dat_fakt(self, imya, znachenie, modul, krug):
        """Записать факт. Возвращает True, если факт ПОЯВИЛСЯ впервые (это и двигает круги)."""
        znachenie = _chistoe_znachenie(imya, znachenie)
        if not znachenie or imya not in FAKTY_OPIS:
            return False
        byl = imya in self.fakty
        self.fakty.setdefault(imya, set())
        novoe = znachenie not in self.fakty[imya]
        self.fakty[imya].add(znachenie)
        ves = PRIORITET_MODULEY.get(modul, 0)
        if ves > self.luchshiy.get(imya, (-1, ''))[0]:
            self.luchshiy[imya] = (ves, znachenie)
        if not byl:
            self.otkuda_fakt[imya] = (modul, krug)
        return (not byl) and novoe

    def est(self, imya):
        return bool(self.fakty.get(imya))

    def odin(self, imya):
        """Одно значение факта для запроса: от самого доверенного модуля, при равенстве —
        самое короткое (короткое имя в выдаче работает лучше длинного с формой и кавычками)."""
        if imya in self.luchshiy:
            return self.luchshiy[imya][1]
        v = sorted(self.fakty.get(imya) or [], key=lambda s: (len(s), s))
        return v[0] if v else ''

    def znachenie(self, razdel, chto):
        """Первое значение уже записанного факта (регион, адрес и т. п.) — для запросов."""
        for z in self.zapisi.values():
            if z['razdel'] == razdel and z['chto'] == chto:
                return z['znachenie']
        return ''

    # ---- записи ------------------------------------------------------------------
    def dobavit(self, razdel, chto, znachenie, istochnik, ssylka='', vid='', chelovek='',
                dolzhnost='', modul='', krug=0, podrobno=''):
        """Записать факт с провенансом. Совпавшее НЕ перезаписывается — источники копятся."""
        znachenie = re.sub(r'\s+', ' ', str(znachenie or '')).strip()
        if not znachenie:
            return
        klyuch = (razdel, chto, znachenie.lower(), (chelovek or '').strip().lower())
        z = self.zapisi.get(klyuch)
        if z is None:
            z = {'razdel': razdel, 'chto': chto, 'znachenie': znachenie, 'vid': vid,
                 'chelovek': (chelovek or '').strip(), 'dolzhnost': (dolzhnost or '').strip(),
                 'istochniki': [], 'ssylki': [], 'moduli': [], 'krugi': [],
                 'podrobno': podrobno}
            self.zapisi[klyuch] = z
        for pole, v in (('istochniki', istochnik), ('ssylki', ssylka), ('moduli', modul)):
            v = (v or '').strip()
            if v and v not in z[pole]:
                z[pole].append(v)
        if krug and krug not in z['krugi']:
            z['krugi'].append(krug)
        # пустое поле дозаполняем, непустое не трогаем: первый источник имеет приоритет,
        # но расхождение всё равно видно по числу источников
        for pole, v in (('vid', vid), ('dolzhnost', dolzhnost), ('podrobno', podrobno)):
            if not z[pole] and v:
                z[pole] = v


# ═════════════════════════════════════════════════════════════ проверки среды
def sreda_dadata():
    if os.environ.get('DADATA_TOKEN'):
        return True, ''
    return False, 'нет DADATA_TOKEN (ни в окружении, ни в ключницах раннера)'


def sreda_xmlriver():
    if os.environ.get('XMLRIVER_USER') and os.environ.get('XMLRIVER_KEY'):
        return True, ''
    return False, ('нет XMLRIVER_USER/XMLRIVER_KEY — платная выдача владельца; ключи есть '
                   'только на сервере в службе, в ключнице раннера их нет')


def sreda_provajder():
    if os.environ.get('PROVIDER_API_KEY'):
        return True, ''
    return False, 'нет PROVIDER_API_KEY'


_SERVER_OTVET = None


def sreda_server():
    """Жив ли раннер на сервере владельца. Проверяется РАЗ за прогон: это сетевой вызов
    с ожиданием результата, гонять его на каждый модуль дорого."""
    global _SERVER_OTVET
    if _SERVER_OTVET is not None:
        return _SERVER_OTVET
    if not (os.environ.get('DROP_URL') and os.environ.get('DROP_TOKEN')):
        _SERVER_OTVET = (False, 'нет DROP_URL/DROP_TOKEN — до раннера не достучаться')
        return _SERVER_OTVET
    try:
        import run_on_server as R
        r = R.submit('ping', {'hi': 1}, poll=5, timeout=120)
        if r.get('ok'):
            _SERVER_OTVET = (True, '')
        else:
            _SERVER_OTVET = (False, f'раннер ответил не ok: {str(r)[:120]}')
    except Exception as e:  # noqa: BLE001
        _SERVER_OTVET = (False, f'раннер не ответил: {type(e).__name__}: {str(e)[:100]}')
    return _SERVER_OTVET


def sreda_korpus():
    if os.path.isdir(RAB):
        return True, ''
    return False, f'нет каталога выгрузок {RAB}'


PROVERKI_SREDY = {
    'dadata': sreda_dadata,
    'xmlriver': sreda_xmlriver,
    'provajder': sreda_provajder,
    'server': sreda_server,
    'korpus': sreda_korpus,
}


# ═════════════════════════════════════════════════════════════ общие мелочи
def _cifry_inn(s):
    return re.sub(r'\D', '', str(s or ''))


def _chistoe_znachenie(fakt, v):
    """Привести значение факта в годный вид ДО записи.

    Поставлено по двум пойманным на первом прогоне поломкам, и обе тихие:
    1. Название `ПАО "ХИМПРОМ"` после разбиения склеек теряло закрывающую кавычку и
       становилось `ПАО "ХИМПРОМ` — в отчёте это выглядит как опечатка, а на деле ушло бы
       в поисковый запрос. Плюс из выгрузок приходит `ПАО &quot;ХИМПРОМ&quot;`.
    2. Домен приходил как `.himprom.com` (лидирующая точка от разбора адреса почты). Такой
       домен молча ломает генератор корпоративных адресов: он выдаёт `i.ivanov@.himprom.com`.
    Оба случая — не «грязь», а именно тихая порча: ошибки не будет, будет неверный запрос.
    """
    import html as _h
    v = re.sub(r'\s+', ' ', _h.unescape(str(v or ''))).strip()
    if not v:
        return ''
    if fakt in ('sayt', 'domen'):
        v = v.lower().strip('.,;:/ ')
        v = re.sub(r'^(?:https?://)?(?:www\.)+', '', v)
        return v if re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', v) else ''
    if fakt == 'nazvanie':
        # непарная кавычка на конце — след обрезки; закрываем, а не выбрасываем строку
        if v.count('"') == 1 and v.endswith('"'):
            v = v[:-1]
        elif v.count('"') == 1:
            v += '"'
        return v.strip(' ,;')
    return v


def _domen_iz(s):
    m = RX_DOMEN.match((s or '').strip())
    return _chistoe_znachenie('domen', m.group(1)) if m else ''


def _razbit(v):
    """Разбить поле-склейку на значения. В корпусе они пишутся через « | », «;», «,»
    и иногда как JSON-список — все три вида встречаются в одних и тех же файлах."""
    v = str(v or '').strip()
    if not v:
        return []
    if v.startswith('[') and v.endswith(']'):
        try:
            return [str(x).strip() for x in json.loads(v) if str(x).strip()]
        except Exception:  # noqa: BLE001
            pass
    return [x.strip(' "\'[]') for x in re.split(r'\s*\|\s*|;|,', v) if x.strip(' "\'[]')]


def _ssylka_ok(s):
    s = (s or '').strip()
    return s if s.startswith('http') else ''


# ═════════════════════════════════════════════════════════════ МОДУЛЬ: локальный корпус
# Что из чего берётся. Колонки в выгрузках проекта названы по-разному от файла к файлу
# (fio/imya/chelovek/kto), поэтому карта колонок общая, а не своя на каждый файл: иначе
# при добавлении новой выгрузки её пришлось бы описывать заново.
KOL_TEL = ('kontakt', 'telefon', 'telefony', 'mobilnyy_10cifr', 'nomer_10cifr',
           'lichnyy_nomer', 'telefony_predpriyatiya', 'vse_nomera', 'nomera_predpriyatiya',
           'obzvon_telefony', 'telefon_predpriyatiya', 'mobilnyy')
KOL_MAIL = ('pochta', 'luchshaya_pochta', 'obzvon_pochta', 'pochty', 'email', 'pochta_lichnaya')
KOL_FIO = ('fio', 'imya', 'chelovek', 'rukovoditel', 'direktor')
KOL_DOL = ('dolzhnost', 'dolzhnost_rukovoditelya', 'rol', 'rol_kanon', 'podrazdelenie')
KOL_SAYT = ('sayt', 'sajt', 'obzvon_sayt')
KOL_SSYL = ('ssylka', 'ssylka_na_istochnik', 'ssylka_sostoyaniya', 'ssylka_na_cheloveka',
            'kartochka', 'novost_ssylka', 'istochnik_ssylka', 'ssylka_na_istochnik')
KOL_IST = ('istochniki', 'istochnik', 'istochnik_cheloveka', 'otkuda_rekvizity')
KOL_MASH = ('marki', 'marka', 'tip_mashiny', 'tipy_mashin', 'marki_mashin', 'marki_epb',
            'oborudovanie_iz_bazy', 'seriya')
KOL_NAZV = ('predpriyatie', 'zakazchik', 'ofic_nazvanie', 'nazvanie', 'name')
KOL_SOST = ('sostoyanie', 'est', 'pokupaet', 'planiruet', 'vyvod_ekspertizy', 'srok_sluzhby',
            'zakupka_predmet', 'chto_eto', 'sreda', 'status_egrul', 'okved', 'region',
            'adres', 'vyruchka_rub', 'proverok_nadzora_2025_2026', 'segment',
            'data_zakluchenia', 'data_zakupki', 'novost')

# Файлы корпуса: путь относительно /home/user/work и как называть источник в провенансе.
KORPUS_FAJLY = [
    ('SPISOK-OBZVONA-POLNYY.csv', 'свод обзвона (все сессии)'),
    ('zhurnal/SVOD-LICHNYE-NOMERA.csv', 'свод личных номеров'),
    ('zhurnal/CEL-centrobezhnye-tehniki-s-nomerom.csv', 'цель: центробежные + техник с номером'),
    ('zhurnal/SVOD-POLNYY-po-predpriyatiyam.csv', 'сводка по предприятию'),
    ('zhurnal/PLANIRUYUT-POKUPAT.csv', 'планируют покупать'),
    ('zhurnal/HARAKTERISTIKI-mashin-po-predpriyatiyam.csv', 'характеристики машин'),
    ('zhurnal/LICA-S-SAJTOV-SO-SSYLKAMI.csv', 'лица с сайтов'),
    ('zhurnal/ERKNM-25-INN.csv', 'ЕРКНМ: надзорные мероприятия'),
    ('zhurnal/HH-vakansiya-plus-mashina.csv', 'hh: вакансия + машина'),
    ('BAZA-CENTROBEZHNIKI-OBSHCHAYA-dop3.csv', 'общая база центробежников'),
    ('OBHOD-kontakty-3s.csv', 'обход сайтов (3-я сессия)'),
    ('OCHERED-centrobezhnye.csv', 'очередь центробежных'),
    ('BEZ-TEHLPR-1486-dadata.csv', 'реквизиты DaData по компаниям без техЛПР'),
    ('novye-dlya-obzvona.csv', 'новые для обзвона (реестр ЭПБ)'),
    ('lica-s-sajtov.csv', 'лица со страниц сайтов'),
    ('SVOD-tri-sostoyaniya.csv', 'свод трёх состояний (есть/покупает/планирует)'),
    ('OTSEV-tip-mashiny.csv', 'отсев по типу машины'),
]
BOLSHOY = 8 * 1024 * 1024   # с какого размера читаем построчно, а не разбором всего файла


def _stroki_po_inn(put, inn):
    """Строки файла по нашему ИНН. Возвращает (строки, пометка) или (None, причина).

    Почему два режима чтения. Файлы корпуса от 30 КБ до 47 МБ. Полный разбор 47 МБ ради
    одной компании — секунды на каждый прогон, а их будет много. Поэтому большие файлы
    фильтруются построчно по вхождению ИНН. У построчного режима есть известная слабость:
    поле в кавычках с переводом строки разорвётся. Такие строки НЕ выбрасываются молча,
    а считаются и попадают в отчёт — иначе это был бы тихий пропуск данных.
    """
    if not os.path.exists(put):
        return None, 'файла нет'
    razmer = os.path.getsize(put)
    if razmer <= BOLSHOY:
        with open(put, encoding='utf-8-sig', errors='replace', newline='') as f:
            probe = f.read(4000)
            razd = ';' if probe.count(';') >= probe.count(',') else ','
            f.seek(0)
            rows = [r for r in csv.DictReader(f, delimiter=razd)
                    if _cifry_inn(r.get('inn') or r.get('inn_zakazchika')) == inn]
        return rows, 'полный разбор'
    ne_razobrano = 0
    rows = []
    with open(put, encoding='utf-8-sig', errors='replace', newline='') as f:
        zag = f.readline()
        razd = ';' if zag.count(';') >= zag.count(',') else ','
        cols = next(csv.reader([zag], delimiter=razd))
        for s in f:
            if inn not in s:
                continue
            try:
                r = next(csv.reader([s], delimiter=razd))
            except Exception:  # noqa: BLE001
                ne_razobrano += 1
                continue
            if len(r) < 2:
                ne_razobrano += 1
                continue
            d = dict(zip(cols, r))
            if _cifry_inn(d.get('inn') or d.get('inn_zakazchika')) == inn:
                rows.append(d)
    return rows, f'построчно ({razmer // 1024 // 1024} МБ), не разобрано строк: {ne_razobrano}'


def mod_korpus(nabor, krug, log):
    """Всё, что проект уже добыл об этой компании, из локальных выгрузок.

    Это единственный модуль, который сам ничего не добывает — он ДОСТАЁТ. И он же чаще
    всего открывает круг: название, сайт и ФИО почти всегда уже лежат в свободе.
    """
    inn = nabor.inn
    itogo = 0
    for otn, imya_ist in KORPUS_FAJLY:
        put = os.path.join(RAB, otn)
        rows, pometka = _stroki_po_inn(put, inn)
        if rows is None:
            log(f'    {otn}: {pometka}')
            continue
        if not rows:
            continue
        log(f'    {otn}: строк {len(rows)} [{pometka}]')
        for r in rows:
            itogo += _zapisi_iz_stroki(nabor, r, imya_ist, otn, krug)
    return {'zapisey': itogo}


def _zapisi_iz_stroki(nabor, r, imya_ist, fajl, krug):
    """Разложить строку любой выгрузки на записи с провенансом.

    Провенанс берётся ИЗ СТРОКИ, если он там есть: в наших сводах колонка `istochniki`
    уже накопительная («tenderpro/разбор-2сессии | Тендер.Про»). Её надо разложить на
    отдельные источники, а не записать одной строкой — иначе подтверждённое дважды снова
    станет неотличимо от подтверждённого однажды.
    """
    n = 0
    ssylka = ''
    for k in KOL_SSYL:
        ssylka = ssylka or _ssylka_ok(r.get(k))
    ist_svoi = []
    for k in KOL_IST:
        ist_svoi.extend(_razbit(r.get(k)))
    istochniki = ist_svoi or [imya_ist]
    # файл-хранитель тоже источник: по нему видно, где строка лежит физически
    istochniki = list(dict.fromkeys(istochniki + [f'{imya_ist} [{fajl}]']))

    fio = ''
    for k in KOL_FIO:
        v = (r.get(k) or '').strip()
        if v and _fio_pohozhe(v):
            fio = v
            break
    dolzh = ''
    for k in KOL_DOL:
        v = (r.get(k) or '').strip()
        if v and not v.isdigit():
            dolzh = v
            break
    podskazka = ' '.join(str(r.get(k) or '') for k in ('vid', 'vid_nomera', 'tip', 'tip_kontakta'))

    def pishem(razdel, chto, znach, **kw):
        nonlocal n
        for ist in istochniki:
            nabor.dobavit(razdel, chto, znach, ist, ssylka=ssylka, modul='korpus',
                          krug=krug, **kw)
        n += 1

    for k in KOL_NAZV:
        # название НЕ разбивается на части: `_razbit` режет по запятой и точке с запятой,
        # а «ООО "Химпром, завод"» — одно имя. Берётся значение целиком.
        v = _chistoe_znachenie('nazvanie', r.get(k))
        if v:
            pishem('реквизиты', 'название', v)
            nabor.dat_fakt('nazvanie', v, 'korpus', krug)
    for k in KOL_SAYT:
        for v in _razbit(r.get(k)):
            d = _domen_iz(v)
            if d:
                pishem('реквизиты', 'сайт', d)
                nabor.dat_fakt('sayt', d, 'korpus', krug)
                nabor.dat_fakt('domen', d, 'korpus', krug)
    if fio:
        pishem('человек', 'ФИО', fio, chelovek=fio, dolzhnost=dolzh)
        nabor.dat_fakt('fio', fio, 'korpus', krug)
    for k in KOL_TEL:
        for v in _razbit(r.get(k)):
            nom = _nomer(v)
            if nom:
                pishem('контакт', 'телефон', nom, vid=_vid_nomera(nom, podskazka + ' ' + k),
                       chelovek=fio, dolzhnost=dolzh)
    for k in KOL_MAIL:
        for v in _razbit(r.get(k)):
            for m in RX_POCHTA.findall(v):
                pishem('контакт', 'почта', m.lower(), vid='почта', chelovek=fio,
                       dolzhnost=dolzh)
                d = m.split('@')[1].lower()
                if d not in SVOBODNAYA_POCHTA:
                    nabor.dat_fakt('domen', d, 'korpus', krug)
    for k in KOL_MASH:
        for v in _razbit(r.get(k)):
            if len(v) > 1:
                pishem('машина', k, v)
    for k in KOL_SOST:
        v = (r.get(k) or '').strip()
        if v and v not in ('0',):
            pishem('о компании', k, v[:400])
    return n


def _fio_pohozhe(s):
    """Похоже ли на ФИО. Заслон против должностей и обрывков в поле имени."""
    try:
        import svesti_vseh_lyudej as SV
        return SV.fio_ok(s)
    except Exception:  # noqa: BLE001
        return bool(re.match(r'^[А-ЯЁ][а-яё\-]+\s+[А-ЯЁ]', (s or '').strip()))


def _nomer(s):
    import svesti_vseh_lyudej as SV
    return SV.nomer(s)


def _vid_nomera(n, podskazka=''):
    import svesti_vseh_lyudej as SV
    return SV.vid_nomera(n, podskazka)


# ═════════════════════════════════════════════════════════════ МОДУЛЬ: ЕГРЮЛ (DaData)
def mod_egrul(nabor, krug, log):
    """Карточка ЕГРЮЛ по ИНН через справочник DaData.

    Модуль `dadata_inn.py` написан под пачку названий (файл -> CSV), но его рабочие
    функции `sprosit`/`razobrat` берут ОДНУ строку. Справочник ищет и по ИНН — то есть
    переделка не нужна вовсе, нужен только вызов не из main().
    """
    import dadata_inn as D
    D.TOK = D.token()
    otvet = D.sprosit(nabor.inn)
    sug = (otvet.get('suggestions') or [])
    if not sug:
        return {'zapisey': 0, 'pusto': 'справочник не знает такого ИНН'}
    razbor = D.razobrat(nabor.inn, otvet)
    d = (sug[0].get('data') or {})
    ist = 'ЕГРЮЛ через справочник DaData'
    ssylka = D.URL + '?query=' + nabor.inn
    n = 0

    def pishem(razdel, chto, znach, **kw):
        nonlocal n
        if znach:
            nabor.dobavit(razdel, chto, znach, ist, ssylka=ssylka, modul='egrul', krug=krug, **kw)
            n += 1

    imya = razbor.get('nazvanie_egrul') or ''
    polnoe = ((d.get('name') or {}).get('full_with_opf') or '')
    pishem('реквизиты', 'название', imya)
    pishem('реквизиты', 'название полное', polnoe)
    for v in (imya, polnoe):
        nabor.dat_fakt('nazvanie', v, 'egrul', krug)
    pishem('реквизиты', 'ОГРН', d.get('ogrn') or '')
    pishem('реквизиты', 'КПП', razbor.get('kpp') or '')
    pishem('реквизиты', 'ОКВЭД', razbor.get('okved') or '')
    pishem('реквизиты', 'статус в ЕГРЮЛ', razbor.get('status') or '')
    pishem('реквизиты', 'регион', razbor.get('region') or '')
    pishem('реквизиты', 'адрес', ((d.get('address') or {}).get('unrestricted_value') or ''))
    ruk = razbor.get('rukovoditel') or ''
    if ruk:
        # у холдингов управляющей организацией стоит ЮРЛИЦО — это не человек, и путать
        # их нельзя: по «ООО ГРУППА ОРГСИНТЕЗ» обратный ход по ФИО искал бы несуществующее
        if _fio_pohozhe(ruk):
            pishem('человек', 'руководитель по ЕГРЮЛ', ruk, chelovek=ruk,
                   dolzhnost=razbor.get('dolzhnost') or 'руководитель')
            nabor.dat_fakt('fio', ruk, 'egrul', krug)
        else:
            pishem('реквизиты', 'управляющая организация', ruk)
    pishem('о компании', 'кандидатов в справочнике', str(razbor.get('kandidatov') or ''))
    return {'zapisey': n}


# ═════════════════════════════════════════════════════════════ МОДУЛЬ: реестр ЭПБ
def mod_epb(nabor, krug, log):
    """Реестр заключений промбезопасности monitor-pb.ru по карточке владельца ОПО.

    Два входа, и оба нужны — это выяснилось замером, а не из чтения кода.

    `/customer/<инн>` — карточка владельца ОПО. Даёт НАЗВАНИЕ (второй, независимый от
    ЕГРЮЛ источник, открывает круг без токена DaData) и сводные счётчики, которых больше
    нигде нет: сколько заключений всего, сколько действует, сколько ИСТЕКАЕТ В 12 МЕСЯЦЕВ.
    Но список заключений на ней — только ПОСЛЕДНИЕ 10, и пагинации нет. У ПАО «Химпром»
    на карточке 10 строк против 5 724 в реестре, то есть 0,2%.

    Полный список берёт `mpb_po_inn.po_inn` (адрес `/conclusions?exploiter=<инн>&type=ТУ`,
    25 строк на страницу). `type=ТУ` — только технические устройства, то есть МАШИНЫ, без
    зданий, трубопроводов и документации.

    Срок ЭПБ — главный сигнал момента: у машины кончается экспертиза, значит её либо
    продлевают, либо меняют. В списке срока НЕТ (там вывод экспертизы), он добирается с
    карточек заключений и только по нашим машинам — `dobrat_sroki`.
    """
    import mpb_harvest as M
    url = f'{M.BASE}/customer/{nabor.inn}'
    try:
        page = M.get(url)
    except urllib.error.HTTPError as e:
        # 404 здесь — не сбой, а ответ: такого владельца ОПО в реестре нет. Различать это
        # с настоящей ошибкой обязательно, иначе «нет заключений» и «сайт лёг» сольются
        if e.code == 404:
            return {'zapisey': 0, 'pusto': 'в реестре ЭПБ нет карточки владельца ОПО '
                                           'по этому ИНН (ответ 404, а не сбой)'}
        raise
    tekst = M._text(page)
    ist = 'реестр заключений ЭПБ (monitor-pb.ru)'
    n = 0

    m = re.search(r'карточка владельца ОПО\s*(.+?)\s*ИНН\s*' + nabor.inn, tekst)
    if m and m.group(1).strip():
        imya = m.group(1).strip()
        nabor.dobavit('реквизиты', 'название', imya, ist, ssylka=url, modul='epb', krug=krug)
        nabor.dat_fakt('nazvanie', imya, 'epb', krug)
        n += 1
    for chto, rx in (('заключений в реестре', r'([\d  ]+)\s*заключений в реестре'),
                     ('срок действует', r'([\d  ]+)\s*действует'),
                     ('срок истекает в 12 мес', r'([\d  ]+)\s*истекают в 12 мес'),
                     ('срок истёк', r'([\d  ]+)\s*срок истёк')):
        mm = re.search(rx, tekst)
        if mm:
            nabor.dobavit('экспертиза ЭПБ', chto, re.sub(r'\D', '', mm.group(1)), ist,
                          ssylka=url, modul='epb', krug=krug)
            n += 1
    # ПОЛНЫЙ список машин — не с карточки, а из реестра. Карточка отдаёт последние 10.
    import mpb_po_inn as P
    stroki, err = P.po_inn(nabor.inn, tolko_tu=True)
    if err:
        log(f'    СБОЙ выкачки реестра: {err}')
    else:
        P.dobrat_sroki(stroki)  # срок только по нашим машинам, чужие карточки не дёргаем
    nash = [r for r in stroki if r['nashe_oborudovanie'] or r['centrobezhnoe']]
    for r in stroki:
        # Машину пишем целиком: тип, вывод экспертизы, срок и статус. Ничего не отсеиваем —
        # прочие устройства показывают масштаб площадки, а насосы прямо помечены насосами,
        # чтобы «центробежный» у них не читался как наша машина (450 из 462 у Химпрома).
        podr = (f"{r['data']}; вывод: {r['vyvod']}"
                + (f"; действует до {r['deystvuet_do']}" if r['deystvuet_do'] else '')
                + (f"; {r['status']}" if r.get('status') else '')
                + (f"; экспертная организация {r['ekspertnaya_org']}" if r['ekspertnaya_org'] else '')
                + ('; НАСОС, не наша машина' if r['nasos'] else ''))
        nabor.dobavit('экспертиза ЭПБ',
                      'центробежная машина' if r['centrobezhnoe']
                      else ('наша машина' if r['nashe_oborudovanie'] else 'заключение'),
                      (r['obekt'] or r['nomer'])[:200], ist,
                      ssylka=r['ssylka'], modul='epb', krug=krug, podrobno=podr)
        n += 1
    centro = [r for r in stroki if r['centrobezhnoe']]
    if centro:
        nabor.dat_fakt('centrobezhnoe_dokazano', 'реестр ЭПБ', 'epb', krug)
    istyok = [r for r in nash if 'ист' in (r.get('status') or '')]
    log(f'    заключений ТУ в реестре: {len(stroki)} | наших машин: {len(nash)} | '
        f'центробежных: {len(centro)} | с истёкшей ЭПБ: {len(istyok)}')
    return {'zapisey': n, 'zaklyucheniy': len(stroki), 'nashih': len(nash),
            'centrobezhnyh': len(centro), 'istyokshih': len(istyok)}


# ═════════════════════════════════════════════════════════════ МОДУЛЬ: снимок панели
def mod_snimok_paneli(nabor, krug, log):
    """Локальный снимок базы панели обогащения (enrich_snapshot.db).

    Это выгруженный с сервера срез: компании, роль-почты и сигналы (капекс-события) с
    ссылкой на источник. Лежит рядом, ключа не требует, читается по ИНН — по одному
    работает как есть.
    """
    import sqlite3
    put = os.path.join(RAB, 'panel', 'enrich_snapshot.db')
    if not os.path.exists(put):
        return {'zapisey': 0, 'pusto': f'нет файла {put}'}
    cx = sqlite3.connect('file:%s?mode=ro' % put, uri=True)
    cx.row_factory = sqlite3.Row
    ist = 'панель обогащения (снимок enrich_snapshot.db)'
    n = 0
    for r in cx.execute('select * from companies where inn=?', (nabor.inn,)):
        d = dict(r)
        for pole, chto in (('name', 'название'), ('okved', 'ОКВЭД'), ('region', 'регион'),
                           ('activity', 'деятельность'), ('division', 'направление')):
            if d.get(pole):
                nabor.dobavit('реквизиты', chto, d[pole], ist, modul='snimok_paneli', krug=krug)
                n += 1
        if d.get('name'):
            nabor.dat_fakt('nazvanie', d['name'], 'snimok_paneli', krug)
        if d.get('site'):
            dom = _domen_iz(d['site'])
            nabor.dobavit('реквизиты', 'сайт', dom, ist, ssylka=d['site'],
                          modul='snimok_paneli', krug=krug)
            nabor.dat_fakt('sayt', dom, 'snimok_paneli', krug)
            nabor.dat_fakt('domen', dom, 'snimok_paneli', krug)
            n += 1
        for v in _razbit(d.get('phones')):
            nom = _nomer(v)
            if nom:
                nabor.dobavit('контакт', 'телефон', nom, ist, vid=_vid_nomera(nom),
                              modul='snimok_paneli', krug=krug)
                n += 1
        if d.get('best_email'):
            nabor.dobavit('контакт', 'почта', d['best_email'].lower(), ist, vid='почта',
                          modul='snimok_paneli', krug=krug)
            n += 1
    for r in cx.execute('select * from emails where inn=?', (nabor.inn,)):
        d = dict(r)
        nabor.dobavit('контакт', 'почта', (d.get('email') or '').lower(),
                      f"{ist}: {d.get('source') or 'без источника'}", vid=f"почта {d.get('role') or ''}".strip(),
                      chelovek=d.get('person') or '', modul='snimok_paneli', krug=krug)
        dom = (d.get('email') or '').split('@')[-1].lower()
        if dom and dom not in SVOBODNAYA_POCHTA:
            nabor.dat_fakt('domen', dom, 'snimok_paneli', krug)
        n += 1
    for r in cx.execute('select * from signals where inn=?', (nabor.inn,)):
        d = dict(r)
        nabor.dobavit('новость', d.get('event_type') or 'сигнал', (d.get('what') or '')[:400],
                      f"{ist}: {d.get('source') or ''}".strip(': '),
                      ssylka=_ssylka_ok(d.get('source_url')), modul='snimok_paneli', krug=krug,
                      podrobno=f"сумма {d.get('sum') or '—'}, острота {d.get('hotness')}")
        n += 1
    cx.close()
    return {'zapisey': n}


# ═════════════════════════════════════════════════════════════ МОДУЛЬ: Тендер.Про
_TP_KOMPANII = {}          # id компании на площадке -> ИНН (кэш на прогон)
_TP_KONTROL = None         # результат контрольной бессмыслицы


def _tp_spisok(company_name, page=1):
    import tenderpro_harvest as T
    q = {'sid': '', 'good_name': '', 'tender_name': '', 'dateb': '', 'datee': '',
         'tender_type': '100', 'company_name': company_name, 'tender_state': '0',
         'tender_show_own': '0', 'tender_id': '', 'country': '1', 'region': '0_0',
         'basis': '1', 'tender_promoter': '1', 'tender_officer': '0', 'company_id': '',
         'by': '25', 'order': '3', 'page': str(page)}
    return T.vzyat(T.LIST_URL + '?' + urllib.parse.urlencode(q)) or ''


def _tp_inn_kompanii(cid):
    """ИНН компании площадки. Он напечатан прямо в заголовке карточки компании."""
    import tenderpro_harvest as T
    if cid in _TP_KOMPANII:
        return _TP_KOMPANII[cid]
    h = T.vzyat(T.COMP_URL % cid) or ''
    m = re.search(r'ИНН\s*(\d{10}|\d{12})', T.bez_tegov(h))
    _TP_KOMPANII[cid] = m.group(1) if m else ''
    return _TP_KOMPANII[cid]


def mod_tenderpro(nabor, krug, log, predel_kartochek=10):
    """Тендер.Про: карточки закупок компании и ТЕХНИЧЕСКИЙ контакт из свободного текста.

    `tenderpro_harvest.py` умеет обходить площадку по ключевым СЛОВАМ (компрессор,
    нагнетатель...). По одной компании нужен другой вход — фильтр `company_name` в той же
    форме `/api/tenders/list`. Функции разбора (`vzyat`, `bez_tegov`, `telefony_iz_teksta`,
    `CALLTO`) берутся как есть.

    ДВА ЗАСЛОНА, оба поставлены по замеру, а не на всякий случай:
    1. Контрольная бессмыслица. Фильтр `company_name` проверен: «кастрюлякастрюля» даёт
       ноль тендеров, значит фильтр применяется. А вот фильтр `company_id` НЕ применяется
       вовсе — с несуществующим id площадка отдаёт те же 25 записей, что и без фильтра.
       Поэтому ищем по имени, а не по id, хотя id выглядит надёжнее.
    2. Привязка по ИНН, а не по имени. Совпадение имени ничего не доказывает: у «Химпрома»
       в стране не одно юрлицо. Карточка принимается, только если ИНН компании с площадки
       равен нашему; остальные считаются и в записи не идут.
    """
    global _TP_KONTROL
    import tenderpro_harvest as T
    import patenty_harvest as P
    imya = nabor.odin('nazvanie')
    yadro = P.chistoe_imya(imya)[:40].strip()
    if len(yadro) < 3:
        return {'zapisey': 0, 'pusto': f'название «{imya}» после чистки короче трёх знаков'}
    if _TP_KONTROL is None:
        h = _tp_spisok('кастрюлякастрюля')
        _TP_KONTROL = len(set(T.ID_TENDER.findall(h)))
        log(f'    контроль фильтра: бессмыслица даёт {_TP_KONTROL} тендеров '
            f'({"фильтр применяется" if _TP_KONTROL == 0 else "ФИЛЬТР НЕ ПРИМЕНЯЕТСЯ, числа ниже не значат ничего"})')
    h = _tp_spisok(yadro)
    ids = list(dict.fromkeys(T.ID_TENDER.findall(h)))
    log(f'    запрос по названию «{yadro}»: тендеров на первой странице {len(ids)}')
    ist = 'Тендер.Про'
    n, chuzhih, nashih = 0, 0, 0
    for tid in ids[:predel_kartochek]:
        kart = T.vzyat(T.CARD_URL % tid) or ''
        if kart.startswith('__ОШИБКА__'):
            continue
        cids = list(dict.fromkeys(re.findall(r'/company/(\d+)', kart)))
        nash = any(_tp_inn_kompanii(c) == nabor.inn for c in cids[:3])
        if not nash:
            chuzhih += 1
            continue
        nashih += 1
        ssylka = f'https://www.tender.pro/api/tender/{tid}/view_public'
        tekst = T.bez_tegov(kart)
        predmet = re.search(r'Тендер\s+(.{5,160}?)\s*\(id' + tid, tekst)
        if predmet:
            nabor.dobavit('тендер', 'предмет закупки', predmet.group(1), ist, ssylka=ssylka,
                          modul='tenderpro', krug=krug, podrobno=f'id{tid}')
            n += 1
        nabor.dat_fakt('id_zakupki', tid, 'tenderpro', krug)
        # телефоны: сперва разметка площадки, потом двухуровневая регулярка модуля
        nomera = [x for x in T.CALLTO.findall(kart)] + T.telefony_iz_teksta(tekst)
        for raw in dict.fromkeys(nomera):
            nom = _nomer(raw)
            if not nom:
                continue
            okno = _okno_vokrug(tekst, raw)
            fio, dolzh = _kto_ryadom(okno, raw)
            nabor.dobavit('контакт', 'телефон', nom, ist, ssylka=ssylka,
                          vid=_vid_nomera(nom, okno), chelovek=fio, dolzhnost=dolzh,
                          modul='tenderpro', krug=krug, podrobno=okno[:200])
            n += 1
            if fio:
                nabor.dobavit('человек', 'ФИО', fio, ist, ssylka=ssylka, chelovek=fio,
                              dolzhnost=dolzh, modul='tenderpro', krug=krug)
                nabor.dat_fakt('fio', fio, 'tenderpro', krug)
        for m in dict.fromkeys(RX_POCHTA.findall(tekst)):
            dom = m.split('@')[1].lower()
            nabor.dobavit('контакт', 'почта', m.lower(), ist, ssylka=ssylka, vid='почта',
                          modul='tenderpro', krug=krug)
            n += 1
            if dom not in SVOBODNAYA_POCHTA:
                nabor.dat_fakt('domen', dom, 'tenderpro', krug)
        time.sleep(0.4)
    log(f'    карточек наших {nashih}, чужих (ИНН не совпал) {chuzhih}')
    return {'zapisey': n, 'nashih_kartochek': nashih, 'chuzhih_kartochek': chuzhih}


def _okno_vokrug(tekst, kusok, sleva=260, sprava=120):
    i = tekst.find(kusok)
    if i < 0:
        return ''
    return tekst[max(0, i - sleva): i + len(kusok) + sprava]


def _kto_ryadom(okno, nomer_kak_v_tekste):
    """ФИО и должность рядом с номером — готовым разбором `doobogatit_obhod`.

    Он ждёт текст с маркером `[тел: ...]` и берёт ближайшее ФИО СЛЕВА от маркера (правило,
    выведенное замером: выбор «по минимальному расстоянию» систематически приписывает
    номер СЛЕДУЮЩЕМУ человеку в списке). Поэтому маркер сюда и подставляется.
    """
    if not okno:
        return '', ''
    try:
        import doobogatit_obhod as DO
        s = okno.replace(nomer_kak_v_tekste, f'[тел: {nomer_kak_v_tekste}]', 1)
        return DO.fio_i_dolzhnost(s)
    except Exception:  # noqa: BLE001
        return '', ''


# ═════════════════════════════════════════════════════════════ МОДУЛЬ: новости
def mod_novosti(nabor, krug, log, predel=20):
    """Новости о компании: назначения, новые проекты, лица компании.

    Источник тот же, что у коллектора `col_google` из `rassyl/news_scan.py` — лента
    Google News RSS. Сам модуль импортировать нельзя: его первая строка тянет
    `verify_company` из `C:\\sender\\server`, то есть он живёт только на сервере владельца.
    Поэтому здесь повторён ровно его вход (адрес ленты и разбор item), а не выдуман новый
    источник.

    Запросы — три линзы на одну компанию, потому что одним запросом назначения не
    ловятся: «завод» и «назначен главным инженером» лежат в разных новостях.
    """
    imya = nabor.odin('nazvanie')
    import patenty_harvest as P
    yadro = P.chistoe_imya(imya)
    if len(yadro) < 3:
        return {'zapisey': 0, 'pusto': 'название слишком короткое для запроса'}
    # город из реквизитов подмешивается в запрос НЕ для красоты: «Химпром» в стране не один
    # (Новочебоксарск, Волгоград, Кемерово), и без города лента отдаёт чужие новости
    gorod = nabor.znachenie('реквизиты', 'регион') or nabor.znachenie('о компании', 'region')
    gorod = re.sub(r'\s*(Республика|область|край|автономн\w+|округ|-\s*Чувашия).*', '',
                   gorod).strip()
    hvost = f' "{gorod}"' if len(gorod) > 3 else ''
    zaprosy = [f'"{yadro}"{hvost}',
               f'"{yadro}" (назначен OR назначили OR возглавил OR "главный инженер")',
               f'"{yadro}"{hvost} (компрессор OR модернизац OR "новый цех" OR инвест)']
    ist = 'Google News RSS'
    # ВАЖНО для владельца: у новости нет ИНН. Привязка здесь по НАЗВАНИЮ, а это слабее, чем
    # привязка по идентификатору, и вид записи об этом говорит прямо.
    vid_privyazki = 'привязка по названию, не по ИНН — требует проверки человеком'
    n = 0
    vidino = set()
    for q in zaprosy:
        url = ('https://news.google.com/rss/search?q=' + urllib.parse.quote(q)
               + '&hl=ru&gl=RU&ceid=RU:ru')
        try:
            body = _prosto_get(url, 20)
        except Exception as e:  # noqa: BLE001
            log(f'    запрос «{q[:40]}»: не ответил — {type(e).__name__}')
            continue
        items = _rss_razbor(body)
        log(f'    запрос «{q[:46]}»: новостей {len(items)}')
        for it in items[:predel]:
            k = (it['title'] or '')[:120]
            if not k or k in vidino:
                continue
            vidino.add(k)
            nabor.dobavit('новость', 'заголовок', k, f'{ist} ({it["source"] or "источник не назван"})',
                          ssylka=_ssylka_ok(it['link']), modul='novosti', krug=krug,
                          vid=vid_privyazki,
                          podrobno=f'{it["pubDate"]}; запрос: {q}')
            n += 1
        time.sleep(0.7)
    return {'zapisey': n}


def _rss_razbor(body):
    """Разбор RSS/Atom — повторяет `news_scan._rss_items` (см. причину в mod_novosti)."""
    out = []
    for it in (re.findall(r'<item>(.*?)</item>', body, re.S)
               or re.findall(r'<entry>(.*?)</entry>', body, re.S)):
        def g(tag):
            m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', it, re.S)
            return re.sub(r'<!\[CDATA\[|\]\]>', '', m.group(1)).strip() if m else ''
        link = g('link')
        if not link:
            m = re.search(r'<link[^>]*href="([^"]+)"', it)
            link = m.group(1) if m else ''
        out.append({'title': re.sub(r'<[^>]+>', ' ', g('title')).strip(),
                    'link': link,
                    'pubDate': g('pubDate') or g('published') or g('updated'),
                    'source': re.sub(r'<[^>]+>', ' ', g('source')).strip()})
    return out


def _prosto_get(url, timeout=20):
    ua = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
    req = urllib.request.Request(url, headers={'User-Agent': ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


# ═════════════════════════════════════════════════════════════ МОДУЛЬ: патенты
def mod_patenty(nabor, krug, log, predel=12):
    """Патенты предприятия: ФИО изобретателей рядом с названием юрлица.

    `patenty_harvest.py` читает CSV предприятий и гоняет по ним `zapros`. Здесь тот же
    `zapros` вызывается на одно имя. Ограничение источника известно заранее и записано
    в самом модуле: изобретатель мог уволиться, ценность падает с возрастом документа —
    поэтому дата патента идёт в запись.
    """
    import patenty_harvest as P
    imya = P.chistoe_imya(nabor.odin('nazvanie'))
    if len(imya) < 3:
        return {'zapisey': 0, 'pusto': 'название слишком короткое для запроса'}
    d = P.zapros(imya, pauza=2.0)
    if d is None:
        return {'zapisey': 0, 'pusto': 'patents.google не ответил — это НЕ ноль, а сбой'}
    res = (d.get('results') or {})
    items = []
    for cl in res.get('cluster', []):
        items.extend(cl.get('result', []))
    log(f'    счётчик выдачи: {res.get("total_num_results", 0)}, взято {min(len(items), predel)}')
    ist = 'патенты (patents.google.com)'
    n = 0
    for it in items[:predel]:
        p = it.get('patent', {})
        nomer = p.get('publication_number', '')
        ssylka = f'https://patents.google.com/patent/{nomer}' if nomer else ''
        zayav = (p.get('assignee') or '')
        # у патента тоже нет ИНН: заявитель совпал по имени. Пишем это видом записи, иначе
        # чужой патент однофамильца-предприятия ляжет как наш факт
        vid_p = 'привязка по названию заявителя, не по ИНН'
        nabor.dobavit('патент', 'патент', f"{nomer} — {(p.get('title') or '')[:140]}", ist,
                      ssylka=ssylka, modul='patenty', krug=krug, vid=vid_p,
                      podrobno=f"{p.get('publication_date', '')}; заявитель: {zayav[:120]}")
        n += 1
        for fio in re.split(r'[,;]', p.get('inventor') or ''):
            fio = fio.strip()
            if _fio_pohozhe(fio):
                nabor.dobavit('человек', 'изобретатель в патенте', fio, ist, ssylka=ssylka,
                              chelovek=fio, dolzhnost='изобретатель (по патенту)',
                              modul='patenty', krug=krug, vid=vid_p,
                              podrobno=f"патент {nomer} от {p.get('publication_date', '')}")
                nabor.dat_fakt('fio', fio, 'patenty', krug)
                n += 1
    return {'zapisey': n}


# ═════════════════════════════════════════════════════════════ МОДУЛЬ: обход сайта
def mod_obhod_sayta(nabor, krug, log, stranic=25):
    """Обход сайта компании на сервере владельца: контакты, ФИО, должности.

    Почему через сервер, а не отсюда. Обходчик живёт в `rassyl/news_scan.py`
    (`args.site_crawl`) и запускается задачей раннера `news_scan`. У сервера российский
    IP и обход капчи, у песочницы ни того ни другого; часть заводских сайтов вдобавок
    отвечает только по ГОСТ-TLS (проверено на www.himprom.com: из песочницы handshake
    failure). Пустой результат тут — свойство сайта, а не ноль данных: он так и пишется.

    Разбор страниц — готовыми регулярками `regex_lica` через `doobogatit_obhod`.
    """
    import run_on_server as R
    sayt = nabor.odin('sayt')
    r = R.submit('news_scan', {'site_crawl': [sayt], 'pages_cap': stranic}, poll=10, timeout=900)
    if not r.get('ok'):
        return {'zapisey': 0, 'pusto': f"раннер вернул не ok: {str(r.get('error'))[:160]}"}
    data = r.get('data') or {}
    stranicy = []
    for dom, spisok in (data.get('pages') or {}).items():
        stranicy.extend(spisok)
    log(f'    страниц обойдено: {len(stranicy)} ({data.get("sites")})')
    if not stranicy:
        return {'zapisey': 0,
                'pusto': f'сайт {sayt} не отдал ни одной страницы обходчику сервера '
                         f'(это свойство сайта, а не отсутствие данных)'}
    ist = f'обход сайта {sayt} (раннер, task=news_scan)'
    n = 0
    for st in stranicy:
        tekst = st.get('text') or ''
        for raw in dict.fromkeys(_telefony(tekst)):
            nom = _nomer(raw)
            if not nom:
                continue
            okno = _okno_vokrug(tekst, raw)
            fio, dolzh = _kto_ryadom(okno, raw)
            nabor.dobavit('контакт', 'телефон', nom, ist, ssylka=st.get('url') or '',
                          vid=_vid_nomera(nom, okno), chelovek=fio, dolzhnost=dolzh,
                          modul='obhod_sayta', krug=krug, podrobno=okno[:200])
            n += 1
            if fio:
                nabor.dobavit('человек', 'ФИО', fio, ist, ssylka=st.get('url') or '',
                              chelovek=fio, dolzhnost=dolzh, modul='obhod_sayta', krug=krug)
                nabor.dat_fakt('fio', fio, 'obhod_sayta', krug)
        for m in dict.fromkeys(RX_POCHTA.findall(tekst)):
            nabor.dobavit('контакт', 'почта', m.lower(), ist, ssylka=st.get('url') or '',
                          vid='почта', modul='obhod_sayta', krug=krug)
            n += 1
            dom = m.split('@')[1].lower()
            if dom not in SVOBODNAYA_POCHTA:
                nabor.dat_fakt('domen', dom, 'obhod_sayta', krug)
    return {'zapisey': n}


def _telefony(tekst):
    import tenderpro_harvest as T
    return T.telefony_iz_teksta(tekst)


# ═════════════════════════════════════════════════════════ МОДУЛЬ: база панели на сервере
# Ответ раннера обрезан ХВОСТОМ в 6 000 знаков — замерено: печать 20 000 знаков вернулась
# как ПОСЛЕДНИЕ 6 000, начало съедено. Это и сломало первую версию модуля: JSON приходил без
# начала и не разбирался, а в отчёте выглядело как «база пуста». Второй заход — резать ответ
# на части по вызову — работал, но у «Химпрома» дал девять частей и четыре минуты.
# Поэтому результат идёт НЕ через stdout, а через общий файловый обменник: у серверного
# процесса DROP_URL и DROP_TOKEN в окружении есть (проверено PUT-ом), и путь этот в проекте
# штатный — тяжёлые данные всегда ходят через дроп.
PANEL_SKRIPT = r'''# -*- coding: utf-8 -*-
# Чтение centrifugal.db по одному ИНН. ТОЛЬКО SELECT: пересборка базы меняет то, что видит
# продавец, и это решение владельца, а не наше.
# Схема не зашита: у каждой таблицы ищется колонка с ИНН, потому что сборщик базы меняется
# чаще, чем этот запрос.
import gzip, json, os, sqlite3, urllib.request
INN = "@@INN@@"
IMYA = "@@IMYA@@"
out = {'tablicy': {}, 'oshibki': []}
try:
    cx = sqlite3.connect('file:C:/seostat/data/centrifugal.db?mode=ro', uri=True)
    cx.row_factory = sqlite3.Row
except Exception as e:
    print('ОШИБКА-БАЗЫ ' + str(e)); raise SystemExit
for (t,) in cx.execute("select name from sqlite_master where type='table'"):
    try:
        cols = [r[1] for r in cx.execute('pragma table_info("' + t + '")')]
    except Exception as e:
        out['oshibki'].append(t + ': ' + str(e)); continue
    pole = None
    for c in cols:
        if c.lower() in ('inn', 'company_inn', 'inn_zakazchika'):
            pole = c; break
    if not pole:
        continue
    try:
        rows = [dict(r) for r in cx.execute(
            'select * from "' + t + '" where "' + pole + '"=? limit 800', (INN,))]
    except Exception as e:
        out['oshibki'].append(t + ': ' + str(e)); continue
    if rows:
        # пустые поля выбрасываются только из ПЕРЕДАЧИ, а не из базы
        out['tablicy'][t] = [dict((k, v) for k, v in r.items() if v not in (None, '')) for r in rows]
telo = gzip.compress(json.dumps(out, ensure_ascii=False).encode('utf-8'))
u = os.environ.get('DROP_URL', '').rstrip('/'); tok = os.environ.get('DROP_TOKEN', '')
if not (u and tok):
    print('ОШИБКА-ДРОПА нет DROP_URL/DROP_TOKEN в окружении серверного процесса'); raise SystemExit
rq = urllib.request.Request(u + '/' + IMYA, data=telo, method='PUT',
                            headers={'X-Drop-Token': tok})
with urllib.request.urlopen(rq, timeout=120) as r:
    print('ПОЛОЖЕНО %s байт %d таблиц %d' % (IMYA, len(telo), len(out['tablicy'])))
'''


def _drop(metod, imya, telo=None):
    u = os.environ['DROP_URL'].rstrip('/')
    rq = urllib.request.Request(f'{u}/{imya}', data=telo, method=metod,
                                headers={'X-Drop-Token': os.environ['DROP_TOKEN']})
    with urllib.request.urlopen(rq, timeout=120) as r:
        return r.read()


def mod_baza_servera(nabor, krug, log):
    """Сборная база продавца centrifugal.db на сервере владельца — по одному ИНН.

    Она собирается из всего, что добыли сессии, и лежит только на сервере. Читается через
    уже существующий путь — задача раннера `enrich_contacts` с операциями `panel_file_put`
    + `panel_py` (так же, как это делают `proverka_sborki.py` и `osmotr_sborshchika.py`),
    а результат забирается с дропа (почему не из ответа — см. комментарий к PANEL_SKRIPT).
    """
    import base64
    import gzip
    import run_on_server as R
    imya_fajla = f'karta-baza-{nabor.inn}.json.gz'
    skript = (PANEL_SKRIPT.replace('@@INN@@', nabor.inn)
              .replace('@@IMYA@@', imya_fajla))
    dest = r'C:\sender\karta_kompanii_chtenie.py'
    R.submit('enrich_contacts',
             {'op': 'panel_file_put',
              'files': [{'dest': dest, 'b64': base64.b64encode(skript.encode()).decode()}]},
             poll=8, timeout=300)
    r = R.submit('enrich_contacts', {'op': 'panel_py', 'script': dest, 'timeout': 300},
                 poll=8, timeout=600)
    hvost = ((r.get('data') or {}).get('stdout_tail') or '')
    if 'ПОЛОЖЕНО' not in hvost:
        return {'zapisey': 0, 'pusto': f'сервер не положил файл на дроп: '
                                       f'{hvost.strip()[:200] or str(r)[:200]}'}
    log(f'    {hvost.strip().splitlines()[-1]}')
    try:
        d = json.loads(gzip.decompress(_drop('GET', imya_fajla)).decode('utf-8'))
    except Exception as e:  # noqa: BLE001
        return {'zapisey': 0, 'pusto': f'файл с дропа не разобрался: {type(e).__name__}: {e}'}
    finally:
        # за собой убираем: дроп общий для всех сессий, мусорить в нём нельзя
        try:
            _drop('DELETE', imya_fajla)
        except Exception:  # noqa: BLE001
            pass
    ist_baza = 'сборная база продавца (centrifugal.db на сервере)'
    n = 0
    for tabl, rows in (d.get('tablicy') or {}).items():
        log(f'    {tabl}: строк {len(rows)}')
        for r0 in rows:
            # у строк базы есть СВОЙ источник — он и идёт в провенанс первым, имя базы вторым.
            # Наоборот было бы потерей: «tenderpro:свежий:2026-07-29» говорит и откуда, и когда
            svoy = (r0.get('source') or r0.get('istochnik') or '').strip()
            istochniki = ([svoy] if svoy else []) + [ist_baza]
            ssylka = _ssylka_ok(r0.get('source_url') or r0.get('url') or r0.get('ssylka')
                                or r0.get('evidence_url'))
            fio = next((str(r0.get(k)) for k in ('person', 'fio', 'name')
                        if r0.get(k) and _fio_pohozhe(str(r0.get(k)))), '')
            dolzh = str(r0.get('position') or r0.get('role') or r0.get('post')
                        or r0.get('dolzhnost') or '')

            def pishem(razdel, chto, znach, vid='', podrobno=''):
                nonlocal n
                if not znach:
                    return
                for i in istochniki:
                    nabor.dobavit(razdel, chto, znach, i, ssylka=ssylka, chelovek=fio,
                                  dolzhnost=dolzh, modul='baza_servera', krug=krug,
                                  vid=vid, podrobno=podrobno)
                n += 1

            if tabl == 'company':
                # карточка компании в базе продавца — второй независимый источник реквизитов
                for pole, chto in (('name', 'название'), ('okved', 'ОКВЭД'),
                                   ('region', 'регион'), ('address', 'адрес'),
                                   ('revenue', 'выручка')):
                    pishem('реквизиты', chto, str(r0.get(pole) or ''))
                nabor.dat_fakt('nazvanie', str(r0.get('name') or ''), 'baza_servera', krug)
                dom = _domen_iz(str(r0.get('site') or ''))
                if dom:
                    pishem('реквизиты', 'сайт', dom)
                    nabor.dat_fakt('sayt', dom, 'baza_servera', krug)
                    nabor.dat_fakt('domen', dom, 'baza_servera', krug)
            elif tabl == 'contact':
                syroy = str(r0.get('value') or r0.get('contact') or '')
                vid_bazy = str(r0.get('kind') or '')
                if '@' in syroy:
                    pishem('контакт', 'почта', syroy.lower().strip(), vid='почта')
                    dm = syroy.split('@')[-1].lower().strip()
                    if dm and dm not in SVOBODNAYA_POCHTA:
                        nabor.dat_fakt('domen', dm, 'baza_servera', krug)
                else:
                    # «(8352)73-55-55 доб. (66-50)» — добавочный отрезается ДО нормализации,
                    # иначе четырнадцать цифр не свернутся в номер и контакт потеряется
                    osnova = re.split(r'доб|вн\.|ext', syroy, 1)[0]
                    dobav = syroy[len(osnova):].strip(' .доб()') if len(osnova) < len(syroy) else ''
                    nom = _nomer(osnova)
                    if nom:
                        vid = _vid_nomera(nom, f"{vid_bazy} {r0.get('phone_type') or ''}")
                        pishem('контакт', 'телефон', nom,
                               vid=vid + (f'; добавочный {dobav}' if dobav else ''),
                               podrobno=syroy)
                    else:
                        # не разобрался — но НЕ выбрасываем: неразобранный номер это путь
                        # к человеку, а выброшенные данные заново не добываются
                        pishem('контакт', 'номер не разобран', syroy,
                               vid=f'сырая запись из базы ({vid_bazy})')
            elif tabl == 'person':
                pishem('человек', 'ФИО', fio or str(r0.get('name') or ''),
                       vid='технический ЛПР' if str(r0.get('is_tech') or '') in ('1', 'True')
                           else '')
                for pole in ('phone', 'mobile'):
                    nom = _nomer(r0.get(pole))
                    if nom:
                        pishem('контакт', 'телефон', nom,
                               vid=_vid_nomera(nom, str(r0.get('phone_type') or '')))
                if r0.get('email'):
                    pishem('контакт', 'почта', str(r0['email']).lower(), vid='почта')
            elif tabl == 'fact':
                # факты машины: марка + доказательство. Ради них всё и собиралось
                marka = str(r0.get('model') or r0.get('marka') or '')
                podr = '; '.join(f'{k}: {v}' for k, v in r0.items()
                                 if k in ('status', 'equipment_type', 'medium', 'event_date',
                                          'evidence', 'quote') and v)
                pishem('машина', marka and 'марка' or 'факт', marka or podr[:200],
                       vid=str(r0.get('equipment_type') or ''), podrobno=podr[:600])
            else:
                pishem('база сервера', tabl,
                       json.dumps({k: v for k, v in r0.items() if v not in (None, '')},
                                  ensure_ascii=False)[:400])
            if fio:
                nabor.dat_fakt('fio', fio, 'baza_servera', krug)
    for o in (d.get('oshibki') or [])[:5]:
        log(f'    ошибка на сервере: {o}')
    return {'zapisey': n}


# ═════════════════════════════════════════════════════════ МОДУЛЬ: почта по схеме
def mod_pochta_shema(nabor, krug, log, na_cheloveka=8):
    """Кандидаты корпоративного адреса по ФИО и домену — `email_guess.candidates`.

    Это НЕ добытые адреса, а гипотезы: схемы адресов у компаний разные, но пространство
    схем мало и перечислимо. Они пишутся отдельным видом «почта-кандидат (не проверена)»,
    чтобы продавец не принял их за найденный контакт. Проверка — `email_probe.py` по SMTP,
    и она отдельным шагом: много проб с одного IP = блокировка.
    """
    import email_guess as EG
    domen = ''
    for d in sorted(nabor.fakty.get('domen') or []):
        if d not in SVOBODNAYA_POCHTA:
            domen = d
            break
    if not domen:
        return {'zapisey': 0, 'pusto': 'все известные домены — бесплатная почта'}
    # порядок людей не случайный: сперва те, у кого известна должность и много источников —
    # по ним адрес нужнее и проверять его осмысленнее. Полное ФИО вперёд инициалов:
    # у «Иванов И.И.» схем адреса вдвое больше, и почти все они мимо.
    lyudi = [z for z in nabor.zapisi.values() if z['chelovek']]
    lyudi.sort(key=lambda z: (-len(z['istochniki']), not bool(z['dolzhnost']),
                              -len(z['chelovek'].split())))
    imena = list(dict.fromkeys(z['chelovek'] for z in lyudi))
    n = 0
    for fio in imena[:40]:
        try:
            kand = EG.candidates(fio, domen, limit=na_cheloveka)
        except Exception:  # noqa: BLE001
            continue
        for adres in kand:
            nabor.dobavit('контакт', 'почта-кандидат', adres,
                          f'схема адреса по ФИО и домену {domen} (email_guess)',
                          vid='почта-кандидат (НЕ проверена)', chelovek=fio,
                          modul='pochta_shema', krug=krug)
            n += 1
    log(f'    людей {len(imena)}, домен {domen}, кандидатов {n}')
    return {'zapisey': n}


# ═════════════════════════════════════════════════════════════ РЕЕСТР МОДУЛЕЙ
# Одно место, где объявлено всё: имя, что даёт, чем запускается, что ему нужно от среды,
# что ему нужно ЗНАТЬ о компании и какие факты он добавляет. Последние две графы и делают
# возможными круги: по ним считается, кто откроется после кого.
REESTR = [
    {'imya': 'korpus',
     'chto_dayot': 'всё, что проект уже добыл об этой компании: люди, номера, почты, машины, состояния',
     'zapusk': mod_korpus, 'sredy': ['korpus'], 'nuzhno': ['inn'],
     'dayot': ['nazvanie', 'sayt', 'domen', 'fio'], 'po_odnomu': True},

    {'imya': 'egrul',
     'chto_dayot': 'карточка ЕГРЮЛ: официальное название, ОГРН, адрес, ОКВЭД, статус, руководитель',
     'zapusk': mod_egrul, 'sredy': ['dadata'], 'nuzhno': ['inn'],
     'dayot': ['nazvanie', 'fio'], 'po_odnomu': True},

    {'imya': 'epb',
     'chto_dayot': 'реестр заключений промбезопасности по владельцу ОПО: машины, сроки, экспертные организации',
     'zapusk': mod_epb, 'sredy': [], 'nuzhno': ['inn'],
     'dayot': ['nazvanie', 'centrobezhnoe_dokazano'], 'po_odnomu': True},

    {'imya': 'snimok_paneli',
     'chto_dayot': 'локальный снимок базы обогащения: реквизиты, роль-почты, капекс-сигналы',
     'zapusk': mod_snimok_paneli, 'sredy': [], 'nuzhno': ['inn'],
     'dayot': ['nazvanie', 'sayt', 'domen'], 'po_odnomu': True},

    {'imya': 'baza_servera',
     'chto_dayot': 'сборная база продавца centrifugal.db на сервере владельца (люди, контакты, факты)',
     'zapusk': mod_baza_servera, 'sredy': ['server'], 'nuzhno': ['inn'],
     'dayot': ['fio', 'nazvanie', 'sayt', 'domen'], 'po_odnomu': True},

    {'imya': 'tenderpro',
     'chto_dayot': 'закупки Тендер.Про и технический контакт из свободного комментария карточки',
     'zapusk': mod_tenderpro, 'sredy': [], 'nuzhno': ['nazvanie'],
     'dayot': ['fio', 'domen', 'id_zakupki'], 'po_odnomu': True},

    {'imya': 'novosti',
     'chto_dayot': 'новости о компании: назначения, новые проекты, лица компании',
     'zapusk': mod_novosti, 'sredy': [], 'nuzhno': ['nazvanie'],
     'dayot': [], 'po_odnomu': True},

    {'imya': 'patenty',
     'chto_dayot': 'патенты предприятия и ФИО изобретателей',
     'zapusk': mod_patenty, 'sredy': [], 'nuzhno': ['nazvanie'],
     'dayot': ['fio'], 'po_odnomu': True},

    {'imya': 'obhod_sayta',
     'chto_dayot': 'обход сайта компании на сервере: телефоны, почты, ФИО с должностями',
     'zapusk': mod_obhod_sayta, 'sredy': ['server'], 'nuzhno': ['sayt'],
     'dayot': ['fio', 'domen'], 'po_odnomu': True},

    {'imya': 'pochta_shema',
     'chto_dayot': 'кандидаты корпоративного адреса по ФИО и домену (гипотезы, не факты)',
     'zapusk': mod_pochta_shema, 'sredy': [], 'nuzhno': ['fio', 'domen'],
     'dayot': [], 'po_odnomu': True},
]

# Модули, которые по одному ИНН вызвать НЕЛЬЗЯ. Они объявлены здесь нарочно: молчаливое
# отсутствие в списке выглядело бы как «такого источника у нас нет», а это неправда.
# У каждого назван КОНКРЕТНЫЙ шаг, который сделает его доступным.
NE_PO_ODNOMU = [
    {'imya': 'serp_sayt',
     'chto_dayot': 'сайт компании из поисковой выдачи (sayty_dlya_celey.py)',
     'pochemu': 'нет ключей XMLRIVER_USER/XMLRIVER_KEY: платная выдача владельца, ключи '
                'заданы в службе на сервере, в ключнице раннера их нет',
     'chto_sdelat': 'положить XMLRIVER_USER/XMLRIVER_KEY в ключницу раннера — модуль сам '
                    'ходит по одной компании (find_site_via_xmlriver), переделки не требует',
     'nuzhno': ['nazvanie'], 'dayot': ['sayt', 'domen']},

    {'imya': 'lpr_serp_lico',
     'chto_dayot': 'человек по запросу «название + должность» в выдаче: главный инженер, '
                   'энергетик, механик (lpr_serp.py, режимы serp/narrow)',
     'pochemu': 'нет ключей XMLRIVER + модуль импортирует news_scan/enrich_db из '
                'C:\\sender\\server, то есть исполняется только на сервере владельца',
     'chto_sdelat': 'добавить задачу lpr_serp в allowlist раннера (job_runner.py) и в ней '
                    'аргумент --inn на одну цель вместо чтения newsco_targets.jsonl',
     'nuzhno': ['nazvanie'], 'dayot': ['fio']},

    {'imya': 'lpr_serp_back',
     'chto_dayot': 'обратный ход: телефон по уже известному ФИО (lpr_serp.py, режим back)',
     'pochemu': 'то же — ключи XMLRIVER и исполнение только на сервере',
     'chto_sdelat': 'то же плюс аргумент --fio, сейчас режим берёт людей пачкой из базы',
     'nuzhno': ['fio'], 'dayot': []},

    {'imya': 'spravochnik_podrazdeleniy',
     'chto_dayot': 'телефонный справочник подразделений на сайте: ОГЭ, ОГМ, производство '
                   'поимённо с прямыми номерами (dept_directory.py)',
     'pochemu': 'модуль пишет через EnrichDB и импортирует enrich_contacts из '
                'C:\\sender\\server; задачи для него в allowlist раннера нет '
                '(проверено 03.08.2026: allowlist = ping, enrich_contacts, verify_company, '
                'browser_probe, news_scan)',
     'chto_sdelat': 'добавить task dept_directory в job_runner.py и аргумент --sayt на один '
                    'домен вместо чтения общего списка целей',
     'nuzhno': ['sayt'], 'dayot': ['fio']},

    {'imya': 'eis_zakupki',
     'chto_dayot': 'закупки ЕИС и вложения (техзадания, листы согласования с ФИО технарей): '
                   'eis_probe.py, vlozheniya.py',
     'pochemu': 'zakupki.gov.ru из песочницы не отвечает (код 000, проверено), а оба модуля '
                'ходят туда через задачу раннера fetch_url — её в allowlist НЕТ',
     'chto_sdelat': 'применить готовый патч seo-texts/server/patch_add_fetch_url.py на '
                    'сервере: он и добавляет fetch_url в allowlist',
     'nuzhno': ['inn', 'nazvanie'], 'dayot': ['fio', 'id_zakupki']},

    {'imya': 'erknm',
     'chto_dayot': 'надзорные мероприятия ЕРКНМ по ИНН (erknm_harvest.py)',
     'pochemu': 'источник отдаётся только помесячными архивами по 230–340 МБ — качать '
                '2 ГБ ради одной компании бессмысленно',
     'chto_sdelat': 'ничего: прогон уже сделан пачкой, а его результат читает модуль '
                    'korpus из zhurnal/ERKNM-25-INN.csv',
     'nuzhno': ['inn'], 'dayot': []},

    {'imya': 'lica_provajderom',
     'chto_dayot': 'разбор свободных комментариев карточек моделью: кто человек, техническая '
                   'ли роль, чей из двух номеров (tenderpro_lica.py, erknm_razbor.py)',
     'pochemu': 'тратит оплаченную владельцем квоту провайдера, поэтому по умолчанию '
                'выключен; регулярный разбор ФИО и должности уже делает модуль tenderpro '
                'через regex_lica',
     'chto_sdelat': 'включается сознательно: --s-provajderom (пока не подключён — сперва '
                    'решение владельца о шлюзе router.cheap)',
     'nuzhno': ['id_zakupki'], 'dayot': ['fio']},
]


# ═════════════════════════════════════════════════════════════ прогон по компании
def sredy_gotovy(m):
    """(доступен, причина). Причина — про среду, а не про факты."""
    for imya in m['sredy']:
        ok, prichina = PROVERKI_SREDY[imya]()
        if not ok:
            return False, prichina
    return True, ''


def kto_dayot(fakt, krome=()):
    """Кто из модулей обещает этот факт. Нужно, чтобы «ждёт факта» называло виновника."""
    dayushchie = [m['imya'] for m in REESTR if fakt in m['dayot'] and m['imya'] not in krome]
    return dayushchie


def progon(inn, tolko=None, predel_krugov=5, tiho=False):
    """Собрать карту одной компании кругами до неподвижной точки."""
    def log(s):
        if not tiho:
            print(s, flush=True)

    nabor = Nabor(inn)
    moduli = [m for m in REESTR if not tolko or m['imya'] in tolko]
    sostoyanie = {}          # имя -> запись отчёта
    sdelano = set()
    krug = 0
    prichina_ostanova = ''

    # среда считается один раз: она не меняется от круга к кругу
    for m in moduli:
        ok, prich = sredy_gotovy(m)
        sostoyanie[m['imya']] = {
            'imya': m['imya'], 'chto_dayot': m['chto_dayot'],
            'sostoyanie': 'ждёт' if ok else 'нет_среды',
            'prichina': prich, 'krug': None, 'zapisey': 0, 'dal_fakty': [],
            'otkryl_ego': '', 'oshibka': '', 'sekund': 0.0}

    log(f'\n{"=" * 78}\nКАРТА КОМПАНИИ ПО ИНН {inn}\n{"=" * 78}')
    while krug < predel_krugov:
        krug += 1
        ochered = []
        for m in moduli:
            s = sostoyanie[m['imya']]
            if m['imya'] in sdelano or s['sostoyanie'] == 'нет_среды':
                continue
            ne_hvataet = [f for f in m['nuzhno'] if not nabor.est(f)]
            if ne_hvataet:
                dayut = kto_dayot(ne_hvataet[0], krome=(m['imya'],))
                s['sostoyanie'] = 'ждёт_факта'
                s['prichina'] = (f'ждёт факт «{ne_hvataet[0]}» ({FAKTY_OPIS[ne_hvataet[0]]}); '
                                 f'его дают: {", ".join(dayut) or "никто из включённых модулей"}')
                continue
            ochered.append(m)
        if not ochered:
            prichina_ostanova = ('круг пуст: все доступные модули отработаны, остальные ждут '
                                 'фактов, которых уже некому дать')
            krug -= 1
            break

        otkrylo = [m['imya'] for m in ochered if krug > 1]
        log(f'\n─── КРУГ {krug}' + (f'   (открылось: {", ".join(otkrylo)})' if otkrylo else ''))
        # Кто на этом круге НЕ идёт и почему — печатается сразу, а не только в итоге.
        # Иначе владелец видит «модуль пропущен» и не понимает, ждать его или чинить среду.
        for m in moduli:
            s = sostoyanie[m['imya']]
            if m['imya'] in sdelano or m in ochered:
                continue
            log(f'  {m["imya"]}: ПРОПУСК — {s["prichina"]}')
        novyh_faktov = 0
        for m in ochered:
            s = sostoyanie[m['imya']]
            sdelano.add(m['imya'])
            bylo_faktov = {k: set(v) for k, v in nabor.fakty.items()}
            t0 = time.time()
            log(f'  {m["imya"]}:')
            try:
                itog = m['zapusk'](nabor, krug, log) or {}
                # модуль считает свои ОБРАЩЕНИЯ к накопителю, а нам нужно, сколько РАЗНЫХ
                # записей за ним стоит: у korpus 6 692 обращения дают 1 058 записей, потому
                # что одно и то же приходит из десятка выгрузок. Печатать первое число как
                # «записей» — врать в свою пользу.
                s['obrashcheniy'] = itog.get('zapisey', 0)
                s['zapisey'] = sum(1 for z in nabor.zapisi.values()
                                   if m['imya'] in z['moduli'])
                if itog.get('pusto'):
                    s['sostoyanie'] = 'пусто'
                    s['prichina'] = itog['pusto']
                elif s['zapisey'] == 0:
                    # ноль записей без объяснения — тоже ответ, и его надо назвать словами,
                    # иначе «готово, записей 0» читается как «модуль отработал успешно»
                    s['sostoyanie'] = 'пусто'
                    s['prichina'] = 'модуль отработал, но по этому ИНН ничего не нашёл'
                else:
                    s['sostoyanie'] = 'готово'
                    s['prichina'] = ''
                for k, v in itog.items():
                    if k not in ('zapisey', 'pusto'):
                        s.setdefault('podrobno', {})[k] = v
            except Exception as e:  # noqa: BLE001
                s['sostoyanie'] = 'ошибка'
                s['oshibka'] = f'{type(e).__name__}: {str(e)[:220]}'
                s['prichina'] = s['oshibka']
                log(f'    ОШИБКА: {s["oshibka"]}')
            s['sekund'] = round(time.time() - t0, 1)
            s['krug'] = krug
            # какие факты он добавил впервые
            dal = []
            for f, znach in nabor.fakty.items():
                novye = znach - bylo_faktov.get(f, set())
                if novye and (f not in bylo_faktov or not bylo_faktov[f]):
                    dal.append(f)
                elif novye:
                    dal.append(f + ' (пополнил)')
            s['dal_fakty'] = dal
            chistyh = [f for f in dal if '(пополнил)' not in f]
            novyh_faktov += len(chistyh)
            nabor.zhurnal.append({'krug': krug, 'modul': m['imya'],
                                  'sostoyanie': s['sostoyanie'], 'zapisey': s['zapisey'],
                                  'dal_fakty': dal, 'sekund': s['sekund']})
            log(f'    итог: {s["sostoyanie"]}, записей {s["zapisey"]}, {s["sekund"]} с'
                + (f'; дал факты: {", ".join(dal)}' if dal else ''))
        if novyh_faktov == 0:
            ozhidayut = [n for n, s in sostoyanie.items() if s['sostoyanie'] == 'ждёт_факта']
            if ozhidayut:
                prichina_ostanova = (f'круг {krug} не добавил ни одного нового факта — '
                                     f'значит ожидающие модули ({", ".join(ozhidayut)}) '
                                     f'не откроются никогда, это неподвижная точка')
                break
    else:
        prichina_ostanova = f'достигнут предел кругов ({predel_krugov})'
    if not prichina_ostanova:
        prichina_ostanova = 'все модули отработаны'

    # чем открылся каждый модуль, запущенный не на первом круге
    for imya, s in sostoyanie.items():
        if s['krug'] and s['krug'] > 1:
            m = next(x for x in moduli if x['imya'] == imya)
            # открыл его тот факт, который появился ПОСЛЕДНИМ из нужных: пока его не было,
            # модуль стоял, сколько бы остальных ни набралось
            _, fakt = max(((nabor.otkuda_fakt.get(f) or ('?', 0))[1], f) for f in m['nuzhno'])
            kto, k = nabor.otkuda_fakt.get(fakt, ('?', 0))
            s['otkryl_ego'] = f'факт «{fakt}» от модуля {kto} на круге {k}'
    return nabor, sostoyanie, krug, prichina_ostanova


# ═════════════════════════════════════════════════════════════ отчёты
CSV_KOLONKI = ['inn', 'predpriyatie', 'razdel', 'chto', 'znachenie', 'vid', 'chelovek',
               'dolzhnost', 'istochniki', 'istochnikov', 'ssylki', 'moduli', 'krugi',
               'podrobno']


def zapisat(nabor, sostoyanie, krugov, prichina, kuda, tiho=False):
    os.makedirs(kuda, exist_ok=True)
    imya = nabor.odin('nazvanie') or ''
    zapisi = sorted(nabor.zapisi.values(),
                    key=lambda z: (-len(z['istochniki']), z['razdel'], z['chto'],
                                   z['znachenie']))
    put_csv = os.path.join(kuda, f'karta-{nabor.inn}.csv')
    with open(put_csv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_KOLONKI, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for z in zapisi:
            w.writerow({'inn': nabor.inn, 'predpriyatie': imya, 'razdel': z['razdel'],
                        'chto': z['chto'], 'znachenie': z['znachenie'], 'vid': z['vid'],
                        'chelovek': z['chelovek'], 'dolzhnost': z['dolzhnost'],
                        'istochniki': ' | '.join(z['istochniki']),
                        'istochnikov': len(z['istochniki']),
                        'ssylki': ' | '.join(z['ssylki']),
                        'moduli': ' | '.join(z['moduli']),
                        'krugi': ' | '.join(str(x) for x in z['krugi']),
                        'podrobno': z['podrobno']})
    svod = {}
    for z in zapisi:
        svod[z['razdel']] = svod.get(z['razdel'], 0) + 1
    karta = {
        'inn': nabor.inn,
        'nazvanie': imya,
        'sobrano': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'krugov_sdelano': krugov,
        'pochemu_ostanovilis': prichina,
        'fakty': {k: sorted(v) for k, v in nabor.fakty.items()},
        'otkuda_fakt': {k: {'modul': v[0], 'krug': v[1]} for k, v in nabor.otkuda_fakt.items()},
        'moduli': list(sostoyanie.values()),
        'moduli_ne_po_odnomu': NE_PO_ODNOMU,
        'poryadok': nabor.zhurnal,
        'svod_po_razdelam': svod,
        'zapisey_vsego': len(zapisi),
        'podtverzhdeno_dvazhdy_i_bolshe': sum(1 for z in zapisi if len(z['istochniki']) > 1),
        'zapisi': [dict(z, istochnikov=len(z['istochniki'])) for z in zapisi],
    }
    put_json = os.path.join(kuda, f'karta-{nabor.inn}.json')
    with open(put_json, 'w', encoding='utf-8') as f:
        json.dump(karta, f, ensure_ascii=False, indent=1)
    if not tiho:
        pechat_itoga(karta, sostoyanie, put_json, put_csv)
    return put_json, put_csv


def pechat_itoga(karta, sostoyanie, put_json, put_csv):
    print(f'\n{"=" * 78}\nИТОГ ПО {karta["inn"]} — {karta["nazvanie"] or "название не найдено"}')
    print(f'{"=" * 78}')
    print(f'кругов сделано: {karta["krugov_sdelano"]}; остановились потому, что '
          f'{karta["pochemu_ostanovilis"]}')
    print(f'записей: {karta["zapisey_vsego"]}, из них подтверждено двумя и более '
          f'источниками: {karta["podtverzhdeno_dvazhdy_i_bolshe"]}')
    print('\nпорядок работы (что за чем и что открыло следующее):')
    for sh in karta['poryadok']:
        dal = ', '.join(sh['dal_fakty']) or '—'
        print(f'  круг {sh["krug"]}  {sh["modul"]:<16} {sh["sostoyanie"]:<8} '
              f'записей {sh["zapisey"]:<5} дал факты: {dal}')
    print('\nмодули:')
    for s in sostoyanie.values():
        hvost = ''
        if s['sostoyanie'] in ('нет_среды', 'ждёт_факта', 'пусто', 'ошибка'):
            hvost = f' — {s["prichina"]}'
        elif s['otkryl_ego']:
            hvost = f' — открыл его {s["otkryl_ego"]}'
        print(f'  {s["imya"]:<18} {s["sostoyanie"]:<11}{hvost}')
    print('\nмодули, которые по одному ИНН вызвать нельзя:')
    for m in NE_PO_ODNOMU:
        print(f'  {m["imya"]:<26} {m["pochemu"][:100]}')
    print(f'\nразделы: ' + ', '.join(f'{k} — {v}' for k, v in
                                     sorted(karta['svod_po_razdelam'].items(),
                                            key=lambda x: -x[1])))
    print(f'\nфайлы: {put_json}\n       {put_csv}')


def pechat_reestra():
    print(f'\nМОДУЛИ КАРТЫ КОМПАНИИ (доступность среды считается сейчас, доступность по '
          f'фактам — на прогоне)\n{"=" * 100}')
    for m in REESTR:
        ok, prich = sredy_gotovy(m)
        sostoyanie = 'доступен' if ok else 'НЕТ СРЕДЫ'
        print(f'\n{m["imya"]:<18} [{sostoyanie}]')
        print(f'  даёт:            {m["chto_dayot"]}')
        print(f'  требует среды:   {", ".join(m["sredy"]) or "ничего"}')
        print(f'  требует фактов:  {", ".join(m["nuzhno"])}')
        print(f'  добавляет факты: {", ".join(m["dayot"]) or "—"}')
        print(f'  по одному ИНН:   {"да" if m["po_odnomu"] else "нет"}')
        if not ok:
            print(f'  причина:         {prich}')
        else:
            zhdet = [f for f in m['nuzhno'] if f != 'inn']
            if zhdet:
                print(f'  откроется, когда будет: {", ".join(zhdet)} '
                      f'(дают: {", ".join(sorted(set(sum((kto_dayot(f) for f in zhdet), []))))})')
    print(f'\n{"=" * 100}\nПО ОДНОМУ ИНН ВЫЗВАТЬ НЕЛЬЗЯ (объявлены нарочно — молчание '
          f'выглядело бы как «источника нет»)\n{"=" * 100}')
    for m in NE_PO_ODNOMU:
        print(f'\n{m["imya"]:<26}')
        print(f'  даёт:        {m["chto_dayot"]}')
        print(f'  почему нет:  {m["pochemu"]}')
        print(f'  что сделать: {m["chto_sdelat"]}')
        print(f'  требует фактов: {", ".join(m["nuzhno"])}; добавил бы: '
              f'{", ".join(m["dayot"]) or "—"}')
    print(f'\n{"=" * 100}\nФАКТЫ, ПО КОТОРЫМ СЧИТАЮТСЯ КРУГИ\n{"=" * 100}')
    for f, o in FAKTY_OPIS.items():
        print(f'  {f:<12} {o}')
    print(f'\nсреда сейчас:')
    for imya, prov in PROVERKI_SREDY.items():
        ok, prich = prov()
        print(f'  {imya:<12} {"есть" if ok else "НЕТ"}  {prich}')


# ═════════════════════════════════════════════════════════════ вход
def main():
    p = argparse.ArgumentParser(description='Карта компании по ИНН из готовых модулей проекта')
    p.add_argument('--inn', help='один ИНН')
    p.add_argument('--spisok', help='файл со списком ИНН (по одному в строке)')
    p.add_argument('--tolko', help='запустить только эти модули, через запятую')
    p.add_argument('--spisok-moduley', action='store_true', dest='spisok_moduley',
                   help='напечатать реестр модулей и их доступность')
    p.add_argument('--kuda', default=os.path.join(RAB, 'karta'), help='куда класть результат')
    p.add_argument('--krugov', type=int, default=5, help='предел кругов (по умолчанию 5)')
    p.add_argument('--tiho', action='store_true', help='не печатать ход работы')
    a = p.parse_args()

    if a.spisok_moduley:
        pechat_reestra()
        return 0
    inns = []
    if a.inn:
        inns.append(_cifry_inn(a.inn))
    if a.spisok:
        for s in open(a.spisok, encoding='utf-8-sig', errors='replace'):
            s = _cifry_inn(s)
            if s:
                inns.append(s)
    inns = [i for i in dict.fromkeys(inns) if len(i) in (10, 12)]
    if not inns:
        p.error('нужен --inn или --spisok (ИНН — 10 или 12 цифр), либо --spisok-moduley')
    tolko = [x.strip() for x in a.tolko.split(',')] if a.tolko else None
    if tolko:
        izvestnye = {m['imya'] for m in REESTR}
        neizvestnye = [x for x in tolko if x not in izvestnye]
        if neizvestnye:
            nepo = {m['imya'] for m in NE_PO_ODNOMU}
            for x in neizvestnye:
                if x in nepo:
                    m = next(m for m in NE_PO_ODNOMU if m['imya'] == x)
                    print(f'модуль «{x}» по одному ИНН вызвать нельзя: {m["pochemu"]}',
                          file=sys.stderr)
                else:
                    print(f'модуля «{x}» нет; есть: {", ".join(sorted(izvestnye))}',
                          file=sys.stderr)
            tolko = [x for x in tolko if x in izvestnye]
            if not tolko:
                return 2

    for i, inn in enumerate(inns, 1):
        if len(inns) > 1 and not a.tiho:
            print(f'\n\n########## {i}/{len(inns)} ##########')
        nabor, sostoyanie, krugov, prichina = progon(inn, tolko, a.krugov, a.tiho)
        zapisat(nabor, sostoyanie, krugov, prichina, a.kuda, a.tiho)
    return 0


if __name__ == '__main__':
    sys.exit(main())
