# -*- coding: utf-8 -*-
"""Нормализация даты события: единое поле ISO и ОТКУДА эта дата взята.

ПОЧЕМУ ЭТО НУЖНО. В signals дата лежит в поле `ts` в том виде, в каком её отдал источник:
«Sun, 28 Jun 2026 03:18:57 GMT», «Wed, 08 Jul 26 08:00:28 +0300», «13.07.2026»,
«2026-07-26». Три формата в одной колонке - это не дата, а строка: сортировка по ней
даёт бессмыслицу, сравнение «свежее чем» невозможно. Плюс у 76,5% строк она пуста.

ЧЕСТНОЕ РАЗДЕЛЕНИЕ, КОТОРОГО ЗДЕСЬ ДЕРЖИМСЯ. Есть три РАЗНЫЕ даты, и раньше они были
свалены в одну колонку или отсутствовали вовсе:
    data_iso      - когда СООБЩЕНО о событии (карточка источника или RSS-фид или дата в
                    ссылке). Это и есть «дата новости».
    data_vzyatiya - когда МЫ ЭТО ВЗЯЛИ (seen_news / updated_at). Известна почти всегда и
                    поэтому соблазнительна, но событию не принадлежит: новость 2024 года,
                    подобранная вчера, датой взятия выглядит свежей.
    data_plana    - дата из ТЕКСТА, лежащая в БУДУЩЕМ («запустят в 2027», «к 31.12.2027»).
                    Это срок проекта, а не дата события. Смешивать с data_iso нельзя.
Каждая запись несёт `data_otkuda` - ярлык источника даты, а не только саму дату.

Порядок надёжности для data_iso (первый сработавший выигрывает):
    karta_vk   - дата поста ВК из wall.getById (карточка первоисточника);
    karta      - дата в самой карточке источника (ЕИС, tender.pro): ISO или ДД.ММ.ГГГГ;
    rss        - pubDate фида в формате RFC-822;
    url        - дата в адресе статьи (/2026/07/16/) - так их ставит сама редакция;
    tekst      - полная дата из текста, НЕ лежащая в будущем.
Ничего не сработало - data_iso пусто и заполнена `prichina_bez_daty` словами.

Модуль без сети и без базы: чистые функции, годится и для нового потока (по одному
событию на входе), и для разбора старых строк.
"""
import datetime
import re

# Разумные границы. Нижняя стояла на 2015 и ОТБРАСЫВАЛА живые даты: замер по всей базе
# нашёл 5 строк с датами 2009, 2013, 2014 - это настоящие даты старых статей, и они не мусор,
# а ценный признак «сигнал протухший». Гейт нужен против мусора (epoch 1970, год 2099), а не
# против старых новостей, поэтому нижняя граница опущена до 2005.
NIZ = datetime.date(2005, 1, 1)


def _verh():
    return datetime.date.today() + datetime.timedelta(days=2)


def razumnaya(d):
    """Дата прошла границы? Прибор обязан уметь отказывать, иначе «дата есть» ничего не значит."""
    return bool(d) and NIZ <= d <= _verh()


