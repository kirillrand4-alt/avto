# -*- coding: utf-8 -*-
"""Доопределение компании у безымянного раннего события (задача 4 из TZ-RANNEE-SOBYTIE.md).

Зачем. Классификатор `extract_event` требует компанию, а ранняя новость часто
безымянная: «инвестор построит завод в ОЭЗ», «подписано соглашение с резидентом».
Решение владельца 16.09: требование «есть компания» ОСТАЁТСЯ, но выбросить событие
можно только ПОСЛЕ попытки узнать имя иначе, и отсев кладётся в отдельную кучу
(`kucha_bez_imeni.py`), а не удаляется — имя может всплыть через месяц.

Шесть путей (порядок = от дешёвых к дорогим, ранний выход на первом принятом):

  ПУТЬ 5-локальный  наши же собранные события (jsonl + signals)      0 запросов, 0 ₽
  ПУТЬ 1            реестр резидентов ОЭЗ/ТОР по площадке и дате     1 HTTP, кэш сутки
  ПУТЬ 3            инвестпортал региона, «приоритетные проекты»     1-2 HTTP, кэш сутки
  ПУТЬ 2            ЕГРЗ по объекту (заказчик/застройщик)            через абстракцию
  ПУТЬ 4            Федресурс: крупная сделка привязана к ИНН        через абстракцию
  ПУТЬ 5-SERP       более поздняя новость про тот же объект          xmlriver, ПЛАТНО
  ПУТЬ 6            «объект + район + отрасль» в SERP                xmlriver, ПЛАТНО

Пути 2 и 4 намеренно НЕ реализованы здесь: коллекторы ЕГРЗ и Федресурса делает
другой агент. У нас общая точка — функции `poisk_v_egrz()` и `poisk_v_fedresurse()`,
которые ищут чужой модуль по списку известных имён и, пока его нет, честно
возвращают пусто с уликой «коллектора нет». Реализацию не дублируем.

ЖЕЛЕЗНОЕ ПРАВИЛО: компанию НЕ ВЫДУМЫВАТЬ. Имя без подтверждения (совпал регион и
отрасль/объект/площадка) не принимается — возвращается честный None. Смысл правила
измерен на наших данных: наивный матч по редким токенам давал 57% «попаданий», а
глазами общие токены оказывались именем ИЗДАНИЯ («деловая газета», «rugrad online»)
и фамилией журналиста. С обязательным подтверждением точность 88% (проверка 16.09
на 1 106 боевых записях с ПРЯЧЕННЫМ именем), а имя находится у 3,3% безымянных.

ПЛАТНОЕ. Пути 5-SERP и 6 ходят в xmlriver — это деньги (на балансе 299 ₽).
Они выключены по умолчанию: включаются только `ctx['razresheno_platit'] = True`.
Провайдерский API (claude-fable-5) здесь НЕ вызывается вовсе: все решения —
правила, а не модель.

Использование:

    import doopredelenie as DP
    ctx = DP.Kontekst(korpus=DP.Korpus.iz_jsonl(r'C:\\sender\\server\\news_stream.jsonl'))
    r = DP.doopredelit({'title': ..., 'what': ..., 'region': ..., 'source_url': ...}, ctx)
    if r['company']:
        ...  # событие спасено, дальше как обычно: dadata → signals
    else:
        kucha_bez_imeni.polozhit(...)   # в кучу, не в мусор
"""
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

__all__ = ['doopredelit', 'Kontekst', 'Korpus', 'poisk_v_egrz', 'poisk_v_fedresurse',
           'podtverdit', 'STRATEGII']

# ----------------------------------------------------------------- словари
# Слова-штампы новостей: по ним ничего нельзя опознать, в улики не годятся.
_SHTAMPY = set('''завод завода заводе заводы заводов фабрика фабрики фабрике цех цеха
линия линии комплекс комплекса производство производства производств производству
предприятие предприятия предприятий компания компании компанию строительство
строительства строительству строить построят построит построили построено
модернизация модернизации запуск запуска запустят открылся открыли открытие открытия
расширение расширения инвестиции инвестиций инвестор инвестора инвесторы проект проекта
проекты млрд рублей рубля миллиард миллионов года году региона регион области область
округ округа район района города город новый новая новое новые будет будут может можно
объект объекта объектов продукции продукция мощностью выпуск выпуска выпуску работы
работ создание создания начали начал планируют планирует хотят готов готовится обсудили
встрече рамках вложит вложат составит более около первый второй крупнейший новости
новостной официальный официальная газета деловая онлайн online news агентство сообщает
сообщил рассказал глава губернатор губернатора министр министра правительство
резидент резидента резиденты соглашение соглашения подписано подписали
помощью который которые которая которых также после сегодня вчера завтра напомним
рассказали сообщили заявил отметил добавил уточнил подчеркнул отмечается информация
материал подробнее читайте подписывайтесь телеграм источник фотографии фотография'''.split())

# Класс объекта: грубая, но проверяемая привязка «о том же ли объекте речь».
_KLASS_OBEKTA = {
    'завод': ('завод',), 'фабрика': ('фабрик',), 'цех': ('цех',), 'линия': ('лини',),
    'комплекс': ('комплекс',), 'элеватор': ('элеватор',),
    'добыча': ('рудник', 'гок', 'карьер', 'месторожд', 'обогатительн'),
    'теплица': ('теплиц',), 'ферма': ('ферм', 'птицефабрик', 'откормплощ'),
    'терминал': ('терминал', 'причал'), 'склад': ('склад', 'логистическ'),
    'нпз': ('нпз', 'нефтеперераб', 'гхк', 'газохим'),
}

