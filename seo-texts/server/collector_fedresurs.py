# -*- coding: utf-8 -*-
"""Коллектор ФЕДРЕСУРС (fedresurs.ru, ЕФРСФДЮЛ) — задача 3 из TZ-RANNEE-SOBYTIE.md.

Чем этот источник отличается от остальных восьми коллекторов `news_scan.py`:
**ИНН уже лежит в самом сообщении**. Юрлицо публикует сведения о себе по закону
(ст. 7.1 129-ФЗ), и в карточке сообщения стоят ИНН/ОГРН/полное имя участников.
Поэтому шаг «имя -> dadata -> ИНН» здесь НЕ нужен, а `inn_conf` сразу `high`.

ЧТО ЗДЕСЬ ОТКРЫТО, А ЧТО НЕТ (проверено на РФ-сервере 16.09.2026, подробности и
коды ответов — в COLLECTOR-FEDRESURS.md):

* Открыто и бесплатно: JSON-API SPA `https://fedresurs.ru/backend/...`, включая
  публичную спецификацию `/backend/swagger/v1/swagger.json` (200, 366 КБ).
* HTML-страницы сайта закрыты JS-челленджем Qrator (401 на `https://fedresurs.ru/`).
  Парсить HTML бессмысленно, JSON-ручки при этом отвечают 200.
* Обязателен заголовок `Referer` с домена fedresurs.ru. Без него nginx даёт 403.
* ОТКРЫТОЙ ЛЕНТЫ сообщений ЕФРСФДЮЛ «все сообщения такого-то типа за период»
  в API НЕТ. Сообщения отдаются только в разрезе КОНКРЕТНОЙ компании
  (`/backend/companies/{guid}/publications`). Единственная сквозная лента —
  `/backend/encumbrances` (залог/лизинг/факторинг/гарантия), и она ЯВНО
  запрещена в `robots.txt` этого сайта.

Отсюда режимы:

1. `rezhim='inn'` (ПО УМОЛЧАНИЮ) — идём от СВОИХ ИНН (обзвон-база `enrich.db`,
   169 704 юрлица) и спрашиваем по каждому его сообщения за период. Путь
   `robots.txt` не запрещает. Стоимость: 2 запроса на компанию.
2. `rezhim='lenta'` — сквозная лента обременений. Даёт лизинг/залог по ВСЕЙ
   стране, но `/backend/encumbrances` стоит в Disallow. Поэтому по умолчанию
   ВЫКЛЮЧЕН и включается только осознанным решением владельца.

Формат item — как у остальных коллекторов news_scan:
    {title, link, pubDate, source, tier, collector, query}
плюс поля этого источника:
    inn, company_name, msg_type, sum, stage

Запуск: см. блок `if __name__ == '__main__':` внизу.
"""
import io
import json
import os
import re
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

# --------------------------------------------------------------------------- сеть

BASE = 'https://fedresurs.ru/backend/'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/126.0.0.0 Safari/537.36')

# Тот же приём, что в news_scan._get: системный SOCKS-прокси сервера режет часть
# хостов, а госсайты отдают Russian-Trusted-CA -> обычный urlopen падает на проверке
# сертификата. Ходим мимо прокси и без верификации TLS.
_SSLCTX = ssl.create_default_context()
_SSLCTX.check_hostname = False
_SSLCTX.verify_mode = ssl.CERT_NONE
_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                       urllib.request.HTTPSHandler(context=_SSLCTX))

# Проверено сплошным перебором 1..20 и 25/45/49/50/55: сервер принимает НЕ любое
# значение Limit. Отвечают 200 ровно шесть значений — 1, 3, 5, 8, 15, 50; все
# остальные дают 451 с ПУСТЫМ телом, детерминированно (повтор трижды — тот же 451).
# Похоже на белый список размеров страницы у самого API. Держим только рабочие:
# иначе ловим 451 на ровном месте и думаем, что нас забанили.
LIMIT_OK = (1, 3, 5, 8, 15, 50)


class Blok(Exception):
    """Источник закрылся: 401/403 от антибота, либо подряд идут отказы."""


def _limit(n):
    """Ближайшее СНИЗУ допустимое значение Limit (см. LIMIT_OK)."""
    good = [x for x in LIMIT_OK if x <= n] or [LIMIT_OK[0]]
    return good[-1]


def _get(path, referer='https://fedresurs.ru/', timeout=30, tries=3, pause=0.0):
    """GET к /backend/. Возвращает (код, тело-bytes). Referer обязателен: без него 403."""
    url = path if path.startswith('http') else BASE + path.lstrip('/')
    h = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
         'Accept-Language': 'ru-RU,ru;q=0.9', 'Referer': referer}
    code, body = 0, b''
    for i in range(tries):
        try:
            r = _NOPROXY.open(urllib.request.Request(url, headers=h), timeout=timeout)
            code, body = r.getcode(), r.read()
            break
        except urllib.error.HTTPError as e:
            try:
                body = e.read()
            except Exception:  # noqa: BLE001
                body = b''
            code = e.code
            # 404/451 — ответ по существу (нет объекта / негодная форма запроса), не ретраим.
            if code in (403, 404, 451):
                break
            time.sleep(1.2 * (i + 1))
        except Exception:  # noqa: BLE001
            code, body = 0, b''
            time.sleep(1.2 * (i + 1))
    if pause:
        time.sleep(pause)
    return code, body