_MES = {'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'мая': 5, 'май': 5, 'июн': 6, 'июл': 7,
        'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}


def _sobrat(g, m, d):
    try:
        return datetime.date(int(g), int(m), int(d))
    except Exception:  # noqa: BLE001
        return None


def iso_iz_ts(ts):
    """Строка `ts` из signals -> (дата, вид). Вид: karta | rss | '' (не разобралось).

    Вид определяется форматом, и это не догадка: RFC-822 в базу кладут только
    RSS-коллекторы (`_rss_items`, `col_rss`), а ISO и ДД.ММ.ГГГГ приходят из карточек
    площадок (ЕИС, tender.pro), где дату берут из поля карточки.
    """
    t = (ts or '').strip()
    if not t:
        return None, ''
    m = re.match(r'^[A-Za-z]{3},\s*(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{2,4})', t)
    if m:
        g = int(m.group(3))
        g = g + 2000 if g < 100 else g
        d = _sobrat(g, _MES.get(m.group(2).lower(), 0), m.group(1))
        return (d if razumnaya(d) else None), 'rss'
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', t)
    if m:
        d = _sobrat(m.group(1), m.group(2), m.group(3))
        return (d if razumnaya(d) else None), 'karta'
    m = re.match(r'^(\d{4})-(\d{2})$', t)
    if m:
        # ТОЧНОСТЬ ДО МЕСЯЦА. Так ЕИС отдаёт план закупки: «2026-07» это планируемый МЕСЯЦ,
        # дня в источнике нет. Замер: 129 строк. Раньше они попадали в «ts не разобрался»,
        # то есть месяц был известен, а числилось «даты нет». Подставлять 1-е число молча
        # нельзя - поэтому день ставим первым, но вид отдаём отдельный, и точность видна.
        d = _sobrat(m.group(1), m.group(2), 1)
        return (d if razumnaya(d) or (d and d <= datetime.date(2040, 12, 31)) else None), 'karta_mesyac'
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})', t)
    if m:
        d = _sobrat(m.group(3), m.group(2), m.group(1))
        return (d if razumnaya(d) else None), 'karta'
    if re.match(r'^\d{9,13}$', t):
        try:
            sek = int(t[:10])
            d = datetime.datetime.utcfromtimestamp(sek).date()
            return (d if razumnaya(d) else None), 'karta'
        except Exception:  # noqa: BLE001
            return None, ''
    return None, ''


def iso_iz_epoch(sek):
    """Дата поста ВК и любой unix-штамп карточки."""
    try:
        d = datetime.datetime.utcfromtimestamp(int(sek)).date()
    except Exception:  # noqa: BLE001
        return None
    return d if razumnaya(d) else None


_URL_RX = [re.compile(r'/(20[2-3]\d)/(\d{1,2})/(\d{1,2})(?:[/_.-]|$)'),
           re.compile(r'/(20[2-3]\d)-(\d{1,2})-(\d{1,2})'),
           re.compile(r'[?&](?:date|dt|day)=(20[2-3]\d)-(\d{1,2})-(\d{1,2})'),
           re.compile(r'[/_-](20[2-3]\d)(\d{2})(\d{2})[/_-]')]
_URL_RX_DMY = re.compile(r'/(\d{2})-(\d{2})-(20[2-3]\d)(?:[/_.-]|$)')


def data_iz_url(url):
    """Дату в адресе ставит сама редакция при публикации - это дата публикации, не наша."""
    u = url or ''
    for rx in _URL_RX:
        m = rx.search(u)
        if m:
            d = _sobrat(m.group(1), m.group(2), m.group(3))
            if razumnaya(d):
                return d
    m = _URL_RX_DMY.search(u)
    if m:
        d = _sobrat(m.group(3), m.group(2), m.group(1))
        if razumnaya(d):
            return d
    return None


_TXT_RX1 = re.compile(r'\b(\d{1,2})\.(\d{1,2})\.(20[2-3]\d)\b')
_TXT_RX2 = re.compile(r'\b(\d{1,2})\s+(январ|феврал|март|апрел|ма[йя]|июн|июл|август|'
                      r'сентябр|октябр|ноябр|декабр)\w*\s+(20[2-3]\d)', re.I)
_MES_RU = ['январ', 'феврал', 'март', 'апрел', 'ма', 'июн', 'июл', 'август',
           'сентябр', 'октябр', 'ноябр', 'декабр']


def daty_iz_teksta(tekst):
    """Все полные даты из текста -> отсортированный список. Год без числа НЕ берём:
    «в 2027 году» это срок, а не дата, и подставлять к нему 1 января значит выдумывать."""
    out = []
    for m in _TXT_RX1.finditer(tekst or ''):
        d = _sobrat(m.group(3), m.group(2), m.group(1))
        if d and NIZ <= d <= datetime.date(2040, 12, 31):
            out.append(d)
    for m in _TXT_RX2.finditer(tekst or ''):
        sl = m.group(2).lower()
        nom = next((i + 1 for i, s in enumerate(_MES_RU) if sl.startswith(s[:3])), 0)
        d = _sobrat(m.group(3), nom, m.group(1))
        if d and NIZ <= d <= datetime.date(2040, 12, 31):
            out.append(d)
    return sorted(set(out))