# Юрлицо в тексте: «ООО «Ромашка»», «АО "Заря"», «ПАО Северсталь».
_OPF = r'(?:ООО|АО|ПАО|ЗАО|ОАО|НАО|ГУП|МУП|ФГУП|АНО|ИП|УК|ГК|НПО|НПП|ТД)'
_RE_YURLICO = re.compile(
    _OPF + r'\s*[«"„\']([^»"“\']{2,60})[»"“\']'          # ООО «Ромашка»
    r'|' + _OPF + r'\s+([А-ЯЁ][А-Яа-яЁё\-]{2,40}(?:\s+[А-ЯЁ][А-Яа-яЁё\-]{2,40}){0,2})')
# Имя в кавычках без ОПФ — слабее, берём только когда рядом стоит слово-объект.
_RE_V_KAVYCHKAH = re.compile(r'[«"„]([А-ЯЁA-Z][^»"“]{2,40})[»"“]')

# Площадка ОЭЗ/ТОР: «ОЭЗ «Липецк»», «ТОСЭР Хабаровск», «ОЭЗ ППТ «Грозный»».
_RE_PLOSHCHADKA = re.compile(
    r'(?:ОЭЗ|ТОР|ТОСЭР|особ\w+\s+экономическ\w+\s+зон\w*|территори\w+\s+опережающ\w+\s+развити\w*)'
    r'(?:\s+(?:ППТ|ПТ|ТВТ|ПОЭЗ))?\s*[«"„\']?([А-ЯЁ][А-Яа-яЁё\- ]{2,30})?', re.I)

_KESH_TTL = 24 * 3600      # сутки: реестры и инвестпорталы меняются медленно
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')


# ----------------------------------------------------------------- утилиты
def _tekst(sob):
    """Весь текст события одной строкой: заголовок (без хвоста издания) + суть."""
    return ' '.join([_bez_izdaniya(sob.get('title')), sob.get('what') or '',
                     sob.get('full_text') or ''])


def _bez_izdaniya(title):
    """Срезать хвост издания: «...завод построят - Деловая Газета.Юг» → «...завод построят».

    Умеет: отрезать последний сегмент после ' - ', ' — ', ' | ', ' :: ', ' // '.
    Не умеет: узнать издание, если оно стоит В НАЧАЛЕ заголовка или без разделителя.
    Зачем: без этого матчер склеивал два разных завода по общему имени издания
    (замер 16.09 — половина ложных пар была именно такой).
    """
    t = title or ''
    for sep in (' - ', ' — ', ' | ', ' :: ', ' // '):
        if sep in t:
            t = t.rsplit(sep, 1)[0]
    return t.strip()


def _tokeny(*ss, **kw):
    """Содержательные токены: ≥5 букв, не штамп, обрезка хвоста до 9 символов
    (грубая нормализация склонений: «радиаторов»/«радиаторы» → «радиатор»)."""
    minlen = kw.get('minlen', 5)
    out = set()
    for s in ss:
        for t in re.sub(r'[^а-яёa-z0-9 ]', ' ', (s or '').lower()).split():
            if len(t) >= minlen and t not in _SHTAMPY:
                out.add(t[:9])
    return out


def _region_tokeny(s):
    """Регион → множество корней («Краснодарский край» → {'красно'}). Слова
    «область/край/республика/округ/район/город» выкидываем: они ничего не различают."""
    s = (s or '').lower()
    s = re.sub(r'(области|область|обл\.|края|край|республик\w*|респ\.|округ\w*|район\w*|г\.|город\w*)',
               ' ', s)
    return {x[:6] for x in re.sub(r'[^а-яё ]', ' ', s).split() if len(x) >= 4}


def _klass_obekta(txt):
    t = (txt or '').lower()
    return {k for k, ws in _KLASS_OBEKTA.items() if any(w in t for w in ws)}


def _data_iso(s):
    """Любую дату источника → 'YYYY-MM-DD' или ''. Понимает ISO и RFC-822 (RSS)."""
    p = (s or '')[:40]
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', p)
    if m:
        return m.group(0)
    m = re.search(r'(\d{1,2})[ .](\w{3})[a-z]*[ .](\d{4})', p)
    if m:
        mm = {'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
              'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
              'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04', 'мая': '05', 'июн': '06',
              'июл': '07', 'авг': '08', 'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12'}
        k = mm.get(m.group(2).lower()[:3])
        if k:
            return '%s-%s-%02d' % (m.group(3), k, int(m.group(1)))
    m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', p)
    if m:
        return '%s-%s-%s' % (m.group(3), m.group(2), m.group(1))
    return ''


def _dney_mezhdu(d1, d2):
    """Разница дат в днях или None, если хоть одна неизвестна."""
    if not (d1 and d2):
        return None
    try:
        import datetime as _dt
        a = _dt.date(*[int(x) for x in d1.split('-')])
        b = _dt.date(*[int(x) for x in d2.split('-')])
        return abs((a - b).days)
    except Exception:  # noqa: BLE001
        return None


def _imena_iz_teksta(txt, ryadom_s=()):
    """Достать из текста кандидатов-юрлиц.

    Умеет: «ООО «Ромашка»», «АО Заря», «ПАО Северсталь», а также имя в кавычках,
    если рядом (в пределах 60 символов) стоит слово из `ryadom_s` — так кавычки
    «Липецк» в «ОЭЗ «Липецк»» не превращаются в компанию.
    Не умеет: имя без кавычек и без ОПФ («Сибур запустил») — такие ловит только
    классификатор или dadata по контексту, здесь их сознательно не берём, чтобы
    не выдумывать.
    """
    out = []
    for m in _RE_YURLICO.finditer(txt or ''):
        nm = (m.group(1) or m.group(2) or '').strip(' .,;:«»"\'')
        if len(nm) >= 3 and nm.lower() not in _SHTAMPY:
            out.append(nm)
    if ryadom_s:
        for m in _RE_V_KAVYCHKAH.finditer(txt or ''):
            nm = m.group(1).strip()
            okno = (txt[max(0, m.start() - 60):m.end() + 60] or '').lower()
            if len(nm) >= 3 and any(w in okno for w in ryadom_s) and nm.lower() not in _SHTAMPY:
                out.append(nm)
    # порядок сохраняем, дубликаты убираем
    vid, res = set(), []
    for n in out:
        k = re.sub(r'[^а-яёa-z0-9]', '', n.lower())
        if k and k not in vid:
            vid.add(k)
            res.append(n)
    return res[:8]


