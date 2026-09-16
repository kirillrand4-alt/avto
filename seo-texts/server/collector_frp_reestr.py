# -*- coding: utf-8 -*-
"""Коллектор «реестр займов ФРП» (Задача 2 из TZ-RANNEE-SOBYTIE.md).

ЧЕСТНО О ГЛАВНОМ (проверено на сервере 16.09.2026, см. COLLECTOR-FRP-REESTR.md):
публичного машиночитаемого реестра профинансированных проектов у ФРП БОЛЬШЕ НЕТ.
Старый реестр заёмщиков `frprf.ru/klienty/` (706 карточек, в sitemap до сих пор
лежат, lastmod 2020) сегодня отдаёт `301 -> https://frprf.ru` — раздел закрыт
целиком, вместе с картой проектов (`region_js` на главной больше не определён,
`/proekty-i-zayavki/statistika-zayavok/` = 404). JSON-ручки нет: сайт на Bitrix,
XHR под таблицей не существует, RSS тоже нет (все /rss/ = 404).

Поэтому «реестр» здесь ВОССТАНАВЛИВАЕТСЯ из единственного живого публичного
раскрытия ФРП — ленты пресс-центра, в которой Фонд объявляет КАЖДЫЙ заём
(одобрение набсовета и выдачу). Отличие от старого коллектора `col_frp` в
news_scan.py — не в источнике URL, а в том, что здесь лента берётся КАК РЕЕСТР:

  old col_frp                         | col_frp_reestr
  ------------------------------------|---------------------------------------
  одна страница ленты, без пагинации   | пагинация + штатный фильтр по датам
  ~6 ссылок за прогон                  | всё окно за N дней (проверено: 217/год)
  фильтр по словам в тексте ссылки     | фильтр «это заём» по заголовку+анонсу
  pubDate пустой                       | дата из карточки, ISO YYYY-MM-DD
  только title+link                    | заёмщик, сумма займа, регион, отрасль,
                                       | программа, стадия, budget_confirmed
  текст статьи качает потом конвейер   | full_text отдаётся сразу (без второго GET)

Формат item — как у остальных коллекторов news_scan: {title, link, pubDate,
source, tier, collector, query} + поля реестра: company_name, company_hint
(синоним для news_scan.enrich_ev), inn, sum, sum_rub, region, otrasl, program,
stage, stage_code, budget_confirmed=True, project_sum, full_text.

Только stdlib. Сеть — ТОЛЬКО чтение frprf.ru. Ничего не пишет на диск и в БД.
Запуск вручную:  python collector_frp_reestr.py [дней] [макс_items]
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

BASE = 'https://frprf.ru'
FEED = BASE + '/press-tsentr/novosti/'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
FULLTEXT_CAP = 6000          # столько же, сколько берёт news_scan.fetch_article
PER_PAGE = 6                 # карточек на странице ленты (шаблон Bitrix, не настраивается)
MAX_PAGES = 400              # страховка от бесконечной пагинации

# Системный SOCKS-прокси сервера режет часть хостов, а госсайты отдают
# Russian-Trusted-CA → как в news_scan: опенер в обход прокси + свой TLS-контекст.
_SSLCTX = ssl.create_default_context()
_SSLCTX.check_hostname = False
_SSLCTX.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                      urllib.request.HTTPSHandler(context=_SSLCTX))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):   # noqa: D102
        return None


_OPENER_NR = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPSHandler(context=_SSLCTX),
                                         _NoRedirect)

_MONTHS = {'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
           'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11,
           'декабря': 12}


def _get(url, timeout=25, tries=3, opener=None):
    """GET с ретраями. Возвращает (код, текст). Код -1 = сеть не дала ответа."""
    op = opener or _OPENER
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept': 'text/html,*/*', 'Accept-Language': 'ru,en;q=0.8'})
    for i in range(tries):
        try:
            r = op.open(req, timeout=timeout)
            return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read().decode('utf-8', 'replace')
            except Exception:                                # noqa: BLE001
                return e.code, ''
        except Exception:                                    # noqa: BLE001
            if i < tries - 1:
                time.sleep(1.2 * (i + 1))
    return -1, ''


def _txt(h):
    """HTML -> плоский текст (без script/style)."""
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h or '')
    h = re.sub(r'(?i)<br\s*/?>|</p>|</div>|</li>', '\n', h)
    h = re.sub(r'<[^>]+>', ' ', h)
    h = (h.replace('&nbsp;', ' ').replace('&laquo;', '«').replace('&raquo;', '»')
          .replace('&mdash;', '—').replace('&ndash;', '–').replace('&amp;', '&')
          .replace('&quot;', '"').replace('&#8381;', '₽').replace('&#37;', '%'))
    h = re.sub(r'[ \t ]+', ' ', h)
    return re.sub(r'\n{2,}', '\n', h).strip()


# --------------------------------------------------------------- лента как реестр
def _feed_url(d_from, d_to, page):
    """URL страницы ленты со штатным фильтром Bitrix по дате публикации.
    Проверено на сервере: фильтр реально режет выборку, пагинация PAGEN_1 работает."""
    q = {'set_filter': 'y',
         'arrFilter1_DATE_ACTIVE_FROM_1': d_from.strftime('%d.%m.%Y'),
         'arrFilter1_DATE_ACTIVE_FROM_2': d_to.strftime('%d.%m.%Y'),
         'PAGEN_1': str(page)}
    return FEED + '?' + urllib.parse.urlencode(q)


def _cards(html):
    """Карточки со страницы ленты: дата, ссылка, заголовок, анонс.

    ВНИМАНИЕ (грабли, стоившие двух прогонов): в шаблоне ФРП разметка
    `<a  href="...">` — ДВА пробела, и `<div` от `class=` отделён переносом
    строки. Любой регекс с одиночным пробелом молча даёт 0 карточек.
    """
    out = []
    for blk in re.split(r'class="item-news', html or '')[1:]:
        t = re.search(r'class="title"\s*>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not t:
            continue
        d = re.search(r'class="date"[^>]*>\s*([^<]{4,40}?)\s*<', blk)
        iso = ''
        if d:
            m = re.match(r'(\d{1,2})\s+([а-яё]+)\s+(\d{4})', d.group(1).strip(), re.I)
            if m:
                iso = '%s-%02d-%02d' % (m.group(3), _MONTHS.get(m.group(2).lower(), 0),
                                        int(m.group(1)))
        a = re.search(r'</div>\s*<p>\s*(.*?)\s*</p>', blk, re.S)
        out.append({'date': iso,
                    'link': BASE + t.group(1) if t.group(1).startswith('/') else t.group(1),
                    'title': _txt(t.group(2)).replace('\n', ' ').strip(),
                    'anons': _txt(a.group(1)).replace('\n', ' ').strip() if a else ''})
    return out


def _walk_feed(days, cap, verbose=False):
    """Обход ленты за окно дней. Стоп: кончились новые ссылки / упёрлись в cap /
    дата ушла за окно. Дедуп по ссылке (пагинация Bitrix любит повторять хвост)."""
    d_to = date.today()
    d_from = d_to - timedelta(days=max(1, int(days)))
    seen, res = set(), []
    for page in range(1, MAX_PAGES + 1):
        code, html = _get(_feed_url(d_from, d_to, page))
        if code != 200 or not html:
            if verbose:
                print(f'  стр.{page}: код {code} — стоп', file=sys.stderr)
            break
        cc = _cards(html)
        new = [c for c in cc if c['link'] not in seen]
        if verbose:
            print(f'  стр.{page}: карточек {len(cc)}, новых {len(new)}', file=sys.stderr)
        if not new:
            break
        for c in new:
            seen.add(c['link'])
            # Bitrix при PAGEN за пределами диапазона отдаёт первую страницу —
            # ловим это по дате: старше окна ничего быть не должно.
            if c['date'] and c['date'] < d_from.isoformat():
                continue
            res.append(c)
        if len(res) >= cap * 3:      # запас: часть карточек отсеется как «не заём»
            break
    return res


# --------------------------------------------------------------- «это заём?»
# Заём = подтверждённый бюджет. Ловим и одобрение набсовета (самая ранняя стадия),
# и выдачу, и «открыли цех благодаря займу» (поздняя, но с подтверждённой суммой).
_LOAN_RE = re.compile(
    r'за[ёе]м|займ|льготн\w*\s+финансир|ФРП\s+(?:предостав|профинанс|одобр|выдел|вложи)|'
    r'одобрил\w*\s+(?:финансирование|заявк)|получит\w*\s+финансирование|'
    r'профинансир|благодаря\s+ФРП', re.I)
# Не заём: анонсы конференций, кадровые, рейтинги, разъяснения программ.
_NOT_LOAN_RE = re.compile(
    r'вебинар|конференц|форум\b|выставк|семинар|пресс-конференц|назначен|возглавил|'
    r'вакансі|итоги года|рейтинг|опрос|поздравля|день рожден|конкурс\b', re.I)

# Программы займов ФРП — они пишутся в кавычках и их НЕЛЬЗЯ принять за имя заёмщика.
_PROGRAMS = ('Проекты развития', 'Комплектующие изделия', 'Производительность труда',
             'Автокомпоненты', 'Маркировка товаров', 'Приоритетные проекты',
             'Лизинг', 'Лизинг судов', 'Противодействие эпидемическим заболеваниям',
             'Цифровизация промышленности', 'Формирование компонентной базы',
             'Проекты лесной промышленности', 'Деревообработка', 'Экотехнопарк',
             'Производительность труда и поддержка занятости', 'Станкостроение')
_NOT_COMPANY = re.compile(
    r'^(?:' + '|'.join(re.escape(p) for p in _PROGRAMS) + r')$|'
    r'фонд развития промышленности|^ФРП$|ВЭБ|Минпромторг|Правительств|'
    r'нацпроект|Эффективн|Промышленн\w* ипотек', re.I)


def _is_loan(c):
    s = (c.get('title') or '') + ' ' + (c.get('anons') or '')
    return bool(_LOAN_RE.search(s)) and not _NOT_LOAN_RE.search(s)


# --------------------------------------------------------------- разбор карточки
def _detail_text(url):
    """Текст релиза: всё между <h1> и блоком «поделиться/читайте также»."""
    code, html = _get(url)
    if code != 200 or not html:
        return '', code
    m = re.search(r'<h1[^>]*>(.*?)</h1>(.*?)'
                  r'(?:<div[^>]*class="[^"]*(?:share|also|similar|tags)|<footer|</main>|$)',
                  html, re.S)
    body = _txt(m.group(2)) if m else _txt(html)
    # хвост шаблона (меню/подвал), если h1-якорь не сработал
    body = re.split(r'Читайте также|Поделиться|Подать заявку\s*Личный кабинет', body)[0]
    return body.strip(), code


_SUM_RE = re.compile(r'(\d[\d\s  .,]{0,12}?)\s*(млн|млрд|миллион\w*|миллиард\w*)\s*'
                     r'(?:руб\w*|₽)?', re.I)


def _to_rub(num, unit):
    try:
        v = float(re.sub(r'[\s ]', '', num).replace(',', '.'))
    except Exception:                                        # noqa: BLE001
        return 0
    mult = 1_000_000_000 if unit.lower().startswith(('млрд', 'миллиард')) else 1_000_000
    return int(v * mult)


_LOAN_CTX = re.compile(r'за[ёе]м|займ|ФРП|Фонд\w*\s+развития\s+промышленности|'
                       r'льготн\w*\s+финансир|федеральн\w*\s+[Фф]онд|профинансир', re.I)
_PROJ_CTX = re.compile(r'инвестиц|стоимост\w*\s+проект|общ\w*\s+(?:бюджет|стоимост)|'
                       r'вложени|вложил|вложит|объ[ёе]м\w*\s+инвестиц', re.I)


def _find_sum(text):
    """Сумма ИМЕННО займа ФРП (а не всей стройки) + отдельно бюджет проекта.

    Разбор ПОПРЕДЛОЖЕННО, а не «окном вокруг числа»: типичный релиз ФРП звучит
    как «Инвестиции составили 150 млн рублей. Из них 72 млн предоставил ФРП» —
    при окне ±140 символов слово ФРП дотягивалось до чужого числа и 150 млн
    уезжали в сумму займа. Внутри предложения ещё раз смотрим 45 символов слева
    от числа: они отличают «общий бюджет — 150 млн» от «заём — 72 млн», когда
    обе цифры стоят в одной фразе.

    Если ни одного «займового» числа нет — sum остаётся ПУСТЫМ (лучше пусто,
    чем стоимость стройки, выданная за подтверждённый бюджет).
    """
    loan, proj = [], []
    for sent in re.split(r'(?<=[.!?;])\s+|\n+', text or ''):
        s_loan, s_proj = bool(_LOAN_CTX.search(sent)), bool(_PROJ_CTX.search(sent))
        if not (s_loan or s_proj):
            continue
        for m in _SUM_RE.finditer(sent):
            rub = _to_rub(m.group(1), m.group(2))
            if not rub:
                continue
            human = '%s %s ₽' % (
                re.sub(r'[\s ]+', ' ', m.group(1)).strip(),
                'млрд' if m.group(2).lower().startswith(('млрд', 'миллиард')) else 'млн')
            left = sent[max(0, m.start() - 45):m.start()]
            if _PROJ_CTX.search(left):
                proj.append((rub, human))
            elif _LOAN_CTX.search(left) or (s_loan and not s_proj):
                loan.append((rub, human))
            elif s_proj:
                proj.append((rub, human))
    # из нескольких «займовых» чисел берём максимальное: обычно это общая сумма
    # займа, а меньшие — доли федерального и регионального фондов
    s_loan = max(loan)[1] if loan else ''
    rub_loan = max(loan)[0] if loan else 0
    s_proj = max(proj)[1] if proj else ''
    return s_loan, rub_loan, s_proj


_OPF = r'(?:ООО|ОАО|ПАО|АО|ЗАО|НАО|АНО|ГК|НПО|НПП|НПЦ|ПКФ|ТД|УК)'
_COMPANY_PATTERNS = (
    re.compile(r'\b(' + _OPF + r')\s*«([^»]{2,80})»'),
    re.compile(r'(?:компания|предприятие|завод|фабрика|комбинат|производител\w*|'
               r'холдинг|группа\s+компаний|фирма|разработчик|изготовител\w*)\s+«([^»]{2,80})»',
               re.I),
    re.compile(r'«([^»]{2,80})»\s+(?:получил\w*|направит|вложит|запустил\w*|открыл\w*|'
               r'построил\w*|модернизир\w*|расширил\w*|приобрел\w*|инвестир\w*)', re.I),
)


def _find_company(title, text):
    """Заёмщик в ИМЕНИТЕЛЬНОМ падеже (как в ЕГРЮЛ): ОПФ + ядро из кавычек.

    В русском тексте склоняется существительное ПЕРЕД кавычками («на заводе
    „Прогресс“»), а само ядро в кавычках остаётся именительным — поэтому ядро
    берём как есть, а ОПФ подставляем найденный. Программы займа тоже пишутся в
    кавычках — они отсекаются через _NOT_COMPANY.
    """
    src = (title or '') + '\n' + (text or '')
    for i, pat in enumerate(_COMPANY_PATTERNS):
        for m in pat.finditer(src):
            if i == 0:
                opf, core = m.group(1), m.group(2).strip()
                name = '%s «%s»' % (opf.upper(), core)
            else:
                core = m.group(1).strip()
                name = core
            if _NOT_COMPANY.search(core) or _NOT_COMPANY.search(name):
                continue
            if len(core) < 2 or core.lower() in ('труба в трубе',):
                continue
            return name
    return ''


_INN_RE = re.compile(r'ИНН[\s:]*([0-9]{10}|[0-9]{12})')


def _inn_ok(inn):
    """Контрольная сумма ИНН (в релизах ИНН почти не встречается, но если есть —
    проверяем, чтобы не тащить в базу набор цифр из телефона/КПП)."""
    d = [int(x) for x in inn]
    if len(d) == 10:
        k = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return d[9] == sum(a * b for a, b in zip(k, d[:9])) % 11 % 10
    if len(d) == 12:
        k1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        k2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        return (d[10] == sum(a * b for a, b in zip(k1, d[:10])) % 11 % 10
                and d[11] == sum(a * b for a, b in zip(k2, d[:11])) % 11 % 10)
    return False


def _find_inn(text):
    for m in _INN_RE.finditer(text or ''):
        if _inn_ok(m.group(1)):
            return m.group(1)
    return ''


# регион: сначала субъекты (в т.ч. прилагательные), потом крупные города
_REGIONS = [
    (r'Москов\w*\s+област|Подмосков', 'Московская область'),
    (r'Ленинградск\w*\s+област', 'Ленинградская область'),
    (r'\bМоскв', 'Москва'),
    (r'Санкт-Петербург|Петербург', 'Санкт-Петербург'),
    (r'Севастопол', 'Севастополь'), (r'\bКрым', 'Республика Крым'),
    (r'Татарстан|Казан|Набережн\w*\s+Челн|Альметьевск|Нижнекамск', 'Республика Татарстан'),
    (r'Башкортостан|Башкири|\bУф[аеы]\b|Стерлитамак|Салават', 'Республика Башкортостан'),
    (r'Чуваш|Чебоксар|Новочебоксарск', 'Чувашская Республика'),
    (r'Удмурт|Ижевск|Сарапул|Воткинск', 'Удмуртская Республика'),
    (r'Мордови|Саранск', 'Республика Мордовия'),
    (r'Марий\s*Эл|Йошкар-Ол', 'Республика Марий Эл'),
    (r'Коми\b|Сыктывкар|Ухт[аы]', 'Республика Коми'),
    (r'Карели|Петрозаводск|Кондопог', 'Республика Карелия'),
    (r'Дагестан|Махачкал|Каспийск|Дербент', 'Республика Дагестан'),
    (r'Чечн|Чеченск|Грозн', 'Чеченская Республика'),
    (r'Кабардино|Нальчик', 'Кабардино-Балкарская Республика'),
    (r'Осети|Владикавказ', 'Республика Северная Осетия — Алания'),
    (r'Ингушет|Магас|Назран', 'Республика Ингушетия'),
    (r'Карачаево|Черкесск', 'Карачаево-Черкесская Республика'),
    (r'Адыге|Майкоп', 'Республика Адыгея'),
    (r'Калмык|Элист', 'Республика Калмыкия'),
    (r'Буряти|Улан-Удэ', 'Республика Бурятия'),
    (r'Якути|Саха\b|Якутск', 'Республика Саха (Якутия)'),
    (r'Тыв[аеы]\b|Тува|Кызыл', 'Республика Тыва'),
    (r'Хакаси|Абакан|Саяногорск', 'Республика Хакасия'),
    (r'Алта[йя]ск\w*\s+кра|Барнаул|Бийск|Рубцовск', 'Алтайский край'),
    (r'Республик\w*\s+Алтай|Горно-Алтайск', 'Республика Алтай'),
    (r'Краснодарск|Кубан|Краснодар|Сочи|Новороссийск|Армавир', 'Краснодарский край'),
    (r'Ставропольск|Ставропол|Невинномысск|Пятигорск', 'Ставропольский край'),
    (r'Пермск\w*\s+кра|\bПерм[ьи]\b|Березник|Соликамск|Чайковск', 'Пермский край'),
    (r'Красноярск', 'Красноярский край'),
    (r'Приморск\w*\s+кра|Владивосток|Артём|Находк', 'Приморский край'),
    (r'Хабаровск|Комсомольск-на-Амуре', 'Хабаровский край'),
    (r'Забайкал|Чит[аеы]\b', 'Забайкальский край'),
    (r'Камчат|Петропавловск-Камчатск', 'Камчатский край'),
    (r'Свердловск|Екатеринбург|Нижн\w*\s+Тагил|Каменск-Уральск|Первоуральск|Верхн\w*\s+Пышм',
     'Свердловская область'),
    (r'Челябинск|Магнитогорск|Миасс|Златоуст|Копейск', 'Челябинская область'),
    (r'Нижегородск|Нижн\w*\s+Новгород|Дзержинск|Арзамас|Выкс', 'Нижегородская область'),
    (r'Новосибирск|Бердск', 'Новосибирская область'),
    (r'Самарск|Самар[аеы]\b|Тольятти|Новокуйбышевск|Сызран', 'Самарская область'),
    (r'Ростовск|Ростов-на-Дону|Таганрог|Волгодонск|Шахт[ыа]\b', 'Ростовская область'),
    (r'Воронежск|Воронеж|Лиск', 'Воронежская область'),
    (r'Волгоградск|Волгоград|Волжск(?:ий|ом)|Камышин', 'Волгоградская область'),
    (r'Саратовск|Саратов|Энгельс|Балаков', 'Саратовская область'),
    (r'Тульск|\bТул[аеы]\b|Новомосковск|Алекси', 'Тульская область'),
    (r'Калужск|Калуг|Обнинск|Людинов', 'Калужская область'),
    (r'Рязанск|Рязан', 'Рязанская область'),
    (r'Ярославск|Ярославл|Рыбинск|Тутаев', 'Ярославская область'),
    (r'Ивановск|Иванов[оа]\b|Кинешм|Шуя\b', 'Ивановская область'),
    (r'Владимирск|Владимир|Ковров|Муром|Гусь-Хрустальн|Александров',
     'Владимирская область'),
    (r'Тверск|\bТвер[ьи]\b|Ржев|Конаков', 'Тверская область'),
    (r'Липецк|Елец', 'Липецкая область'),
    (r'Белгородск|Белгород|Стар\w*\s+Оскол|Губкин', 'Белгородская область'),
    (r'Курск', 'Курская область'),
    (r'Брянск', 'Брянская область'),
    (r'Смоленск|Вязьм|Сафонов', 'Смоленская область'),
    (r'Псковск|Псков|Велик\w*\s+Лук', 'Псковская область'),
    (r'Новгородск|Велик\w*\s+Новгород|Борович', 'Новгородская область'),
    (r'Вологодск|Вологд|Череповец', 'Вологодская область'),
    (r'Архангельск|Северодвинск|Котлас', 'Архангельская область'),
    (r'Мурманск|Апатит|Мончегорск', 'Мурманская область'),
    (r'Калининградск|Калининград|Советск|Гусев', 'Калининградская область'),
    (r'Кировск\w*\s+област|\bКиров[еа]?\b|Кирово-Чепецк|Слободск', 'Кировская область'),
    (r'Костромск|Костром|Шарь', 'Костромская область'),
    (r'Орловск|\bОрл[ае]\b|\bОрёл\b|\bОрел\b|Мценск', 'Орловская область'),
    (r'Тамбовск|Тамбов|Мичуринск|Котовск', 'Тамбовская область'),
    (r'Пензенск|Пенз|Кузнецк', 'Пензенская область'),
    (r'Ульяновск|Димитровград', 'Ульяновская область'),
    (r'Оренбургск|Оренбург|Орск|Новотроицк|Бузулук', 'Оренбургская область'),
    (r'Тюменск|Тюмен|Тобольск|Ишим', 'Тюменская область'),
    (r'Ханты-Мансийск|ХМАО|Сургут|Нижневартовск|Нефтеюганск',
     'Ханты-Мансийский автономный округ — Югра'),
    (r'Ямало-Ненецк|ЯНАО|Ноябрьск|Новый\s+Уренгой|Салехард',
     'Ямало-Ненецкий автономный округ'),
    (r'Курганск|Курган|Шадринск', 'Курганская область'),
    (r'Омск', 'Омская область'),
    (r'Томск|Северск', 'Томская область'),
    (r'Кемеровск|Кузбасс|Кемеров|Новокузнецк|Ленинск-Кузнецк', 'Кемеровская область'),
    (r'Иркутск|Ангарск|Братск|Усолье', 'Иркутская область'),
    (r'Амурск\w*\s+област|Благовещенск|Свободн\w*\b', 'Амурская область'),
    (r'Сахалинск|Сахалин|Южно-Сахалинск', 'Сахалинская область'),
    (r'Магаданск|Магадан', 'Магаданская область'),
    (r'Еврейск\w*\s+автоном|Биробиджан', 'Еврейская автономная область'),
    (r'Чукот|Анадыр', 'Чукотский автономный округ'),
    (r'Астраханск|Астрахан', 'Астраханская область'),
    (r'Ненецк\w*\s+автоном|Нарьян-Мар', 'Ненецкий автономный округ'),
    (r'Донецк|ДНР\b', 'Донецкая Народная Республика'),
    (r'Луганск|ЛНР\b', 'Луганская Народная Республика'),
    (r'Запорожск', 'Запорожская область'),
    (r'Херсонск', 'Херсонская область'),
]
_REGIONS = [(re.compile(p, re.I), n) for p, n in _REGIONS]


def _find_region(title, text):
    src = (title or '') + '\n' + (text or '')[:2500]
    for pat, name in _REGIONS:
        if pat.search(src):
            return name
    return ''


# отрасль: грубый словарь по тексту релиза (нужен для отбора КЦ/Meyer ещё до ОКВЭД)
_OTRASL = [
    (r'фотосепаратор|сортировк\w*\s+зерн|зернов|элеватор|мукомол|крупян', 'АПК и переработка зерна'),
    (r'пищев|продукт\w*\s+питания|молочн|мясн|кондитерск|хлебопекарн|напитк|консерв',
     'Пищевая промышленность'),
    (r'фармацевт|лекарствен|медиздели|медицинск\w*\s+издели', 'Фармацевтика и медизделия'),
    (r'станк|станкостроен|обрабатывающ\w*\s+центр|инструментальн', 'Станкостроение'),
    (r'машиностро|насос|компрессор|редуктор|подшипник|арматур\w*\s+(?:трубопровод|запорн)',
     'Машиностроение'),
    (r'автокомпонент|автомобильн|автопром', 'Автопром и автокомпоненты'),
    (r'нефтегаз|нефтедобыч|нефтехим|буров', 'Нефтегаз и нефтехимия'),
    (r'химическ|полимер|пластик|лакокрасоч|удобрени', 'Химия и полимеры'),
    (r'металлург|металлообработ|прокат|литейн|сталелитейн|трубн', 'Металлургия и металлообработка'),
    (r'электрон|микроэлектрон|радиоэлектрон|печатн\w*\s+плат', 'Электроника'),
    (r'электротехн|кабел|трансформатор|электродвигател', 'Электротехника'),
    (r'стройматериал|цемент|кирпич|бетон|утеплител|сухи\w*\s+смес', 'Стройматериалы'),
    (r'деревообработ|пиломатериал|фанер|ЦБК|целлюлоз|лесн\w*\s+промышленн', 'Лесопереработка'),
    (r'текстил|швейн|трикотаж|обувн|ткан', 'Лёгкая промышленность'),
    (r'упаковк|тар[аыу]\b|гофрокартон|этикет', 'Упаковка'),
    (r'судостро|верф', 'Судостроение'),
    (r'авиа|двигател\w*\s+для\s+самол|беспилотн', 'Авиация и БПЛА'),
    (r'мебел', 'Мебельное производство'),
    (r'перерабо\w*\s+отход|вторсырь|ТКО\b|рециклин', 'Переработка отходов'),
]
_OTRASL = [(re.compile(p, re.I), n) for p, n in _OTRASL]


def _find_otrasl(title, text):
    src = (title or '') + '\n' + (text or '')[:3000]
    for pat, name in _OTRASL:
        if pat.search(src):
            return name
    return ''


def _find_program(text):
    for p in _PROGRAMS:
        if re.search(r'«\s*' + re.escape(p), text or '', re.I):
            return p
    return ''


# стадия проекта (нумерация как в Задаче 5 ТЗ: 1 проект / 2 стройка / 3 пуск / 4 расширение)
def _find_stage(title, text):
    src = (title or '') + ' ' + (text or '')[:900]
    if re.search(r'одобрил|одобрен|предостав\w*\s+за[ёе]м|получит\s+за[ёе]м|направит\s+на|'
                 r'профинансир\w*\s+(?:создани|запуск|строительств)|выделит', src, re.I) \
            and not re.search(r'открыл|запустил|ввел|введ[её]н', src, re.I):
        return 'финансирование одобрено', 1
    if re.search(r'начал\w*\s+строительств|строит\w*\s+(?:завод|цех|корпус)|возводит', src, re.I):
        return 'строительство', 2
    if re.search(r'открыл|запустил|ввел\w*\s+в\s+эксплуатац|введ[её]н|заработал', src, re.I):
        return 'запуск', 3
    if re.search(r'расширил|увеличил\w*\s+выпуск|модернизир|нарастил', src, re.I):
        return 'расширение', 4
    return 'финансирование одобрено', 1


# --------------------------------------------------------------- публичная ручка
def registry_alive(timeout=15):
    """Проверка: не вернул ли ФРП старый реестр заёмщиков /klienty/ обратно.

    Сегодня отдаёт 301 на главную. Если когда-нибудь снова начнёт отдавать 200 с
    карточками — коллектор надо переключать на него (там были ОКВЭД, сумма,
    программа и срок в виде полей, а не текстом). Вызывается из __main__.
    """
    code, _ = _get(BASE + '/klienty/', timeout=timeout, tries=1, opener=_OPENER_NR)
    return {'url': BASE + '/klienty/', 'code': code, 'alive': code == 200}


def col_frp_reestr(days=None, max_items=200, workers=6, verbose=False, with_detail=True):
    """Реестр займов ФРП за последние `days` дней (по умолчанию 90).

    Возвращает list[dict] в формате коллекторов news_scan:
      обязательные: title, link, pubDate, source, tier, collector, query
      реестровые:   company_name, company_hint, inn, sum, sum_rub, region,
                    otrasl, program, stage, stage_code, budget_confirmed,
                    project_sum, full_text, article_chars
    """
    days = int(days or 90)
    cap = int(max_items or 200)
    cards = _walk_feed(days, cap, verbose=verbose)
    loans = [c for c in cards if _is_loan(c)][:cap]
    if verbose:
        print(f'  лента: {len(cards)} новостей, из них про займы {len(loans)}', file=sys.stderr)

    def build(c):
        body, code = (_detail_text(c['link']) if with_detail else ('', 0))
        text = body or ((c.get('title') or '') + ' ' + (c.get('anons') or ''))
        s, rub, proj = _find_sum(text)
        stage, stage_code = _find_stage(c['title'], text)
        name = _find_company(c['title'], text)
        it = {
            # --- контракт коллектора news_scan
            'title': c['title'],
            'link': c['link'],
            'pubDate': c['date'],                 # ISO YYYY-MM-DD (задача 6 ТЗ)
            'source': 'ФРП',                      # как у старого col_frp — чтобы не плодить источник
            'tier': 2,
            'collector': 'frp_reestr',
            'query': 'реестр займов ФРП (пресс-центр)',
            # --- реестровые поля
            'company_name': name,
            'company_hint': name,                 # это поле news_scan берёт как фолбэк компании
            'inn': _find_inn(text),
            'sum': s,
            'sum_rub': rub,
            'project_sum': proj,
            'region': _find_region(c['title'], text),
            'otrasl': _find_otrasl(c['title'], text),
            'program': _find_program(text),
            'stage': stage,
            'stage_code': stage_code,
            'budget_confirmed': True,             # заём = бюджет подтверждён (lead_scoring)
            'anons': c.get('anons', ''),
            'detail_code': code,
        }
        if body:
            it['full_text'] = (c['title'] + '\n\n' + body)[:FULLTEXT_CAP]
            it['article_chars'] = len(body)
        return it

    if with_detail and loans:
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
            out = list(ex.map(build, loans))
    else:
        out = [build(c) for c in loans]
    return out


def _summary(items):
    """Короткая сводка прогона (для ручного запуска и для отчётов)."""
    def cnt(key):
        return sum(1 for i in items if i.get(key))
    stages = {}
    for i in items:
        stages[i.get('stage') or '?'] = stages.get(i.get('stage') or '?', 0) + 1
    return {'items': len(items),
            'с компанией': cnt('company_name'), 'с суммой': cnt('sum'),
            'с регионом': cnt('region'), 'с отраслью': cnt('otrasl'),
            'с программой': cnt('program'), 'с ИНН': cnt('inn'),
            'сумма займов, млрд ₽': round(sum(i.get('sum_rub') or 0 for i in items) / 1e9, 2),
            'стадии': stages,
            'даты': (min((i['pubDate'] for i in items if i.get('pubDate')), default=''),
                     max((i['pubDate'] for i in items if i.get('pubDate')), default=''))}


if __name__ == '__main__':
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    t0 = time.time()
    print('старый реестр /klienty/: %s' % json.dumps(registry_alive(), ensure_ascii=False),
          file=sys.stderr)
    res = col_frp_reestr(days=d, max_items=n, verbose=True)
    out = os.environ.get('FRP_OUT', '')
    if out:                                   # файл только если попросили явно
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    for i in res[:10]:
        print(json.dumps({k: i.get(k) for k in
                          ('pubDate', 'company_name', 'sum', 'region', 'otrasl',
                           'program', 'stage', 'title')},
                         ensure_ascii=False))
    print(json.dumps({'сводка': _summary(res), 'сек': round(time.time() - t0, 1)},
                     ensure_ascii=False, indent=1))