def god_iz_teksta(tekst):
    gg = sorted({int(g) for g in re.findall(r'\b(20[2-3]\d)\b', tekst or '')})
    return gg


PRICHINY = {
    'vk': 'ВК: дата есть в карточке поста, коллектор её не переносит (pubDate пустой)',
    'vydacha': 'поисковая выдача: коллектор ставит pubDate пустым, в ссылке даты нет',
    'karta_bez_daty': 'карточка площадки без даты в ссылке и тексте',
    'net_nigde': 'ни в ts, ни в ссылке, ни в тексте даты нет',
}


def normalizovat(ts='', source_url='', what='', source='', vk_epoch=None,
                 vzyatie=None, seen_ts=None):
    """Одна запись -> нормализованная дата и ярлык её происхождения.

    vk_epoch - дата поста, если её удалось достать из карточки ВК (wall.getById);
    vzyatie/seen_ts - даты ВЗЯТИЯ (updated_at / seen_news), в data_iso не попадают НИКОГДА.
    """
    r = {'data_iso': '', 'data_otkuda': '', 'data_vzyatiya': '', 'data_vzyatiya_otkuda': '',
         'data_plana': '', 'prichina_bez_daty': '', 'data_tochnost': '',
         'ts_syraya': (ts or '').strip()}

    # дата взятия - отдельно и всегда честно помечена
    for znach, yarlyk in ((seen_ts, 'seen_news'), (vzyatie, 'updated_at')):
        d, _ = iso_iz_ts(znach)
        if d:
            r['data_vzyatiya'] = d.isoformat()
            r['data_vzyatiya_otkuda'] = yarlyk
            break

    segodnya = datetime.date.today()
    d = iso_iz_epoch(vk_epoch) if vk_epoch else None
    if d:
        r['data_iso'], r['data_otkuda'] = d.isoformat(), 'karta_vk'
        r['data_tochnost'] = 'день'
    if not r['data_iso']:
        d, vid = iso_iz_ts(ts)
        if d and vid == 'karta_mesyac':
            # «2026-07» из плана закупки ЕИС: месяц известен, дня нет. Если месяц ещё не
            # наступил, это СРОК, а не дата события, и в data_iso ему не место.
            if d > segodnya:
                r['data_plana'] = d.strftime('%Y-%m')
                r['prichina_bez_daty'] = ('в карточке только планируемый месяц закупки (%s), '
                                          'он в будущем: это срок, а не дата события'
                                          % d.strftime('%Y-%m'))
            else:
                r['data_iso'], r['data_otkuda'] = d.isoformat(), vid
                r['data_tochnost'] = 'месяц'
        elif d:
            r['data_iso'], r['data_otkuda'] = d.isoformat(), vid
            r['data_tochnost'] = 'день'
    if not r['data_iso']:
        d = data_iz_url(source_url)
        if d:
            r['data_iso'], r['data_otkuda'] = d.isoformat(), 'url'
            r['data_tochnost'] = 'день'

    # текст: берём только НЕ будущую дату; будущая - это срок проекта, ей своё поле
    daty = daty_iz_teksta(what)
    proshlye = [x for x in daty if x <= segodnya]
    budushchie = [x for x in daty if x > segodnya]
    if not r['data_iso'] and proshlye:
        r['data_iso'], r['data_otkuda'] = proshlye[-1].isoformat(), 'tekst'
        r['data_tochnost'] = 'день'
    if budushchie:
        r['data_plana'] = budushchie[0].isoformat()
    elif not r['data_plana']:
        gg = [g for g in god_iz_teksta(what) if g > segodnya.year]
        if gg:
            r['data_plana'] = str(gg[0])          # только год, дня в тексте нет

    if not r['data_iso'] and not r['prichina_bez_daty']:
        u = (source_url or '').lower()
        if 'vk.com' in u or 'вконтакте' in (source or '').lower():
            r['prichina_bez_daty'] = PRICHINY['vk']
        elif (ts or '').strip():
            r['prichina_bez_daty'] = 'ts не разобрался: %r' % (ts or '')[:40]
        elif u:
            r['prichina_bez_daty'] = PRICHINY['vydacha']
        else:
            r['prichina_bez_daty'] = PRICHINY['net_nigde']
    return r