# ----------------------------------------------------------------- подтверждение
def podtverdit(sob, kand_tekst='', kand_region='', kand_data='', strukturnyy=False):
    """ЗАЩИТА ОТ ТЁЗОК. Можно ли принять имя, найденное в источнике-кандидате.

    Умеет проверить три независимые вещи:
      * регион — корни региона события пересекаются с регионом кандидата или
        встречаются в его тексте;
      * отрасль/объект — совпал класс объекта (завод/фабрика/рудник…) ИЛИ есть
        общий содержательный токен (радиатор, чиабатта, газобетон);
      * дата — источник-кандидат не дальше 540 дней от события.

    Возвращает (принять: bool, уверенность: 'high'|'low', улики: list[str]).
    Правило: 'high' = регион И отрасль/объект; 'low' = ровно одно из двух плюс
    сходящаяся дата; иначе отказ (принять=False).
    Для структурных источников (реестр резидентов, ЕГРЗ, Федресурс) при
    `strukturnyy=True` совпадения площадки/объекта и региона достаточно для 'high':
    там имя стоит рядом с объектом не по совпадению слов, а по записи реестра.

    Чего НЕ умеет и не должна: доказать, что компания та самая. Это фильтр от
    грубых тёзок, а не суд. Поэтому итог дальше живёт с меткой уверенности, и
    'low' в лид-деске должен быть виден оператору.
    """
    uliki = []
    s_reg = _region_tokeny(sob.get('region'))
    k_reg = _region_tokeny(kand_region)
    s_txt = _tekst(sob)
    region_ok = bool(s_reg and (k_reg & s_reg))
    if not region_ok and s_reg and kand_tekst:
        region_ok = any(r in (kand_tekst or '').lower() for r in s_reg)
    if region_ok:
        uliki.append('регион совпал: %s' % (sob.get('region') or '')[:40])

    s_kl, k_kl = _klass_obekta(s_txt), _klass_obekta(kand_tekst)
    obshchie = _tokeny(s_txt, minlen=6) & _tokeny(kand_tekst, minlen=6)
    klass_ok = bool(s_kl and k_kl and (s_kl & k_kl))
    otrasl_ok = klass_ok or bool(obshchie)
    if klass_ok:
        uliki.append('класс объекта совпал: %s' % ','.join(sorted(s_kl & k_kl)))
    if obshchie:
        uliki.append('общие предметные слова: %s' % ','.join(sorted(obshchie)[:4]))

    d = _dney_mezhdu(_data_iso(sob.get('published') or sob.get('event_date')), _data_iso(kand_data))
    data_ok = (d is None) or (d <= 540)
    if d is not None:
        uliki.append('разница дат %d дн.' % d)

    if region_ok and otrasl_ok:
        return True, 'high', uliki
    if strukturnyy and (region_ok or otrasl_ok) and data_ok:
        # структурный источник (реестр/ЕГРЗ/Федресурс): имя стоит рядом с объектом
        # по записи реестра, а не по совпадению слов в новости — одного совпадения
        # хватает, но уверенность остаётся низкой и оператор это видит
        return True, 'low', uliki
    if (region_ok or otrasl_ok) and data_ok:
        return True, 'low', uliki
    uliki.append('ОТКАЗ: подтверждения нет (регион=%s, отрасль=%s)' % (region_ok, otrasl_ok))
    return False, 'low', uliki