def _json(path, referer='https://fedresurs.ru/', **kw):
    code, body = _get(path, referer, **kw)
    if code in (401, 403):
        raise Blok('fedresurs отдал %s на %s (Referer/антибот)' % (code, path[:80]))
    try:
        return code, json.loads(body.decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return code, None


# --------------------------------------------------------- типы сообщений ЕФРСФДЮЛ

# Коды взяты из живого справочника /backend/reference-book/message-types
# (там 125 типов ЕФРСБ-банкротства + типы ЕФРСФДЮЛ). Ниже — только то, что
# говорит о СТРОЙКЕ / РАСШИРЕНИИ / КАПВЛОЖЕНИЯХ, ради чего источник и берётся.
#   stage — шкала задачи 5 ТЗ: 1 проект/намерение, 2 стройка и закупка, 3 пуск,
#           4 действующее производство/расширение.
#   hotness 1..5 — как в остальном конвейере.
TIPY_CAPEX = {
    # --- деньги пришли и уже тратятся на технику: лизинг = закупка оборудования ---
    'FinancialLeaseContract2': dict(
        name='Заключение договора финансовой аренды (лизинга)', stage=2, hotness=3,
        zachem='лизингодатель обязан опубликовать договор; в карточке — ПРЕДМЕТ лизинга '
               '(вплоть до «компрессорная установка») и срок. Компания в этот момент '
               'ДОКАЗАННО покупает технику в долг'),
    'ChangeFinancialLeaseContract2': dict(
        name='Изменение договора финансовой аренды (лизинга)', stage=2, hotness=3,
        zachem='досрочный выкуп / добор предметов — парк техники меняется'),
    # --- кредит под залог оборудования: то же самое с другой стороны ---
    'CreationRightOfPledge2': dict(
        name='Возникновение права залога', stage=2, hotness=3,
        zachem='залог движимого имущества (станки, линии, транспорт) под кредит — '
               'деньги берутся под технику, часто одновременно с её покупкой'),
    'ChangeRightOfPledge2': dict(
        name='Изменение права залога', stage=2, hotness=2,
        zachem='перезалог/довнесение предмета — признак новой кредитной сделки'),
    # --- обеспечение под контракт/аванс: поставка или подряд на крупную сумму ---
    'IssueIndependentGuarantee': dict(
        name='Выдача независимой гарантии', stage=2, hotness=3,
        zachem='банковская гарантия выдаётся под исполнение крупного контракта или '
               'аванс — в карточке есть сумма гарантии'),
    'FinancingMonetaryRequirement': dict(
        name='Заключение договора финансирования под уступку денежного требования', stage=2,
        hotness=2, zachem='факторинг = резкий рост оборота, компания не успевает за спросом'),
    'FinancingMonetaryRequirementClient': dict(
        name='Заключение договора факторинга (сообщение клиента)', stage=2, hotness=2,
        zachem='то же самое со стороны клиента'),
    # --- решения о создании и перестройке производств ---
    'FirmCreated': dict(
        name='Создание юридического лица', stage=1, hotness=3,
        zachem='новое юрлицо под проект — самая ранняя точка, оборудование ещё не выбрано'),
    'FirmReorganization': dict(
        name='Реорганизация юридического лица', stage=1, hotness=3,
        zachem='выделение/присоединение под новую площадку или новое направление; '
               'в карточке перечислены ВСЕ участники реорганизации с их ИНН'),
    'FirmAuthorizedCapitalIncrease': dict(
        name='Увеличение уставного капитала', stage=1, hotness=4,
        zachem='в ООО деньги на стройку часто заводят именно так — прямое вливание '
               'средств учредителем, раньше любой новости'),
    'FirmAutonomousInstitutionCreation': dict(
        name='Создание автономного учреждения', stage=1, hotness=2,
        zachem='бюджетный проект с капвложениями'),
    # --- инвестдоговоры ---
    'ConclusionConcessionAgreement': dict(
        name='Заключение концессионного соглашения', stage=1, hotness=5,
        zachem='инвестиционный договор с публичной стороной: концессионер обязуется '
               'ПОСТРОИТЬ объект. Ранняя стадия с подтверждённым бюджетом'),
    'ChangeConcessionAgreement': dict(
        name='Изменение концессионного соглашения', stage=1, hotness=2, zachem='сдвиг условий стройки'),
    'SaleOrLeaseEnterprise2': dict(
        name='Продажа предприятия или передача его в аренду', stage=4, hotness=4,
        zachem='смена хозяина имущественного комплекса — новый собственник почти всегда '
               'вкладывается в модернизацию'),
    'ConclusionContractOfSale': dict(
        name='Договор с сохранением права собственности на товар', stage=2, hotness=3,
        zachem='рассрочка на оборудование: техника уже у покупателя, право собственности — нет'),
    'CreationContractWithRetainOwnershipForSubject': dict(
        name='Заключение договора с сохранением права собственности на товар', stage=2, hotness=3,
        zachem='то же самое, новая редакция типа'),
    # --- лицензии и разрешения: без них новое производство не запускают ---
    'FirmLicenseGranted': dict(
        name='Получение лицензии', stage=3, hotness=4,
        zachem='лицензию берут ПЕРЕД пуском нового объекта (взрывопожароопасные '
               'производства, фарма, пищёвка, обращение с отходами)'),
    'FirmLicenseRenewed': dict(name='Продление лицензии', stage=4, hotness=1,
                               zachem='рутина, берём только для полноты картины'),
    'FirmLicenseReissued': dict(
        name='Переоформление лицензии', stage=3, hotness=3,
        zachem='переоформляют при появлении НОВОГО адреса/объекта или нового вида работ'),
    # --- масштаб бизнеса (не событие, но вход в скоринг) ---
    'FirmAssetsValue': dict(
        name='Стоимость чистых активов', stage=4, hotness=1,
        zachem='единственный тип с гарантированной СУММОЙ в карточке; рост активов '
               'год к году = идёт капстройка. Для скоринга, не для повода написать'),
    'MandatoryAssessmentCustomer': dict(
        name='Обязательная оценка (сообщение заказчика)', stage=4, hotness=2,
        zachem='оценивают имущество перед крупной сделкой/залогом/взносом в УК'),
}

# НЕГАТИВ: если такое есть в окне — компании не до покупки оборудования.
# Собираются только при stop_tipy=True и нужны для подавления, а не для питча.
TIPY_STOP = {
    'AppearanceOfBankruptcySigns': 'Возникновение признаков банкротства',
    'BankruptcyArticle8': 'Обстоятельства по статье 8 Закона о банкротстве',
    'BankruptcyArticle9': 'Обстоятельства по статье 9 Закона о банкротстве',
    'CreditorIntentionGoToCourt': 'Намерение кредитора обратиться в суд с заявлением о банкротстве',
    'DebtorIntentionGoToCourt': 'Намерение должника обратиться в суд с заявлением о банкротстве',
    'FirmLiquidation': 'Ликвидация юридического лица',
    'FirmRegisterExclude': 'Исключение юридического лица из ЕГРЮЛ',
    'AssetImpairment': 'Обесценение активов',
    'FirmLicenseProhibited': 'Аннулирование или прекращение действия лицензии',
    'UnreliableInformation': 'Недостоверность сведений',
    'FirmStopActivity': 'Прекращение деятельности',
}

# Ключевые слова предмета лизинга/залога, которые делают сообщение по-настоящему нашим.
# Компрессор Центр — компрессоры, генераторы азота/кислорода, МКС; Meyer — фотосепараторы
# и рентген-инспекция. Совпало — поднимаем hotness, но НЕ фильтруем жёстко: техника
# в карточке часто описана обобщённо («Оборудование промышленное»).
PREDMET_KC = re.compile(
    r'компрессор|винтов|поршнев|ресивер|осушител|пневмо|воздуходув|азотн|кислородн|'
    r'газоразделит|криоген|генератор\s+азота|генератор\s+кислорода', re.I)
PREDMET_MEYER = re.compile(
    r'фотосепаратор|сепаратор|рентген|интроскоп|досмотров|сортировочн|калибровочн|'
    r'зерноочистительн|элеватор', re.I)
PREDMET_PROM = re.compile(
    r'станок|станки|линия|линию|линии|производственн|технологическ|оборудован|'
    r'экструдер|пресс|котел|котёл|печь|конвейер|дробилк|мельниц|гранулятор|'
    r'упаковочн|фасовочн|термопласт|кран мостов|кран-балк|грузоподъ|подъёмник|'
    r'подъемник|лаборатор|испытательн|насос|вентилятор|сушилк|сушильн|'
    r'термическ|литьев|формовочн|штамп|сварочн|покрасочн|окрасочн', re.I)
# Заведомо НЕ наш предмет. В лизинге это львиная доля потока: автопарк, дорожная и
# строительная техника. Само по себе сообщение остаётся (компания живая и тратит
# деньги), но поводом для питча компрессора оно не является — гасим hotness.
# Формулировки взяты из живой выдачи: «Средства транспортные», «Самоходная техника
# (ПСМ)», «Строительная и дорожно-строительная техника», «Легковой автотранспорт».
PREDMET_NE_NASH = re.compile(
    r'автомобиль|автобус|легков|седельн|тягач|полуприцеп|прицеп|самосвал|фургон|'
    r'экскаватор|каток|бульдозер|грейдер|асфальт|битум|автогрейдер|автокран|'
    r'погрузчик|трактор|комбайн|блок-модуль|вагон|баржа|судно|катер|'
    r'самоходн|спецтехник|дорожно-строительн|средства транспортн|автотранспорт|'
    r'мусоровоз|бетономешалк|бетононасос|автоцистерн|сборно-разборн', re.I)


# ------------------------------------------------------------------- вспомогательное

def _dt(s):
    """'2026-07-31T13:28:08.87' -> 'YYYY-MM-DD' (для event_date задачи 6 ТЗ)."""
    return (s or '')[:10]


def _dni_nazad(days):
    """(DateStart, DateEnd) в формате, который принимает API: YYYY-MM-DD."""
    t = time.time()
    return (time.strftime('%Y-%m-%d', time.localtime(t - days * 86400)),
            time.strftime('%Y-%m-%d', time.localtime(t + 86400)))


_SUM_KEY = re.compile(r'(sum|amount|value|price|cost|payment|razmer)', re.I)


def _naiti_summu(node, _glubina=0):
    """Найти денежную сумму в content карточки.

    У каждого типа своё поле: FirmAssetsValue -> assetsValue, гарантия -> guaranteeAmount,
    залог -> обязательство внутри вложенного объекта. Поэтому не перечисляем поля, а
    обходим дерево и берём первое осмысленное число по имени ключа.
    """
    if _glubina > 5 or node is None:
        return ''
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and _SUM_KEY.search(k) \
                    and float(v) >= 1000:
                return '%.2f' % float(v)
        for v in node.values():
            got = _naiti_summu(v, _glubina + 1)
            if got:
                return got
    elif isinstance(node, list):
        for v in node[:20]:
            got = _naiti_summu(v, _glubina + 1)
            if got:
                return got
    return ''


def _predmety(content):
    """Описания предметов лизинга/залога из карточки -> строка для заголовка.

    Схема `subjects` у разных типов разная (проверено на живых карточках):
      лизинг  -> {'identifier', 'classifier': {'code','description'}, 'description'}
      залог   -> {'itemTxtId', 'classifierCode', 'classifierName', 'description'}
    Описание у залога многострочное («Баржа-кормораздатчик\\n2012 год постройки\\n...»),
    поэтому переводы строк схлопываем.
    """
    out = []
    for s in (content.get('subjects') or [])[:6]:
        if not isinstance(s, dict):
            continue
        d = re.sub(r'\s+', ' ', (s.get('description') or '')).strip()
        cl = ((s.get('classifier') or {}).get('description')
              or s.get('classifierName') or '').strip()
        txt = d or cl
        if d and cl and cl.lower() not in d.lower():
            txt = '%s (%s)' % (d, cl)
        if txt and txt not in out:
            out.append(txt)
    return '; '.join(out)


# Где в карточке лежат стороны сделки. Имена полей разнятся от типа к типу, поэтому
# перечисляем все встреченные варианты: списки и одиночные объекты.
_STORONY = (
    ('lessees', 'лизингополучатель'), ('lessors', 'лизингодатель'),
    ('mortgagorCompanies', 'залогодатель'), ('mortgagorIndividualEntrepreneurs', 'залогодатель'),
    ('mortgagorPersons', 'залогодатель'), ('mortgagorNonResidentCompanies', 'залогодатель'),
    ('pledgeeCompanies', 'залогодержатель'), ('pledgeeIndividualEntrepreneurs', 'залогодержатель'),
    ('pledgeePersons', 'залогодержатель'), ('pledgeeNonResidentCompanies', 'залогодержатель'),
    ('pledgors', 'залогодатель'), ('pledgees', 'залогодержатель'),
    ('debtors', 'должник'), ('clients', 'клиент'), ('financialAgents', 'фактор'),
    ('principals', 'принципал'), ('beneficiaries', 'бенефициар'),
    ('buyers', 'покупатель'), ('sellers', 'продавец'), ('otherContractors', 'иная сторона'),
    ('reorganizationCompanies', 'участник реорганизации'),
    ('concessionaires', 'концессионер'), ('concedents', 'концедент'),
    ('licensingCompany', 'лицензирующий орган'), ('principal', 'принципал'),
)


def _uchastniki(content):
    """Все стороны сообщения с ИНН: [(инн, имя, роль)].

    Это и есть главная ценность Федресурса: ИНН приходит ГОТОВЫМ, шаг dadata не нужен.
    Часть сторон может быть закрыта постановлением Правительства РФ №5 от 12.01.2018
    (санкционная защита) — тогда вместо имени стоит формулировка о скрытии, а ИНН пуст.
    """
    out = []
    for pole, rol in _STORONY:
        v = content.get(pole)
        for x in (v if isinstance(v, list) else [v] if isinstance(v, dict) else []):
            if isinstance(x, dict) and x.get('inn'):
                out.append((str(x['inn']), x.get('fullName') or x.get('name') or '', rol))
    pi = content.get('publisherInfo') or {}
    if isinstance(pi, dict) and pi.get('inn'):
        out.append((str(pi['inn']), pi.get('fullName') or '', 'публикатор'))
    return out


def _tip_meta(code):
    """Описание типа из TIPY_CAPEX, с учётом старых кодов.

    У многих типов две редакции: `FinancialLeaseContract` (старая) и
    `FinancialLeaseContract2` (действующая). Справочник отдаёт обе под одним
    русским названием, а карточка старого сообщения вернёт старый код — и без
    этой поправки у него оказались бы stage=0 и заниженный hotness.
    """
    return TIPY_CAPEX.get(code) or TIPY_CAPEX.get((code or '') + '2') or {}


def _hotness(code, predmet):
    """База типа + поправка по ПРЕДМЕТУ лизинга/залога.

    База у типа умеренная: без предмета «заключён договор лизинга» — это лишь факт,
    что компания вкладывается в технику, а какую — неизвестно. Решает предмет:
    компрессор/азот/фотосепаратор — наш прямой повод (5), любая другая промышленная
    техника — соседний повод (4), автопарк и дорожная техника — почти шум (2).
    """
    h = _tip_meta(code).get('hotness', 2)
    if predmet:
        if PREDMET_KC.search(predmet) or PREDMET_MEYER.search(predmet):
            h = 5
        elif PREDMET_PROM.search(predmet) and not PREDMET_NE_NASH.search(predmet):
            h = max(h, 4)
        elif PREDMET_NE_NASH.search(predmet):
            h = min(h, 2)
    return h


# ------------------------------------------------------------- источник ИНН: наша база

DEFAULT_DB = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')


def inn_iz_bazy(db_path=None, okved=None, regions=None, limit=2000, offset=0,
                tolko_s_saytom=False, division=None):
    """Кандидаты на опрос — из своей же базы (`enrich.db`, таблица companies).

    Читаем ТОЛЬКО на чтение (`mode=ro`), ничего не пишем: правило владельца про
    enrich.db/sender.db. Фильтры `okved` (двузначные разделы, как ICP_OKVED в
    news_scan) и `regions` (коды субъектов) применяем ЛОКАЛЬНО — у Федресурса
    поиска по ОКВЭД нет вовсе (проверено: SearchString='28.13' -> found=0),
    а у нас ОКВЭД и регион уже лежат по каждому ИНН.
    """
    db = db_path or DEFAULT_DB
    if not os.path.exists(db):
        return []
    con = sqlite3.connect('file:%s?mode=ro' % db.replace('\\', '/'), uri=True, timeout=30)
    try:
        where, args = ['inn IS NOT NULL', "length(inn) IN (10,12)",
                       'COALESCE(is_competitor,0)=0'], []
        if okved:
            where.append('(' + ' OR '.join(['substr(okved,1,2)=?'] * len(okved)) + ')')
            args += [str(x).zfill(2)[:2] for x in okved]
        if regions:
            regs = [str(x).zfill(2)[:2] for x in regions]
            # region в базе заполнен не у всех, поэтому вторая ветка — по первым
            # двум цифрам ИНН (код субъекта регистрации).
            where.append('((' + ' OR '.join(['region LIKE ?'] * len(regs)) + ') OR (' +
                         ' OR '.join(['substr(inn,1,2)=?'] * len(regs)) + '))')
            args += ['%%%s%%' % r for r in regs] + regs
        if division:
            where.append('division LIKE ?')
            args.append('%%%s%%' % division)
        if tolko_s_saytom:
            where.append("COALESCE(site,'')<>''")
        q = ('SELECT inn, COALESCE(name, short_name, "") FROM companies WHERE '
             + ' AND '.join(where) + ' ORDER BY COALESCE(pxr,0) DESC, inn LIMIT ? OFFSET ?')
        return [(r[0], r[1]) for r in con.execute(q, args + [int(limit), int(offset)])]
    finally:
        con.close()


# --------------------------------------------------------------------- кэш ИНН -> guid

_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '.fedresurs_guid_cache.json')
_CACHE = None