# ---------------------------------------------------------- контроль негодным входом
NEGODNOE = [
    ('пустая строка', ''),
    ('мусор', 'вчера утром'),
    ('несуществующий день', '32.13.2026'),
    ('битый RFC-822', 'Bla, 99 Xyz 2026 10:00:00 GMT'),
    ('слишком старая', '01.01.1970'),
    ('из будущего', '01.01.2099'),
    ('число без даты', '12345'),
    ('похоже на дату, но не она', 'ГОСТ 12.1.005-88'),
    ('несуществующий месяц', '2026-13'),
    ('год без месяца', '2026'),
]
NEGODNYE_URL = [
    ('без даты', 'https://example.ru/news/kompressor-kupili'),
    ('версия в пути', 'https://example.ru/v2/12/34/page'),
    ('номер закупки', 'https://zakupki.gov.ru/epz/order/0371500001226000199'),
    ('дата из будущего в пути', 'https://example.ru/2099/01/01/nechto'),
]


def kontrol(pechat=True):
    """Заведомо негодный вход не должен давать дату. Возвращает число проколов."""
    prokoly = []
    for imya, znach in NEGODNOE:
        d, vid = iso_iz_ts(znach)
        if d is not None:
            prokoly.append('ts «%s» (%s) -> %s' % (znach, imya, d))
        if pechat:
            print('  ts  %-26s %-30s -> %s' % (imya, repr(znach)[:30], d or 'нет'))
    for imya, u in NEGODNYE_URL:
        d = data_iz_url(u)
        if d is not None:
            prokoly.append('url «%s» (%s) -> %s' % (u, imya, d))
        if pechat:
            print('  url %-26s %-30s -> %s' % (imya, u[-30:], d or 'нет'))
    # годный вход обязан разбираться, иначе «нет проколов» достигается отказом всему
    godnye = [('Sun, 28 Jun 2026 03:18:57 GMT', datetime.date(2026, 6, 28), 'rss'),
              ('Wed, 08 Jul 26 08:00:28 +0300', datetime.date(2026, 7, 8), 'rss'),
              ('13.07.2026', datetime.date(2026, 7, 13), 'karta'),
              ('2026-07-26', datetime.date(2026, 7, 26), 'karta'),
              ('2026-07', datetime.date(2026, 7, 1), 'karta_mesyac'),
              ('18.06.2009', datetime.date(2009, 6, 18), 'karta')]
    for s, zhdem, vid_zhdem in godnye:
        d, vid = iso_iz_ts(s)
        ok = (d == zhdem and vid == vid_zhdem)
        if not ok:
            prokoly.append('годная дата «%s» разобралась как %s/%s' % (s, d, vid))
        if pechat:
            print('  годн %-30s -> %s / %s %s' % (s, d, vid, '' if ok else 'ПРОКОЛ'))
    u = 'https://vestidv.ru/news/2026/07/16/125240'
    if data_iz_url(u) != datetime.date(2026, 7, 16):
        prokoly.append('годный url не разобрался: %s' % u)
    if pechat:
        print('  годн url %-38s -> %s' % (u[-38:], data_iz_url(u)))
    return prokoly


if __name__ == '__main__':
    print('=== контроль негодным входом ===')
    p = kontrol()
    print('проколов: %d' % len(p))
    for x in p:
        print('  ! ' + x)