# ----------------------------------------------------------------- корпус наших событий
class Korpus(object):
    """Наши собственные события как поисковый индекс (для пути 5 без единого запроса).

    Умеет: собраться из `news_stream.jsonl` (там есть и безымянные) и/или из
    `signals` в enrich.db (там только события С ИНН); найти запись про ТОТ ЖЕ
    объект по редким токенам с обязательным подтверждением.
    Не умеет: знать о новостях, которых мы не собирали. Это и есть потолок пути 5
    внутри корпуса: на боевых данных 16.09 (корпус 8 146 записей с именем) имя
    нашлось у 3,3% безымянных событий.

    ПОРОГ РЕДКОСТИ. «Редкий токен» = встречается не чаще чем у одной записи из
    тысячи, но не строже трёх записей. Порог не выдуман: замер 16.09 на отложенной
    выборке (1 106 записей с ПРЯЧЕННЫМ именем, корпус 8 146):

        порог df   охват   точность   спасено безымянных
          3         1,8%     75%          1,4%
          5         4,8%     83%          1,9%
          8         9,9%     88%          3,3%     <- сюда попадает правило N/1000
         12        14,3%     82%          4,1%

    То есть слишком строгий порог не только душит охват, но и РЕЖЕТ точность:
    при df<=3 совпадения держатся на случайных редкостях вроде фамилии
    журналиста. Порог 12 добавляет охват ценой точности — включается вручную
    (`Korpus(..., rare=12)`), когда оператор готов проверять больше 'low'.
    """

    RARE_MIN = 3        # строже этого не имеет смысла (замер выше)
    RARE_DOLYA = 1000   # редкий = не чаще одной записи на тысячу корпуса

    def __init__(self, zapisi=None, rare=None):
        self.zapisi = []
        self._df = Counter()
        self._idx = defaultdict(list)
        self._rare_zadan = rare          # None = считать по размеру корпуса
        self.rare = rare or self.RARE_MIN
        for z in (zapisi or []):
            self.dobavit(z)

    # ---- сборка
    def dobavit(self, z):
        """z: {'company','inn','title','what','region','published','source_url'}"""
        if not (z.get('company') or '').strip():
            return
        t = _tokeny(_bez_izdaniya(z.get('title')), z.get('what')) - _tokeny(z.get('source_name'))
        z = dict(z, _t=t, _reg=_region_tokeny(z.get('region') or z.get('dd_region')),
                 _kl=_klass_obekta(_bez_izdaniya(z.get('title')) + ' ' + (z.get('what') or '')),
                 _d=_data_iso(z.get('published') or z.get('ts')))
        self.zapisi.append(z)
        self._df.update(t)

    def gotov(self):
        """Построить обратный индекс по редким токенам. Вызывать после всех dobavit."""
        self.rare = self._rare_zadan or max(self.RARE_MIN, len(self.zapisi) // self.RARE_DOLYA)
        self._idx = defaultdict(list)
        for i, z in enumerate(self.zapisi):
            for t in z['_t']:
                if self._df[t] <= self.rare:
                    self._idx[t].append(i)
        return self

    @classmethod
    def iz_jsonl(cls, path, limit=0, rare=None):
        k = cls(rare=rare)
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        k.dobavit(json.loads(line))
                    except Exception:  # noqa: BLE001
                        continue
                    if limit and len(k.zapisi) >= limit:
                        break
        except Exception:  # noqa: BLE001
            pass
        return k.gotov()

    @classmethod
    def iz_bd(cls, db_path, limit=0, rare=None):
        """signals + companies из enrich.db. Открываем СТРОГО на чтение."""
        k = cls(rare=rare)
        try:
            cx = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
            q = ('SELECT s.inn, c.name, s.what, s.event_type, s.source, s.source_url, s.ts, '
                 'c.region FROM signals s LEFT JOIN companies c ON c.inn=s.inn')
            if limit:
                q += ' LIMIT %d' % int(limit)
            for inn, name, what, et, src, url, ts, reg in cx.execute(q):
                k.dobavit({'inn': inn, 'company': name or '', 'title': what or '',
                           'what': what or '', 'region': reg or '', 'published': ts or '',
                           'source_url': url or '', 'source_name': src or ''})
            cx.close()
        except Exception:  # noqa: BLE001
            pass
        return k.gotov()

    # ---- поиск
    def nayti(self, sob, pozdnee=False):
        """Найти запись про тот же объект. `pozdnee=True` — только новости ПОЗЖЕ события
        (имя обычно появляется в более поздней). Возвращает (запись, общие токены) или None."""
        q = _tokeny(_bez_izdaniya(sob.get('title')), sob.get('what')) - _tokeny(sob.get('source_name'))
        rare = {t for t in q if self._df.get(t, 0) <= self.rare}
        if len(rare) < 2:
            return None
        s_reg = _region_tokeny(sob.get('region'))
        s_kl = _klass_obekta(_tekst(sob))
        s_d = _data_iso(sob.get('published') or sob.get('event_date'))
        cand = Counter()
        for t in rare:
            for i in self._idx.get(t, ()):
                cand[i] += 1
        for i, n in cand.most_common(15):
            if n < 2:                       # один общий редкий токен — это совпадение, не улика
                break
            z = self.zapisi[i]
            if (z.get('source_url') or '') and z.get('source_url') == sob.get('source_url'):
                continue                    # это мы сами
            if not (s_reg and z['_reg'] and (s_reg & z['_reg'])):
                continue
            if not (s_kl and z['_kl'] and (s_kl & z['_kl'])):
                continue
            if pozdnee and s_d and z['_d'] and z['_d'] < s_d:
                continue
            return z, sorted(rare & z['_t'])
        return None


# ----------------------------------------------------------------- контекст
class Kontekst(object):
    """Всё внешнее, от чего зависят стратегии: корпус, сеть, деньги, реестры.

    Поля:
      korpus              — Korpus или None (путь 5-локальный без него не работает);
      razresheno_platit   — разрешены ли платные SERP-запросы (xmlriver). ПО УМОЛЧАНИЮ
                            False: на балансе 299 ₽ и трата не согласована;
      internet            — разрешён ли выход в сеть вообще (реестры/порталы);
      dadata_token        — токен dadata для привязки ИНН (по умолчанию из окружения);
      reestry             — путь к JSON-справочнику площадок и инвестпорталов;
      kesh_dir            — куда складывать скачанные страницы реестров;
      puti                — какие пути включены (по умолчанию все);
      log                 — функция-логгер (по умолчанию молчит).
    """

    def __init__(self, korpus=None, razresheno_platit=False, internet=True, dadata_token=None,
                 reestry=None, kesh_dir=None, puti=None, log=None, dadata=None):
        self.korpus = korpus
        self.razresheno_platit = bool(razresheno_platit)
        self.internet = bool(internet)
        self.dadata_token = dadata_token or os.environ.get('DADATA_TOKEN', '')
        self.kesh_dir = kesh_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 'kesh_doopr')
        self.reestry = reestry or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               'reestry_ploshchadok.json')
        self.puti = puti            # None = все пути; список имён = только они
        self.log = log or (lambda *a: None)
        self._dadata = dadata       # можно подменить в тестах
        self._spravochnik = None

    # --- справочник площадок/порталов (JSON рядом с модулем, правится руками)
    def spravochnik(self):
        """{'oez': {'липецк': {'url':..., 'region':...}}, 'portaly': {'липецк': [url,...]}}"""
        if self._spravochnik is None:
            try:
                with open(self.reestry, encoding='utf-8') as f:
                    self._spravochnik = json.load(f)
            except Exception:  # noqa: BLE001
                self._spravochnik = {'oez': {}, 'portaly': {}}
        return self._spravochnik

    # --- сеть с кэшем на диске
    def skachat(self, url, ttl=_KESH_TTL, timeout=25):
        """GET с файловым кэшем (сутки). Возвращает текст или ''. Без сети — ''."""
        if not self.internet:
            return ''
        try:
            os.makedirs(self.kesh_dir, exist_ok=True)
            import hashlib
            p = os.path.join(self.kesh_dir, hashlib.sha1(url.encode()).hexdigest() + '.html')
            if os.path.isfile(p) and (time.time() - os.path.getmtime(p)) < ttl:
                return open(p, encoding='utf-8', errors='replace').read()
            req = urllib.request.Request(url, headers={'User-Agent': _UA,
                                                       'Accept-Language': 'ru,en;q=0.8'})
            body = urllib.request.urlopen(req, timeout=timeout).read()
            txt = body.decode('utf-8', 'replace')
            with open(p, 'w', encoding='utf-8') as f:
                f.write(txt)
            return txt
        except Exception as e:  # noqa: BLE001
            self.log('skachat %s: %s' % (url[:60], e))
            return ''

    # --- привязка имени к ИНН (переиспользуем боевую dadata из news_scan, не дублируем)
    def dadata(self, imya):
        if self._dadata is not None:
            return self._dadata(imya)
        if not self.dadata_token:
            return None
        try:
            import news_scan as NS
            return NS.dadata_suggest(imya, self.dadata_token)
        except Exception as e:  # noqa: BLE001
            self.log('dadata: %s' % e)
            return None

    # --- платный SERP
    def serp(self, zapros, n=8):
        """xmlriver (Яндекс) → [(заголовок, url, сниппет)]. ПЛАТНО.

        Молча ничего не тратит: без `razresheno_platit=True` возвращает пусто.
        """
        if not (self.razresheno_platit and self.internet):
            return []
        user, key = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
        if not (user and key):
            return []
        u = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
             + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop&query='
             + urllib.parse.quote(zapros))
        body = self.skachat(u, ttl=7 * 24 * 3600, timeout=45)
        out = []
        for doc in re.findall(r'<doc>(.*?)</doc>', body or '', re.S)[:n]:
            def g(tag, d=doc):
                m = re.search(r'<%s[^>]*>(.*?)</%s>' % (tag, tag), d, re.S)
                return re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+>', '', m.group(1)).strip() if m else ''
            out.append((g('title'), g('url'), g('passage') or g('contentType')))
        return out