def _cache_load():
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.load(open(_CACHE_PATH, encoding='utf-8'))
        except Exception:  # noqa: BLE001
            _CACHE = {}
    return _CACHE


def _cache_save():
    """Пишем атомарно и с fsync: прогон по 169k ИНН переживает рестарт контейнера,
    и второй раз guid'ы не выкупаются (урок durability из CLAUDE.md)."""
    if _CACHE is None:
        return
    tmp = _CACHE_PATH + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(_CACHE, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _CACHE_PATH)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------------- API-обёртки

def guid_po_inn(inn, pause=0.35):
    """ИНН -> guid карточки компании на Федресурсе (+ имя и ОКВЭД-текст).

    GET /backend/companies?SearchString=<ИНН>&Limit=5&Offset=0
    SearchString принимает ИНН, ОГРН и имя (проверено); по ОКВЭД не ищет.
    """
    c = _cache_load()
    if inn in c:
        return tuple(c[inn]) if c[inn] else (None, '', '')
    code, d = _json('companies?SearchString=%s&Limit=5&Offset=0' % urllib.parse.quote(str(inn)),
                    referer='https://fedresurs.ru/search/entity?searchString=%s' % inn,
                    pause=pause)
    rows = (d or {}).get('pageData') or []
    hit = [r for r in rows if str(r.get('inn') or '') == str(inn)]
    if not hit:
        c[inn] = None
        return None, '', ''
    r = hit[0]
    val = (r.get('guid'), r.get('name') or '', r.get('okvedName') or '')
    c[inn] = list(val)
    return val


_KARTA_TIPOV = None


def karta_tipov(pause=0.0):
    """Справочник типов: {русское название в нижнем регистре: [коды]}.

    GET /backend/reference-book/message-types -> [{code, name, project, isOld}, ...]
    (≈200 записей: project=1 — банкротные ЕФРСБ, остальное — ЕФРСФДЮЛ).
    Нужен потому, что СПИСОК публикаций отдаёт `type` РУССКИМ НАЗВАНИЕМ, а код типа
    лежит только в карточке. Имея справочник, мы отбираем нужные сообщения БЕЗ
    похода за карточкой — то есть одним запросом на компанию вместо одного на тип.
    Одному названию иногда соответствуют два кода (старый и новый, `isOld`), поэтому
    значение — список; несмешанный приоритет у не-`isOld`.
    """
    global _KARTA_TIPOV
    if _KARTA_TIPOV is not None:
        return _KARTA_TIPOV
    code, d = _json('reference-book/message-types', pause=pause)
    m = {}
    if code == 200 and isinstance(d, list):
        for x in d:
            nm = (x.get('name') or '').strip().lower()
            cd = x.get('code')
            if not nm or not cd:
                continue
            m.setdefault(nm, [])
            (m[nm].insert(0, cd) if not x.get('isOld') else m[nm].append(cd))
    _KARTA_TIPOV = m
    return m