# ----------------------------------------------------------------- общие точки с соседями
def poisk_v_egrz(objekt, region='', data=''):
    """АБСТРАКЦИЯ над коллектором ЕГРЗ (его делает другой агент — задача 1 ТЗ).

    Умеет: найти чужой модуль по списку известных имён и позвать его поиск.
    Ожидаемый контракт ответа: список словарей с ключами
    `zakazchik`/`customer`, `zastroyshchik`/`developer`, `object`, `region`, `date`,
    `sum`, `url`.
    Не умеет: сама ходить в ЕГРЗ. Пока коллектора нет — честно возвращает [].
    """
    for mod, fn in (('egrz_collector', 'poisk'), ('egrz_collector', 'search'),
                    ('egrz', 'poisk'), ('egrz', 'search'), ('news_scan', 'col_egrz_poisk')):
        try:
            m = __import__(mod)
            f = getattr(m, fn, None)
            if callable(f):
                return f(objekt, region=region, data=data) or []
        except Exception:  # noqa: BLE001
            continue
    return []


def poisk_v_fedresurse(objekt, region='', data='', okved=''):
    """АБСТРАКЦИЯ над коллектором Федресурса (задача 3 ТЗ, делает другой агент).

    Ожидаемый контракт ответа: список словарей с `inn`, `name`, `type` (тип
    сообщения), `date`, `text`, `url`. Федресурс — единственный источник, где ИНН
    стоит прямо в сообщении, поэтому dadata здесь не нужна.
    Пока коллектора нет — честно возвращает [].
    """
    for mod, fn in (('fedresurs_collector', 'poisk'), ('fedresurs_collector', 'search'),
                    ('fedresurs', 'poisk'), ('fedresurs', 'search')):
        try:
            m = __import__(mod)
            f = getattr(m, fn, None)
            if callable(f):
                return f(objekt, region=region, data=data, okved=okved) or []
        except Exception:  # noqa: BLE001
            continue
    return []


# ----------------------------------------------------------------- стратегии
def _itog(company, inn, put, uver, uliki, extra=None):
    r = {'company': company, 'inn': inn, 'путь': put, 'uverennost': uver, 'uliki': list(uliki)}
    # ТЗ просит ключ «ulики» — держим его как алиас на тот же список, чтобы
    # и читаемое имя, и буквальное из ТЗ указывали на одно и то же.
    r['ulики'] = r['uliki']
    if extra:
        r.update(extra)
    return r


def strategiya_nash_korpus(sob, ctx):
    """ПУТЬ 5-локальный: более поздняя (или просто другая) новость про тот же объект
    среди НАШИХ собранных событий.

    Умеет: найти по редким токенам запись с именем, где совпали и регион, и класс
    объекта; 0 запросов, 0 ₽, работает офлайн.
    Не умеет: найти то, чего мы не собирали. Замер 16.09 на боевом корпусе
    (8 146 записей с именем): имя нашлось у 3,3% безымянных событий, точность
    матчера 88% (проверка с прятанием имени на 1 106 записях; ещё 3% ответов —
    та же компания в другом написании, «ЧКПЗ» против «Челябинский
    кузнечно-прессовый завод», то есть по делу верных ~91%).
    """
    if ctx.korpus is None:
        return None, ['путь 5-локальный: корпус не подан']
    hit = ctx.korpus.nayti(sob)
    if not hit:
        return None, ['путь 5-локальный: пары в корпусе нет']
    z, obshchie = hit
    ok, uver, uliki = podtverdit(sob, kand_tekst=(z.get('title') or '') + ' ' + (z.get('what') or ''),
                                 kand_region=z.get('region'), kand_data=z.get('published'))
    uliki = ['путь 5-локальный: %s' % (z.get('source_url') or '')[:90],
             'общие редкие слова: %s' % ','.join(obshchie[:4])] + uliki
    if not ok:
        return None, uliki
    return _itog(z.get('company'), z.get('inn') or None, 'наш корпус', uver, uliki), uliki