def kod_tipa(rus_name):
    """Русское название типа -> код (предпочитая действующий). '' если не опознали."""
    v = karta_tipov().get((rus_name or '').strip().lower()) or []
    return v[0] if v else ''


def soobshcheniya_kompanii(guid, days=90, max_na_kompaniyu=30, pause=0.35, tip=None):
    """Сообщения ЕФРСФДЮЛ одной компании за период — ОДИН запрос (плюс пагинация).

    GET /backend/companies/{guid}/publications
        ?OnlySfact=true&DateStart=YYYY-MM-DD&DateEnd=YYYY-MM-DD&Limit=15&Offset=0
    Ответ: {found, pageData:[{publicationType,guid,number,datePublish,type,participants}]},
    где `type` — русское название (см. karta_tipov), `guid` — ключ карточки.

    `tip` (код) добавляет серверный фильтр `&Type=<код>`; пользоваться им имеет смысл
    только когда нужен ОДИН конкретный тип. Перебирать им два десятка капекс-типов
    нельзя: это два десятка запросов на компанию вместо одного.
    """
    ds, de = _dni_nazad(days)
    ref = 'https://fedresurs.ru/company/' + str(guid)
    lim = _limit(min(max_na_kompaniyu, 15))
    hvost = ('&Type=' + urllib.parse.quote(tip)) if tip else ''
    out, vidno, off = [], set(), 0
    while len(out) < max_na_kompaniyu:
        code, d = _json(
            'companies/%s/publications?OnlySfact=true&DateStart=%s&DateEnd=%s'
            '&Limit=%d&Offset=%d%s' % (guid, ds, de, lim, off, hvost),
            referer=ref, pause=pause)
        if code != 200 or not isinstance(d, dict):
            break
        rows = d.get('pageData') or []
        for r in rows:
            g = r.get('guid')
            if g and g not in vidno:
                vidno.add(g)
                out.append(r)
        off += lim
        if len(rows) < lim or off >= int(d.get('found') or 0):
            break
    return out