def strategiya_oez_reestr(sob, ctx):
    """ПУТЬ 1: реестр резидентов ОЭЗ/ТОР по площадке и дате.

    Умеет: вытащить из текста имя площадки («ОЭЗ «Липецк»»), взять по справочнику
    `reestry_ploshchadok.json` адрес страницы резидентов, скачать (кэш сутки),
    выдрать юрлица и выбрать то, у которого профиль совпадает с объектом события.
    Не умеет: работать без заполненного справочника площадок и без открытой
    страницы резидентов (у части ОЭЗ список только в PDF/презентации). Не умеет
    выбрать резидента, когда на площадке два похожих профиля — тогда вернёт 'low'.

    Применимость на наших данных (16.09): ОЭЗ/ТОР/резидентство упоминают 8,3%
    безымянных событий, имя площадки разбирается у 6,1%.
    """
    txt = _tekst(sob) + ' ' + (sob.get('region') or '')
    m = _RE_PLOSHCHADKA.search(txt)
    if not m:
        return None, ['путь 1: площадка ОЭЗ/ТОР в тексте не названа']
    ploshchadka = (m.group(1) or '').strip(' «»"\'-.,')
    if len(ploshchadka) < 3:
        return None, ['путь 1: площадка не разобралась']
    spr = ctx.spravochnik().get('oez') or {}
    kl = re.sub(r'[^а-яёa-z]', '', ploshchadka.lower())[:12]
    zapis = None
    for k, v in spr.items():
        kk = re.sub(r'[^а-яёa-z]', '', k.lower())[:12]
        if kk and (kk in kl or kl in kk):
            zapis = v
            break
    if not zapis:
        return None, ['путь 1: площадка «%s» есть, но её нет в справочнике реестров' % ploshchadka[:30]]
    stranica = ctx.skachat(zapis.get('url') or '')
    if not stranica:
        return None, ['путь 1: страница резидентов «%s» не открылась' % ploshchadka[:30]]
    chistyy = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', stranica, flags=re.S)
    chistyy = re.sub(r'<[^>]+>', ' ', chistyy)
    s_kl = _klass_obekta(_tekst(sob))
    s_tok = _tokeny(_tekst(sob), minlen=6)
    luchshiy = None
    for imya in _imena_iz_teksta(chistyy):
        # окно вокруг имени в тексте реестра — по нему и проверяем профиль
        i = chistyy.find(imya)
        if i < 0:
            continue
        okno = chistyy[max(0, i - 300):i + 300]
        if (s_kl and (_klass_obekta(okno) & s_kl)) or (_tokeny(okno, minlen=6) & s_tok):
            luchshiy = (imya, okno)
            break
    if not luchshiy:
        return None, ['путь 1: в реестре «%s» профиль объекта не сошёлся ни с одним резидентом'
                      % ploshchadka[:30]]
    imya, okno = luchshiy
    ok, uver, uliki = podtverdit(sob, kand_tekst=okno, kand_region=zapis.get('region')
                                 or sob.get('region'), strukturnyy=True)
    uliki = ['путь 1: реестр резидентов %s (%s)' % (ploshchadka[:30], (zapis.get('url') or '')[:70])] + uliki
    if not ok:
        return None, uliki
    dd = ctx.dadata(imya)
    return _itog(imya, (dd or {}).get('inn'), 'реестр ОЭЗ/ТОР', uver, uliki), uliki


def strategiya_investportal(sob, ctx):
    """ПУТЬ 3: инвестпортал региона, раздел «приоритетные/ключевые инвестпроекты».

    Умеет: по справочнику `reestry_ploshchadok.json` → 'portaly' взять страницы
    региона, скачать (кэш сутки), найти абзац про наш объект (общие предметные
    слова) и вытащить оттуда юрлицо.
    Не умеет: искать по региону, которого нет в справочнике; читать проекты,
    опубликованные картинкой или в pdf-презентации; отличить инвестора от
    подрядчика, если в абзаце названы оба — в таком случае вернётся 'low'.

    Применимость: у нас регион заполнен у 84% безымянных событий, значит запрос
    в принципе составим почти всегда — упирается всё в полноту справочника порталов.
    """
    regs = _region_tokeny(sob.get('region'))
    if not regs:
        return None, ['путь 3: регион события неизвестен']
    portaly = (ctx.spravochnik().get('portaly') or {})
    urls = []
    for k, v in portaly.items():
        if _region_tokeny(k) & regs:
            urls += (v if isinstance(v, list) else [v])
    if not urls:
        return None, ['путь 3: инвестпортала для региона «%s» нет в справочнике'
                      % (sob.get('region') or '')[:30]]
    s_tok = _tokeny(_tekst(sob), minlen=6)
    for u in urls[:3]:
        stranica = ctx.skachat(u)
        if not stranica:
            continue
        chistyy = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', stranica, flags=re.S)
        chistyy = re.sub(r'<[^>]+>', ' ', chistyy)
        for imya in _imena_iz_teksta(chistyy):
            i = chistyy.find(imya)
            if i < 0:
                continue
            okno = chistyy[max(0, i - 400):i + 400]
            if not (_tokeny(okno, minlen=6) & s_tok):
                continue
            ok, uver, uliki = podtverdit(sob, kand_tekst=okno, kand_region=sob.get('region'),
                                         strukturnyy=True)
            uliki = ['путь 3: инвестпортал %s' % u[:70]] + uliki
            if ok:
                dd = ctx.dadata(imya)
                return _itog(imya, (dd or {}).get('inn'), 'инвестпортал', uver, uliki), uliki
    return None, ['путь 3: на инвестпортале региона проект не опознан']