def kartochka(msg_guid, pause=0.35):
    """Карточка сообщения: GET /backend/sfact-messages/{guid}.

    Отдаёт messageType (КОД типа), typeName, datePublish, publisher, content.
    В content — суть: предметы лизинга с классификатором, стороны с ИНН/ОГРН,
    номера и даты договоров, суммы там, где они по форме есть.
    Часть сведений может быть закрыта: «Сведения скрыты в соответствии с
    требованиями постановления Правительства РФ от 12.01.2018 г. №5» (санкционная
    защита) — тогда у стороны нет ни имени, ни ИНН, и это нормальный ответ.
    """
    code, d = _json('sfact-messages/%s' % msg_guid,
                    referer='https://fedresurs.ru/sfactmessages/%s' % msg_guid, pause=pause)
    return d if code == 200 and isinstance(d, dict) else None


def obremeneniya_kompanii(guid, pause=0.35):
    """GET /backend/companies/{guid}/encumbrances — залог/лизинг/факторинг одной компании.

    Одним запросом отдаёт всё, сгруппированное по видам («Лизинг», «Залог», ...),
    но БЕЗ фильтра по датам. Полезно как дешёвая проверка «есть ли вообще у компании
    лизинг», когда период не важен. В отличие от сквозной ленты /backend/encumbrances,
    эта ручка в robots.txt НЕ запрещена.
    """
    code, d = _json('companies/%s/encumbrances' % guid,
                    referer='https://fedresurs.ru/company/%s' % guid, pause=pause)
    return d if code == 200 else None


# --------------------------------------------------------------------- сборка item'а

# Словесные названия стадий — чтобы item читался и человеком, и соседним
# коллектором `collector_egrz.py`, который пишет стадию строкой.
STAGE_NAME = {1: 'проект', 2: 'стройка', 3: 'пуск', 4: 'расширение', 0: ''}