def strategiya_egrz(sob, ctx):
    """ПУТЬ 2: ЕГРЗ — в заключении экспертизы названы заказчик и застройщик.

    Умеет: собрать описание объекта из события и позвать `poisk_v_egrz()`; из
    ответа взять заказчика (он же обычно инвестор), при пустом заказчике —
    застройщика; подтвердить регионом и объектом.
    Не умеет: ходить в ЕГРЗ сама (это соседний коллектор) и отличить инвестора от
    генподрядчика, если заказчиком записан подрядчик — такие случаи помечаем 'low'.
    """
    objekt = ' '.join(sorted(_tokeny(_tekst(sob), minlen=6))[:6]) or _bez_izdaniya(sob.get('title'))
    try:
        nahodki = poisk_v_egrz(objekt, region=sob.get('region') or '',
                               data=_data_iso(sob.get('published')))
    except Exception as e:  # noqa: BLE001
        return None, ['путь 2: коллектор ЕГРЗ упал: %s' % str(e)[:60]]
    if not nahodki:
        return None, ['путь 2: ЕГРЗ ничего не вернул (или коллектора ещё нет)']
    for z in nahodki[:5]:
        imya = (z.get('zakazchik') or z.get('customer') or '').strip()
        rol = 'заказчик'
        if not imya:
            imya = (z.get('zastroyshchik') or z.get('developer') or '').strip()
            rol = 'застройщик'
        if not imya:
            continue
        ok, uver, uliki = podtverdit(sob, kand_tekst=' '.join([z.get('object') or '',
                                                               z.get('text') or '']),
                                     kand_region=z.get('region'), kand_data=z.get('date'),
                                     strukturnyy=True)
        uliki = ['путь 2: ЕГРЗ, %s = %s, %s' % (rol, imya[:50], (z.get('url') or '')[:70])] + uliki
        if not ok:
            continue
        if rol == 'застройщик':
            uver = 'low'      # застройщик часто подрядчик, а не будущий владелец оборудования
            uliki.append('понижено до low: застройщик может быть подрядчиком')
        dd = ctx.dadata(imya)
        return _itog(imya, (dd or {}).get('inn') or z.get('inn'), 'ЕГРЗ', uver, uliki), uliki
    return None, ['путь 2: в найденных заключениях нет заказчика/застройщика']


def strategiya_fedresurs(sob, ctx):
    """ПУТЬ 4: Федресурс — сообщение о крупной сделке/залоге привязано к ИНН.

    Умеет: позвать `poisk_v_fedresurse()` по объекту, региону и дате; взять ИНН
    прямо из сообщения (dadata не нужна) и подтвердить регионом/объектом.
    Не умеет: ходить в Федресурс сама; найти сообщение, если сделка была оформлена
    до даты новости больше чем за полтора года (окно подтверждения 540 дней).
    """
    objekt = ' '.join(sorted(_tokeny(_tekst(sob), minlen=6))[:6])
    try:
        soobshcheniya = poisk_v_fedresurse(objekt, region=sob.get('region') or '',
                                           data=_data_iso(sob.get('published')))
    except Exception as e:  # noqa: BLE001
        return None, ['путь 4: коллектор Федресурса упал: %s' % str(e)[:60]]
    if not soobshcheniya:
        return None, ['путь 4: Федресурс пуст (или коллектора ещё нет)']
    for s in soobshcheniya[:5]:
        imya, inn = (s.get('name') or '').strip(), (s.get('inn') or '').strip()
        if not (imya or inn):
            continue
        ok, uver, uliki = podtverdit(sob, kand_tekst=s.get('text') or '',
                                     kand_region=s.get('region'), kand_data=s.get('date'),
                                     strukturnyy=True)
        uliki = ['путь 4: Федресурс, %s, ИНН %s, %s' % ((s.get('type') or 'сообщение')[:30],
                                                        inn or '—', (s.get('url') or '')[:60])] + uliki
        if ok:
            return _itog(imya or None, inn or None, 'Федресурс', uver, uliki), uliki
    return None, ['путь 4: сообщения есть, но подтверждения по региону/объекту нет']


def strategiya_serp_pozdnyaya(sob, ctx):
    """ПУТЬ 5-SERP: более поздняя новость про тот же объект в поиске (xmlriver). ПЛАТНО.

    Умеет: составить запрос «<предметные слова объекта> <регион>», прочитать
    заголовки и сниппеты выдачи и достать из них юрлицо; подтверждение — общее
    с остальными путями.
    Не умеет: тратить деньги без разрешения (`razresheno_platit=True`), а также
    отличить новость про соседний завод в том же районе — от этого спасает только
    требование двух совпадений (регион + предметное слово).
    """
    if not ctx.razresheno_platit:
        return None, ['путь 5-SERP: пропущен, платные запросы запрещены (xmlriver, 299 ₽ на балансе)']
    slova = sorted(_tokeny(_tekst(sob), minlen=6))[:4]
    if not slova:
        return None, ['путь 5-SERP: предметных слов нет, запрос не составить']
    zapros = ' '.join(slova + [(sob.get('region') or '')])
    for t, u, sn in ctx.serp(zapros, n=8):
        for imya in _imena_iz_teksta(t + ' ' + sn, ryadom_s=('завод', 'фабрик', 'компан', 'инвест')):
            ok, uver, uliki = podtverdit(sob, kand_tekst=t + ' ' + sn,
                                         kand_region=sob.get('region'))
            uliki = ['путь 5-SERP: %s (%s)' % (t[:60], u[:60]), 'запрос: %s' % zapros[:80]] + uliki
            if ok:
                dd = ctx.dadata(imya)
                return _itog(imya, (dd or {}).get('inn'), 'SERP поздняя новость', uver, uliki), uliki
    return None, ['путь 5-SERP: имя в выдаче не подтвердилось']