def _item(msg_guid, code_tipa, name_tipa, date_pub, inn, company, predmet, summa, query):
    stage = _tip_meta(code_tipa).get('stage', 0)
    zagolovok = '%s — %s' % (company or ('ИНН ' + str(inn)), name_tipa or code_tipa)
    if predmet:
        zagolovok += ': ' + predmet[:120]
    if summa:
        zagolovok += ' (%s руб.)' % summa
    return {
        # обязательный формат news_scan
        'title': zagolovok[:300],
        'link': 'https://fedresurs.ru/sfactmessages/%s' % msg_guid,
        'pubDate': date_pub or '',
        'source': 'Федресурс',
        'tier': 2,                       # тир-2 «реестры», как ФРП
        'collector': 'fedresurs',
        'query': query,
        # поля этого источника
        'inn': str(inn),
        'company_name': company or '',
        'msg_type': code_tipa or '',
        'sum': summa or '',
        'stage': stage,                  # число по шкале задачи 5 ТЗ
        # --- служебное, чтобы стыковаться с соседями без переходника ---
        'stage_name': STAGE_NAME.get(stage, ''),   # как в collector_egrz.py
        'inn_conf': 'high',              # ИНН пришёл из самого сообщения, dadata не нужна
        'event_date': date_pub or '',    # уже ISO YYYY-MM-DD (задача 6 ТЗ)
        'what': (predmet or name_tipa or '')[:400],
    }


# ------------------------------------------------------------------ главный коллектор

def col_fedresurs(days=90, max_items=300, tipy=None, okved=None, regions=None,
                  inns=None, rezhim='inn', db_path=None, limit_inn=1500, offset_inn=0,
                  pause=0.35, detali=True, stop_tipy=False, division=None,
                  tolko_s_saytom=False, log=None):
    """Собрать события Федресурса.

    days        — окно публикации, дней назад (DateStart/DateEnd у API).
    max_items   — потолок числа item'ов на выходе.
    tipy        — список КОДОВ типов сообщений (ключи TIPY_CAPEX). None = все капекс-типы.
    okved       — список двузначных разделов ОКВЭД для отбора наших ИНН (локально).
    regions     — список кодов субъектов для отбора наших ИНН (локально).
    inns        — явный список ИНН; если задан, база не читается.
    rezhim      — 'inn' (по умолчанию, robots-совместимо) или 'lenta' (см. предупреждение).
    detali      — тянуть карточку каждого сообщения (предмет лизинга, сумма, все стороны).
                  Без неё item'ы будут без `sum` и без предмета, зато вдвое меньше запросов.
    stop_tipy   — добавить негативные типы (банкротные признаки) для подавления.

    Возвращает список item'ов; сводка прогона — в `col_fedresurs.summary`.
    """
    def _log(s):
        if log:
            log(s)

    tipy = list(tipy) if tipy else list(TIPY_CAPEX.keys())
    if stop_tipy:
        tipy += list(TIPY_STOP.keys())
    tipy = [t for t in tipy if t]

    if rezhim == 'lenta':
        return _lenta_obremeneniy(days=days, max_items=max_items, pause=pause, log=_log)

    if inns:
        kand = [(str(i), '') for i in inns]
    else:
        kand = inn_iz_bazy(db_path=db_path, okved=okved, regions=regions,
                           limit=limit_inn, offset=offset_inn, division=division,
                           tolko_s_saytom=tolko_s_saytom)
    _log('кандидатов на опрос: %d' % len(kand))

    items, stat = [], Counter()
    for n, (inn, imya_iz_bazy) in enumerate(kand, 1):
        if len(items) >= max_items:
            break
        try:
            guid, imya, okved_txt = guid_po_inn(inn, pause=pause)
        except Blok as e:
            stat['blok'] += 1
            _log('ОСТАНОВ: %s' % e)
            break
        if not guid:
            stat['нет на федресурсе'] += 1
            continue
        stat['найдено компаний'] += 1
        company = imya or imya_iz_bazy
        try:
            rows = soobshcheniya_kompanii(guid, days=days, pause=pause)
        except Blok as e:
            _log('ОСТАНОВ: %s' % e)
            break
        if not rows:
            stat['без сообщений в окне'] += 1
            continue
        stat['есть сообщения в окне'] += 1
        for r in rows:
            if len(items) >= max_items:
                break
            mg = r.get('guid')
            name_tipa = r.get('type') or ''
            # ОТСЕВ ПО СПРАВОЧНИКУ, а не по карточке: карточку тянем только для тех,
            # кто прошёл отбор. Иначе на каждую компанию улетает по запросу на каждое
            # её сообщение, а нужных среди них единицы.
            code_tipa = kod_tipa(name_tipa)
            if tipy and code_tipa and code_tipa not in tipy:
                stat['тип не наш'] += 1
                continue
            if tipy and not code_tipa:
                stat['тип не опознан'] += 1
                continue
            predmet, summa = '', ''
            if detali and mg:
                k = kartochka(mg, pause=pause) or {}
                code_tipa = k.get('messageType') or code_tipa
                name_tipa = k.get('typeName') or name_tipa
                cont = k.get('content') or {}
                predmet = _predmety(cont)
                summa = _naiti_summu(cont)
                # ИНН берём ИЗ СООБЩЕНИЯ (в этом вся ценность источника), а не из
                # запроса: в реорганизации и в лизинге сторон несколько.
                svoy = [u for u in _uchastniki(cont) if u[0] == str(inn)]
                if svoy and svoy[0][1]:
                    company = svoy[0][1]
            it = _item(mg, code_tipa, name_tipa, _dt(r.get('datePublish')),
                       inn, company, predmet, summa, code_tipa or name_tipa)
            it['hotness'] = _hotness(code_tipa, predmet)
            items.append(it)
            stat['сообщений'] += 1
            stat['тип:' + (code_tipa or name_tipa)[:40]] += 1
        if n % 50 == 0:
            _cache_save()
            _log('  ... %d/%d компаний, item-ов %d' % (n, len(kand), len(items)))
    _cache_save()
    col_fedresurs.summary = dict(stat)
    col_fedresurs.summary['кандидатов'] = len(kand)
    return items


col_fedresurs.summary = {}


# --------------------------------------------------------- режим сквозной ленты (OFF)

LENTA_PREDUPREZHDENIE = (
    'ВНИМАНИЕ: /backend/encumbrances стоит в Disallow файла https://fedresurs.ru/robots.txt. '
    'Ручка технически отвечает 200 и отдаёт лизинг/залог по всей стране, но владелец '
    'сайта явно попросил роботов её не обходить. Режим включается только осознанно.')


def _lenta_obremeneniy(days=30, max_items=300, pause=0.6, gruppy=('Leasing', 'Pledge'),
                       log=None):
    """Сквозная лента обременений — ВЫКЛЮЧЕНА по умолчанию, см. LENTA_PREDUPREZHDENIE.

    GET /backend/encumbrances?Group=<Leasing|Pledge|Factoring|Guarantee|ContractOfSale|
        BuyBack|RestrictionOfRightsUnderContract|RightOfItemRetention>
        &PublishDateStart=YYYY-MM-DD&PublishDateEnd=YYYY-MM-DD&Limit=50&Offset=0
    Ответ: {found, pageData:[{number, guid, publishDate, type, weakSide[], strongSide[]}]},
    где weakSide — лизингополучатель/залогодатель (НАШ клиент) с ИНН и именем.
    Ограничения: found упирается в 10000, Offset > ~50 даёт 400 — то есть лента
    читается только узкими окнами по датам.
    """
    if log:
        log(LENTA_PREDUPREZHDENIE)
    ds, de = _dni_nazad(days)
    items = []
    for grp in gruppy:
        off = 0
        while len(items) < max_items:
            code, d = _json('encumbrances?Group=%s&PublishDateStart=%s&PublishDateEnd=%s'
                            '&Limit=50&Offset=%d' % (grp, ds, de, off),
                            referer='https://fedresurs.ru/search/encumbrances', pause=pause)
            if code != 200 or not isinstance(d, dict):
                break
            rows = d.get('pageData') or []
            for r in rows:
                storony = [s for s in (r.get('weakSide') or []) if s.get('inn')]
                if not storony:
                    continue
                s = storony[0]
                items.append(_item(r.get('guid'), r.get('type') or '', r.get('type') or '',
                                   _dt(r.get('publishDate')), s.get('inn'),
                                   s.get('name') or '', '', '', 'encumbrances:' + grp))
            off += 50
            if len(rows) < 50:
                break
    return items[:max_items]


# ------------------------------------------------------------------------------ запуск

def _pechat(items):
    print('\n%-12s %-10s %-5s %-46s %s' % ('дата', 'ИНН', 'stage', 'компания', 'тип'))
    for it in items[:80]:
        print('%-12s %-10s %-5s %-46s %s' % (it['pubDate'], it['inn'], it['stage'],
                                             (it['company_name'] or '')[:46],
                                             (it['msg_type'] or '')[:40]))


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    # Параметры: key=value в argv, либо JSON в stdin — но stdin читаем ТОЛЬКО по явному
    # «-» в аргументах. Под раннером сервера (panel_py) stdin — открытая труба, и
    # безусловный read() на ней просто повиснет до таймаута задания.
    args = {}
    if '-' in sys.argv[1:]:
        try:
            raw = sys.stdin.read()
            if raw.strip():
                args = json.loads(raw)
        except Exception:  # noqa: BLE001
            args = {}
    for a in sys.argv[1:]:
        if '=' in a:
            k, v = a.split('=', 1)
            try:
                args[k] = json.loads(v)
            except Exception:  # noqa: BLE001
                args[k] = v
    kw = dict(days=int(args.get('days', 180)), max_items=int(args.get('max_items', 40)),
              tipy=args.get('tipy'), okved=args.get('okved'), regions=args.get('regions'),
              inns=args.get('inns'), rezhim=args.get('rezhim', 'inn'),
              db_path=args.get('db_path'), limit_inn=int(args.get('limit_inn', 60)),
              offset_inn=int(args.get('offset_inn', 0)),
              pause=float(args.get('pause', 0.35)),
              detali=bool(args.get('detali', True)),
              stop_tipy=bool(args.get('stop_tipy', False)),
              division=args.get('division'),
              log=lambda s: print('[fedresurs] ' + s))
    print('[fedresurs] база ИНН: %s (есть: %s)' % (kw.get('db_path') or DEFAULT_DB,
                                                   os.path.exists(kw.get('db_path') or DEFAULT_DB)))
    t0 = time.time()
    got = col_fedresurs(**kw)
    _pechat(got)
    print('\n=== СВОДКА за %.0fс ===' % (time.time() - t0))
    for k, v in sorted(col_fedresurs.summary.items()):
        print('  %-40s %s' % (k, v))
    print('  item-ов: %d' % len(got))
    if got:
        print('\n=== ПРИМЕР item ===')
        print(json.dumps(got[0], ensure_ascii=False, indent=1))