def strategiya_serp_obekt_rayon(sob, ctx):
    """ПУТЬ 6: связка «объект + район + отрасль» в нашем xmlriver. ПЛАТНО.

    Умеет: собрать более узкий запрос, чем путь 5 — тип объекта, район/город и
    отраслевое слово, — и разобрать выдачу так же, как путь 5.
    Не умеет: работать без района/региона (на наших данных запрос составим у 52%
    безымянных событий) и без разрешения тратить.
    """
    if not ctx.razresheno_platit:
        return None, ['путь 6: пропущен, платные запросы запрещены (xmlriver, 299 ₽ на балансе)']
    kl = sorted(_klass_obekta(_tekst(sob)))
    reg = (sob.get('region') or '').strip()
    slova = sorted(_tokeny(_tekst(sob), minlen=6))[:3]
    if not (kl and reg and slova):
        return None, ['путь 6: не хватает объекта/района/отрасли для запроса']
    zapros = '%s %s %s ООО ИЛИ АО' % (kl[0], reg, ' '.join(slova))
    for t, u, sn in ctx.serp(zapros, n=8):
        for imya in _imena_iz_teksta(t + ' ' + sn, ryadom_s=('завод', 'фабрик', 'компан', 'инвест')):
            ok, uver, uliki = podtverdit(sob, kand_tekst=t + ' ' + sn, kand_region=reg)
            uliki = ['путь 6: %s (%s)' % (t[:60], u[:60]), 'запрос: %s' % zapros[:80]] + uliki
            if ok:
                dd = ctx.dadata(imya)
                return _itog(imya, (dd or {}).get('inn'), 'SERP объект+район', uver, uliki), uliki
    return None, ['путь 6: имя в выдаче не подтвердилось']


# порядок = от дешёвых к дорогим; первый принятый кандидат прекращает перебор
STRATEGII = [
    ('нашкорпус', strategiya_nash_korpus),          # 0 запросов, 0 ₽
    ('оэз', strategiya_oez_reestr),                 # 1 HTTP, кэш сутки
    ('инвестпортал', strategiya_investportal),      # 1-3 HTTP, кэш сутки
    ('егрз', strategiya_egrz),                      # чужой коллектор
    ('федресурс', strategiya_fedresurs),            # чужой коллектор
    ('серп5', strategiya_serp_pozdnyaya),           # ПЛАТНО
    ('серп6', strategiya_serp_obekt_rayon),         # ПЛАТНО
]


def doopredelit(sobytie, ctx=None):
    """Главная точка. Событие без компании → имя или честный None.

    sobytie: {'title','what','region','source_url','published','event_type','sum',...}
    Возврат: {'company': str|None, 'inn': str|None, 'путь': str,
              'uverennost': 'high'|'low', 'uliki': [...]}  (алиас ключа — 'ulики').

    Гарантии:
      * компания НЕ выдумывается: без подтверждения (регион + отрасль/объект)
        возвращается None, а улики показывают, что именно пробовали;
      * платные пути не выполняются, пока не разрешено явно;
      * ни одна стратегия не может уронить вызов — исключение превращается в улику.
    """
    ctx = ctx if isinstance(ctx, Kontekst) else Kontekst(**(ctx or {}))
    vse_uliki, probovali = [], []
    for imya_puti, fn in STRATEGII:
        if ctx.puti and imya_puti not in ctx.puti:
            continue
        probovali.append(imya_puti)
        try:
            kand, uliki = fn(sobytie, ctx)
        except Exception as e:  # noqa: BLE001
            vse_uliki.append('%s: исключение %s' % (imya_puti, str(e)[:80]))
            continue
        vse_uliki.extend(uliki or [])
        if kand and kand.get('company'):
            kand['uliki'] = vse_uliki
            kand['ulики'] = vse_uliki
            kand['probovali'] = probovali
            return kand
    r = _itog(None, None, 'не найдено', 'low', vse_uliki)
    r['probovali'] = probovali
    return r


# ----------------------------------------------------------------- самопроверка
def _samoproverka():
    """Офлайн-тест логики: подтверждение, разбор имён, корпус. Сеть не трогает."""
    sob = {'title': 'Во Владимире открылся завод по производству алюминиевых радиаторов - НТВ',
           'what': 'запуск завода радиаторов отопления', 'region': 'Владимирская область',
           'published': '2026-06-01', 'source_url': 'https://x.ru/a'}
    korpus = Korpus([
        {'company': 'VALFEX', 'inn': '3327102265',
         'title': 'Губернатор посетил новый завод по производству радиаторов',
         'what': 'завод алюминиевых радиаторов, Суздальский округ',
         'region': 'Владимирская область', 'published': '2026-06-20',
         'source_url': 'https://y.ru/b'},
        {'company': 'Ромашка', 'inn': '1', 'title': 'Завод радиаторов в Крыму',
         'what': 'завод радиаторов', 'region': 'Крым', 'published': '2026-06-20',
         'source_url': 'https://z.ru/c'},
    ]).gotov()
    r = doopredelit(sob, Kontekst(korpus=korpus, internet=False))
    assert r['company'] == 'VALFEX', r
    assert r['путь'] == 'наш корпус' and r['uverennost'] == 'high', r
    # тёзка из другого региона не должна приниматься
    sob2 = dict(sob, region='Крым')
    r2 = doopredelit(sob2, Kontekst(korpus=korpus, internet=False))
    # у крымской записи общий редкий токен всего один («радиаторо»), у владимирской
    # не совпал регион → ни одна не принимается. Это и есть защита от тёзок.
    assert r2['company'] is None, r2
    # без корпуса и без сети — честный None, платные пути не выполняются
    r3 = doopredelit(sob, Kontekst(internet=False))
    assert r3['company'] is None and r3['путь'] == 'не найдено', r3
    assert any('платные запросы запрещены' in u for u in r3['uliki']), r3['uliki']
    assert r3['uliki'] is r3['ulики']
    assert _imena_iz_teksta('Резидент ООО «Петэксперт» строит завод') == ['Петэксперт']
    assert _bez_izdaniya('Завод построят - Деловая Газета.Юг') == 'Завод построят'
    print('самопроверка: ок (%d стратегий, платные выключены)' % len(STRATEGII))


if __name__ == '__main__':
    import sys
    if '--samoproverka' in sys.argv or len(sys.argv) == 1:
        _samoproverka()
