# -*- coding: utf-8 -*-
r"""Факты о продукции и новости с сайта предприятия — для персонализации писем.

По ТЗ соседней сессии (TZ-OBHOD-SAYTOV-fakty-dlya-pisem.md, 13.08). Смысл: письмо
во втором абзаце называет, что предприятие выпускает. Сейчас генератор берёт одно
поле activity, и когда там пусто — модель пересказывает НАЗВАНИЕ ОКВЭД как
продукцию. Замеры соседей: «Машины Сладости» получили «конфеты-суфле и какао-
порошок» (какао — это название кода 10.82), «Пивкомбинат Балаковский» по сайту
делает печенье и пряники, а не пиво. Слепое сравнение с живым редактором: 2,89
против 4,11 по конкретности — разрыв ровно в том, что она открывает сайт.

Отсюда три запрета ТЗ, которые вшиты в промпт: ничего не выводить из ОКВЭД, ничего
не выводить из названия компании, не обобщать до отрасли. Пустое поле — нормальный
результат, пустое лучше правдоподобного.

Страницы берём ИЗ КЭША (их привозит Зенка или обычный краул) — сеть здесь не нужна.
Результат кладём в enrich.db, таблица site_facts: это сервер, он переживает рестарт
песочницы.

Команды:
    python site_facts.py --ochered [N]    поставить компании кампании 8 в очередь Зенки
                                          за фактами (строка «ИНН;url;facts»)
    python site_facts.py --sobrat [N]     разобрать страницы из кэша провайдером
    python site_facts.py --stat           что собрано
"""
import gzip
import json
import os
import re
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
# gen_provider лежит НЕ рядом со скриптами обогащения, а на уровень выше
# (C:\sender\gen_provider.py) — без этого падало ModuleNotFoundError
for _p in (os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.append(_p)
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
SENDER_BD = os.environ.get('SENDER_DB', r'C:\sender\sender.db')
KAMPANIYA = int(os.environ.get('KAMPANIYA', '8'))
MODEL = os.environ.get('FACTS_MODEL', 'gpt-5.6-luna')
# Модель для НОВОСТЕЙ отдельная: замер 13.08 показал, что луна честна (все её
# новости подтверждены дословно), но скупа — тратит 590 токенов на ответ против
# 3131 у хайку и обрывает список. Хайку выдала 12 новостей, из них 11 полностью
# подтверждены текстом страниц. Поэтому карточку делает луна, новости — хайку.
MODEL_NOVOSTI = os.environ.get('FACTS_NEWS_MODEL', 'claude-haiku-4-5')

SHEMA = """CREATE TABLE IF NOT EXISTS site_facts(
    inn TEXT PRIMARY KEY,
    facts_json  TEXT,
    sources_json TEXT,
    site TEXT,
    ts   TEXT,
    note TEXT)"""

PROMPT = """Ты собираешь факты о предприятии ТОЛЬКО из текста его сайта — для холодного
письма, где второй абзац называет, что предприятие выпускает.

ТРИ ЗАПРЕТА (нарушение делает работу бессмысленной):
1. Ничего не выводить из ОКВЭД: код — классификатор, а не ассортимент.
2. Ничего не выводить из названия компании: «Пивкомбинат» может делать печенье,
   «Молзавод» — мороженое.
3. Не обобщать до отрасли: «молочная продукция» вместо «масло, крем-сыр, сыр»
   бесполезна — такая фраза подходит любому заводу и читается как массовая рассылка.

Все значения — СЛОВАМИ САЙТА, без пересказа. Пустое поле — нормальный результат;
пустое лучше правдоподобного.

Компания: %(name)s, ИНН %(inn)s, сайт %(site)s.

Страницы сайта (адрес и текст):
%(stranicy)s

В тексте страниц ссылки записаны как «подпись [адрес]» — это НАСТОЯЩИЕ адреса со
страницы. В поле url новости ставь адрес САМОЙ ЗАПИСИ из такой пары, а не адрес
раздела и не главную. Нет адреса записи — оставь url пустым, это честнее.

Верни СТРОГО JSON:
{"продукция": ["до 12 позиций или групп, словами сайта"],
 "упаковка_фасовка": ["флоу-пак", "ведро 5 кг"],
 "сырьё": ["что заходит на вход"],
 "мощности": ["ТОЛЬКО фразы с числом, дословно"],
 "контроль_качества": ["ХАССП", "ISO 22000", "собственная лаборатория"],
 "энергохозяйство": ["компрессорная", "пневмоинструмент", "окрасочная камера",
                     "пескоструй", "сушильная камера", "котельная", "станочный парк"],
 "расширение": ["новый цех/линия/участок/склад, дословно и С ДАТОЙ, если она есть"],
 "газы": ["азот", "кислород", "аргон", "модифицированная атмосфера", "газовая резка"],
 "новости": [{"дата": "как на сайте", "заголовок": "дословно",
              "url": "прямая ссылка НА САМУ ЗАПИСЬ", "текст": "первые 2-3 предложения дословно"}],
 "свежая_новость": "первая подходящая из новостей, с датой",
 "цитата": "одна буквальная строка со страницы, подтверждающая продукцию",
 "источники": ["url, откуда взято"],
 "уверенность": "высокая|средняя|низкая"}

Про три новых поля. Они нужны компрессорному направлению, а прежние — рентгену и
фотосепараторам; компания бывает целью обоих сразу, поэтому спрашиваем всё вместе.
  * энергохозяйство — то, что ПОТРЕБЛЯЕТ сжатый воздух или стоит рядом с ним:
    компрессорная, пневмоинструмент, покраска, пескоструй, сушка, котельная,
    станочный парк. Пиши словами сайта, не додумывай по отрасли.
  * расширение — новый цех, линия, участок, склад, реконструкция. С датой, если
    она на сайте. Без даты тоже бери, но дату не выдумывай.
  * газы — азот, кислород, аргон, углекислота, модифицированная атмосфера,
    газовая резка, а также покупка баллонов и криогеники.
Пустое поле здесь так же нормально, как и в остальных: у механического завода не
будет модифицированной атмосферы, у молокозавода — газовой резки.

Про новости: годятся запуск и модернизация линии, цеха, склада; рост мощности —
особенно с числом; новый продукт или упаковка; сертификация; новое оборудование;
выход в сеть или регион; награда на отраслевой выставке. НЕ годятся поздравления,
дни рождения, корпоративы, «работаем в штатном режиме», перепечатки чужих новостей.
Без даты новость бесполезна — «недавно» писать нельзя. Глубина — последние 12
месяцев, до 10 записей, свежая первой."""


PROMPT_NOVOSTI = """Со страниц сайта компании «%(name)s» выпиши НОВОСТИ — дословно.

Ссылки в тексте записаны как «подпись [адрес]»: это настоящие адреса со страницы.
В поле url ставь адрес САМОЙ ЗАПИСИ из такой пары, а не адрес раздела и не главную.
Нет адреса записи — оставь url пустым, это честнее выдумки.

Годятся: запуск и модернизация линии, цеха, склада; рост мощности, особенно с
числом; новый продукт или упаковка; сертификация и аудит; новое оборудование;
выход в сеть или регион; награда на отраслевой выставке.
НЕ годятся: поздравления, дни рождения, корпоративы, «работаем в штатном режиме»,
перепечатки чужих новостей.

Без даты новость бесполезна — «недавно» писать нельзя, такую запись пропускай.
Глубина — последние 12 месяцев, до 10 записей, свежая первой. Если новостей нет,
верни пустой список: пустое лучше правдоподобного.

Страницы:
%(stranicy)s

Верни СТРОГО JSON: {"новости": [{"дата": "как на сайте", "заголовок": "дословно",
 "url": "ссылка на саму запись", "текст": "первые 2-3 предложения дословно"}]}"""

# следы ленты: дата рядом с годом — по ним решаем, звать ли вторую модель
_SLED_NOVOSTI = re.compile(
    r'\d{1,2}[.\s](?:0[1-9]|1[0-2]|январ|феврал|март|апрел|мая|июн|июл|август|'
    r'сентябр|октябр|ноябр|декабр)\w*[.\s]?20\d\d', re.I)
_STRANICA_NOVOSTEY = re.compile(r'(news|novosti|press|blog|smi|media)', re.I)


def _dobrat_novosti(klient, kompaniya, stranicy, fakty, nado=3):
    """Второй проход: новости отдельной моделью, но только если есть за чем идти.

    Три условия, иначе вызов не делаем и денег не тратим:
      * основная модель дала меньше `nado` новостей;
      * на страницах видны даты (лента вообще существует);
      * есть страницы, похожие на новостной раздел.
    Кормим ТОЛЬКО новостные страницы — так вход в разы меньше, чем полная карточка.
    """
    import gen_provider as GP

    if len(fakty.get('новости') or []) >= nado:
        return None
    novostnye = [(u, t) for u, t in stranicy
                 if _STRANICA_NOVOSTEY.search(u) or _SLED_NOVOSTI.search(t)]
    if not novostnye:
        return None
    tekst = '\n\n'.join('--- %s\n%s' % (u, t[:9000]) for u, t in novostnye[:6])
    if not _SLED_NOVOSTI.search(tekst):
        return None
    msg = GP.call(klient, [{'role': 'user', 'content': PROMPT_NOVOSTI % {
        'name': (kompaniya.get('name') or '')[:80], 'stranicy': tekst}}],
        model=MODEL_NOVOSTI, attempts=2)
    d = GP.parse_json(msg) or {}
    novye = [n for n in (d.get('новости') or [])
             if isinstance(n, dict) and str(n.get('дата') or '').strip()]
    if len(novye) <= len(fakty.get('новости') or []):
        return None          # не полнее старого — не переписываем
    return novye[:10]



# --- РАЗБОР ЭНЕРГОХОЗЯЙСТВА: что ДЕЙСТВИТЕЛЬНО потребляет сжатый воздух ------------
# Поле «энергохозяйство» собирается словами сайта, поэтому в него попадает и то, что
# к воздуху отношения не имеет: «природным газом» у газовой компании — это её товар,
# «котельная» — энергообъект, но не потребитель воздуха. Отделу продаж нужен не
# список слов, а признак «этому писать про компрессор» с доказательством строкой.
# Раскладываем на три корзины ПРАВИЛАМИ, а не моделью: правило проверяемо и бесплатно.
_VOZDUH = re.compile(
    r'пневм|компрессор|станк|чпу|\bcnc\b|фрезер|токарн|шлифов|покрас|окрасоч|'
    r'пескостру|дробестру|сушк|сушил|сушильн|лазер|плазм|резк|гибк|сварк|штамп|'
    r'пресс|лить[её]|формовк|фасовк|упаковочн|розлив|конвейер|обдув|аэрац|флотац|'
    r'вакуум|распылен|краскопульт|термопласт|экструд', re.I)
_GAZY_TEHN = re.compile(
    r'азот|кислород|аргон|углекислот|криоген|баллон|модифицированн\w+ атмосфер|'
    r'газовая резк|газокислородн|защитн\w+ газ|газов\w+ смес', re.I)
_ENERGO_NE_VOZDUH = re.compile(
    r'котельн|электростанц|трансформатор|подстанц|теплотрасс|газопровод|'
    r'природн\w+ газ|отоплен|энергоснабжен|электросет', re.I)


def razlozhit_energohozyaystvo(fakty):
    """Три корзины: воздух точно, газы техничеcкие, просто энергообъект.

    Возвращает словарь для записи в карточку. Строки сохраняем ДОСЛОВНО — они и
    есть доказательство для письма, менеджер должен видеть, откуда вывод.
    """
    vozduh, gazy, prosto = [], [], []
    for pole in ('энергохозяйство', 'газы', 'продукция', 'мощности', 'расширение'):
        for x in (fakty.get(pole) or []):
            s = str(x).strip()
            if not s:
                continue
            if _GAZY_TEHN.search(s):
                if s not in gazy:
                    gazy.append(s)
            elif _VOZDUH.search(s):
                if s not in vozduh:
                    vozduh.append(s)
            elif pole == 'энергохозяйство' and _ENERGO_NE_VOZDUH.search(s):
                if s not in prosto:
                    prosto.append(s)
    return {'воздух_точно': vozduh[:8], 'газы_технические': gazy[:8],
            'энергообъекты_без_воздуха': prosto[:5],
            'признак_КЦ': bool(vozduh or gazy)}



# --- СВЕЖЕСТЬ НОВОСТЕЙ ПРОВЕРЯЕМ САМИ ---------------------------------------------
# Промпт просит «последние 12 месяцев», и модель это нарушает: у Кропоткинского
# пивзавода взята запись от 14 декабря 2021 с адресом /press-tsentr/2019/.
# Инфоповод «почему пишу сейчас» из пятилетней новости не построить, поэтому
# режем правилом, а не просьбой.
_MESYACY = {'\u044f\u043d\u0432\u0430\u0440': 1, '\u0444\u0435\u0432\u0440\u0430\u043b': 2,
            '\u043c\u0430\u0440\u0442': 3, '\u0430\u043f\u0440\u0435\u043b': 4,
            '\u043c\u0430\u044f': 5, '\u043c\u0430\u0439': 5, '\u0438\u044e\u043d': 6,
            '\u0438\u044e\u043b': 7, '\u0430\u0432\u0433\u0443\u0441\u0442': 8,
            '\u0441\u0435\u043d\u0442\u044f\u0431\u0440': 9, '\u043e\u043a\u0442\u044f\u0431\u0440': 10,
            '\u043d\u043e\u044f\u0431\u0440': 11, '\u0434\u0435\u043a\u0430\u0431\u0440': 12}


def _data_novosti(s):
    """Дата из строки сайта в (год, месяц). Форматы разные, гадать не будем:
    что не разобралось — возвращаем None, и такая запись остаётся (лучше лишняя,
    чем потерянная свежая)."""
    t = str(s or '').lower().replace('\u0451', '\u0435')
    m = re.search(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](20\d\d)', t)
    if m:
        return int(m.group(3)), int(m.group(2))
    m = re.search(r'(\d{1,2})\s+([\u0430-\u044f]+)\s+(20\d\d)', t)
    if m:
        for kl, nom in _MESYACY.items():
            if m.group(2).startswith(kl):
                return int(m.group(3)), nom
    m = re.search(r'([\u0430-\u044f]+)\s+(20\d\d)', t)
    if m:
        for kl, nom in _MESYACY.items():
            if m.group(1).startswith(kl):
                return int(m.group(2)), nom
    m = re.search(r'\b(20\d\d)\b', t)
    if m:
        return int(m.group(1)), 12
    return None


def otsech_starye_novosti(novosti, mesyacev=15):
    """Оставить записи не старше mesyacev. Порог 15, а не 12: сайт может писать
    «декабрь 2025» без числа, и жёсткие 12 месяцев отрезали бы годную новость."""
    teper = time.localtime()
    predel = teper.tm_year * 12 + teper.tm_mon - mesyacev
    svezhie = []
    for n in (novosti or []):
        if not isinstance(n, dict):
            continue
        d = _data_novosti(n.get('\u0434\u0430\u0442\u0430'))
        if d is None or d[0] * 12 + d[1] >= predel:
            svezhie.append(n)
    return svezhie


def _bd():
    c = sqlite3.connect(BD, timeout=60)
    c.execute(SHEMA)
    # popytok: сколько раз карточка не собралась. Без счётчика пустую карточку
    # либо больше никогда не пробуют (так и было), либо крутят вечно.
    try:
        c.execute('ALTER TABLE site_facts ADD COLUMN popytok INTEGER DEFAULT 0')
    except Exception:  # noqa: BLE001
        pass
    c.execute('PRAGMA journal_mode=WAL')
    c.commit()
    return c


def _kompanii_kampanii():
    """ИНН и сайты компаний очереди подтверждения (по ТЗ — сперва кампания Meyer)."""
    s = sqlite3.connect(SENDER_BD)
    s.row_factory = sqlite3.Row
    inny = [str(r['inn']) for r in s.execute(
        "select distinct r.inn from confirm_reviews cr "
        "join recipients r on r.id=cr.recipient_id "
        "where cr.campaign_id=? and cr.status='pending' and r.inn is not null",
        (KAMPANIYA,)).fetchall()]
    s.close()
    if not inny:
        return []
    c = sqlite3.connect(BD)
    c.row_factory = sqlite3.Row
    q = ','.join('?' * len(inny))
    out = []
    for r in c.execute("select inn, coalesce(name,'') name, coalesce(site,'') site, "
                       "coalesce(cand_site,'') cand from companies where inn in (%s)" % q,
                       inny):
        u = (r['site'] or r['cand'] or '').strip()
        if u:
            out.append({'inn': str(r['inn']), 'name': r['name'], 'site': u})
    c.close()
    return out


def ochered(predel=100):
    """Поставить компании в очередь Зенки С МЕТКОЙ facts — она возьмёт каталог и
    новости вместо страницы контактов."""
    komp = _kompanii_kampanii()[:predel]
    if not komp:
        return {'нечего_ставить': True}
    put = os.path.join(ZENNO, 'ochered.txt')
    os.makedirs(ZENNO, exist_ok=True)
    with open(put, 'a', encoding='utf-8') as f:
        f.write('\n'.join('%s;%s;facts' % (k['inn'], k['site']) for k in komp) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return {'поставлено': len(komp), 'файл': put}


_SSYLKA = re.compile(r'<a\b[^>]*?href\s*=\s*["\']([^"\'>]+)["\'][^>]*>(.*?)</a>',
                     re.S | re.I)
# РАЗДЕЛ или ЗАПИСЬ. Раздел («/news/», «/press-center/») нам не нужен: до него
# обходчик доберётся сам. Нужна ссылка на КОНКРЕТНУЮ запись, а её видно по дате
# или числовому номеру в адресе.
_RAZDEL_NOVOSTEY = re.compile(r'(news|novosti|press|blog|article|stat[ьi])', re.I)
_ZAPIS = re.compile(r'(/20\d\d[/-]\d|/\d{3,}|[?&]id=\d+|-\d{4,}|\.html?$)', re.I)


def _ssylki_v_tekst(html, adres_stranicy, predel=40):
    """Заменить <a href=X>текст</a> на «текст [X]» — чтобы адрес пережил срезание тегов.

    Берём не все подряд. Первая версия тащила всё с длинной подписью и давала
    150 ссылок на компанию: они выдавливали из отведённого объёма настоящий текст,
    за который мы платим. Оставляем только то, что похоже на ОТДЕЛЬНУЮ ЗАПИСЬ —
    у неё в адресе дата или номер, — и не больше predel штук на страницу,
    без повторов.
    """
    try:
        from urllib.parse import urljoin
    except Exception:  # noqa: BLE001
        return html

    vzyato = set()

    def zamena(m):
        syraya, vnutri = m.group(1), m.group(2)
        podpis = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', vnutri)).strip()
        if not podpis or syraya.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            return vnutri
        # запись новости: либо адрес прямо на неё, либо длинный заголовок в разделе новостей
        zapis = _ZAPIS.search(syraya) and _RAZDEL_NOVOSTEY.search(
            syraya + ' ' + adres_stranicy)
        zagolovok = len(podpis) >= 30 and _RAZDEL_NOVOSTEY.search(
            syraya + ' ' + adres_stranicy)
        if not (zapis or zagolovok):
            return vnutri
        try:
            polnyy = urljoin(adres_stranicy, syraya)
        except Exception:  # noqa: BLE001
            polnyy = syraya
        if polnyy in vzyato or len(vzyato) >= predel:
            return vnutri            # повтор или перебор — адрес не нужен
        vzyato.add(polnyy)
        return '%s [%s]' % (podpis, polnyy)

    return _SSYLKA.sub(zamena, html)


def _stranicy(inn, predel_znakov=60000):
    """Страницы компании из кэша: [(url, текст)] — теги срезаны, порядок сохранён."""
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return []
    try:
        with gzip.open(p, 'rb') as f:
            d = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return []
    out, vsego = [], 0
    for pg in (d.get('pages') or []):
        h = pg.get('html') or ''
        if not h:
            continue
        t = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
        # ССЫЛКИ СОХРАНЯЕМ ДО СРЕЗАНИЯ ТЕГОВ. Раньше здесь сразу шло срезание всего,
        # и вместе с тегами исчезали href — модель физически не могла дать ссылку на
        # новость и подставляла адрес страницы целиком. Соседняя сессия поймала это
        # как «ссылка ведёт на главную, а не на запись» (13.08).
        # Тащим не все подряд, иначе меню раздует вход: берём ссылку, если её текст
        # длинный (заголовок новости) или сам адрес похож на запись.
        t = _ssylki_v_tekst(t, pg.get('url') or '')
        t = re.sub(r'<[^>]+>', ' ', t)
        for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"'),
                     ('&laquo;', '«'), ('&raquo;', '»'), ('&mdash;', '-')):
            t = t.replace(a, b)
        t = re.sub(r'\s+', ' ', t).strip()
        if len(t) < 200:
            continue
        # ТЗ требует дословности: режем страницу, но не выбрасываем целиком
        kusok = t[:8000]
        if vsego + len(kusok) > predel_znakov:
            break
        vsego += len(kusok)
        out.append((pg.get('url') or '', kusok))
    return out


def _iz_kesha(predel):
    """Компании, чьи страницы уже лежат в кэше (их привезла Зенка или обычный краул).

    Нужно, чтобы не ждать обхода кампании: страницы по многим компаниям уже есть, и
    качество разбора проверяется на них прямо сейчас. Берём самые свежие файлы.
    """
    c = sqlite3.connect(BD)
    c.row_factory = sqlite3.Row
    imena = {str(r['inn']): (r['name'] or '', (r['site'] or r['cand'] or ''))
             for r in c.execute("select inn, coalesce(name,'') name, coalesce(site,'') site, "
                                "coalesce(cand_site,'') cand from companies")}
    c.close()
    fajly = [n for n in os.listdir(KESH) if n.endswith('.json.gz')]
    fajly.sort(key=lambda x: -os.path.getmtime(os.path.join(KESH, x)))
    out = []
    for n in fajly:
        inn = n.split('.')[0]
        if inn not in imena:
            continue
        name, site = imena[inn]
        out.append({'inn': inn, 'name': name, 'site': site})
        if len(out) >= predel * 3:
            break
    return out


def sobrat(predel=50, iz_kesha=False, spisok=None):
    """Разобрать страницы провайдером и записать в site_facts."""
    import gen_provider as GP
    c = _bd()
    c.row_factory = sqlite3.Row
    # ГОТОВА = карточка с содержимым. Раньше здесь стоял просто список ИНН из
    # site_facts, и компания, у которой разбор упал (провайдер ответил «модель
    # недоступна») или страниц ещё не было, помечалась разобранной НАВСЕГДА:
    # 102 пустые карточки на 1611, и у 101 из них страницы в кэше уже лежали.
    # Владелец 14.08 спросил про ошибки провайдера прямо: «такие переспрашиваются?»
    gotovye = {str(r[0]) for r in c.execute(
        "select inn from site_facts where coalesce(facts_json,'')<>'' "
        "or coalesce(popytok,0) >= 3")}
    istochnik = spisok if spisok is not None else (
        _iz_kesha(predel) if iz_kesha else _kompanii_kampanii())
    komp = [k for k in istochnik if k['inn'] not in gotovye][:predel]
    if not komp:
        c.close()
        return {'все_разобраны': len(gotovye)}

    klient = GP.make_client()
    itog = {'разобрано': 0, 'без_страниц': 0, 'сбоев': 0, 'с_продукцией': 0,
            'с_новостями': 0}
    for k in komp:
        stranicy = _stranicy(k['inn'])
        if not stranicy:
            c.execute("INSERT INTO site_facts(inn, facts_json, sources_json, site, ts, "
                      "note, popytok) VALUES(?,?,?,?,?,?,1) ON CONFLICT(inn) DO UPDATE SET "
                      "ts=excluded.ts, note=excluded.note, "
                      "popytok=coalesce(site_facts.popytok,0)+1",
                      (k['inn'], '', '', k['site'],
                       time.strftime('%Y-%m-%dT%H:%M:%S'), 'страниц в кэше нет'))
            c.commit()
            itog['без_страниц'] += 1
            continue
        tekst = '\n\n'.join('--- %s\n%s' % (u, t) for u, t in stranicy)
        vopros = PROMPT % {'name': k['name'][:80], 'inn': k['inn'],
                           'site': k['site'], 'stranicy': tekst}
        try:
            msg = GP.call(klient, [{'role': 'user', 'content': vopros}],
                          model=MODEL, attempts=3)
            fakty = GP.parse_json(msg)
        except Exception as e:  # noqa: BLE001
            itog['сбоев'] += 1
            c.execute("INSERT INTO site_facts(inn, facts_json, sources_json, site, ts, "
                      "note, popytok) VALUES(?,?,?,?,?,?,1) ON CONFLICT(inn) DO UPDATE SET "
                      "ts=excluded.ts, note=excluded.note, "
                      "popytok=coalesce(site_facts.popytok,0)+1",
                      (k['inn'], '', '', k['site'],
                       time.strftime('%Y-%m-%dT%H:%M:%S'), 'провайдер: ' + str(e)[:120]))
            c.commit()
            continue
        # ВТОРОЙ ПРОХОД ЗА НОВОСТЯМИ. Замер 13.08: луна честна (все её новости
        # подтверждены дословно), но скупа — 590 токенов на ответ против 3131 у
        # хайку, и список обрывается. На 20 компаниях луна дала 2 новости, хайку
        # 12, из них 11 подтверждены текстом. Поэтому добираем хайку — и только
        # там, где на страницах реально есть лента: лишний вызов на сайте без
        # новостей это выброшенные деньги.
        try:
            dobrannye = _dobrat_novosti(klient, k, stranicy, fakty)
            if dobrannye:
                fakty['новости'] = dobrannye
                if not fakty.get('свежая_новость') and dobrannye:
                    p = dobrannye[0]
                    fakty['свежая_новость'] = '%s — %s' % (p.get('дата', ''),
                                                           p.get('заголовок', ''))
                itog['новости_вторым_проходом'] = itog.get('новости_вторым_проходом', 0) + 1
        except Exception:  # noqa: BLE001
            pass                      # добор не удался — карточка всё равно годная

        # признак для отдела продаж считаем ЗДЕСЬ и кладём в карточку, чтобы его
        # не пересчитывал каждый читающий по-своему
        # свежесть режем ДО записи: старая новость в письме хуже, чем её отсутствие
        _bylo_n = len(fakty.get('новости') or [])
        fakty['новости'] = otsech_starye_novosti(fakty.get('новости'))
        if _bylo_n and not fakty['новости']:
            fakty['свежая_новость'] = ''
        elif fakty['новости']:
            _p = fakty['новости'][0]
            fakty['свежая_новость'] = '%s — %s' % (_p.get('дата', ''),
                                                   _p.get('заголовок', ''))
        fakty['разбор_КЦ'] = razlozhit_energohozyaystvo(fakty)

        istochniki = fakty.get('источники') or [u for u, _t in stranicy]
        c.execute("INSERT OR REPLACE INTO site_facts(inn, facts_json, sources_json, "
                  "site, ts, note, popytok) VALUES(?,?,?,?,?,?,0)",
                  (k['inn'], json.dumps(fakty, ensure_ascii=False),
                   json.dumps(istochniki, ensure_ascii=False), k['site'],
                   time.strftime('%Y-%m-%dT%H:%M:%S'), ''))
        c.commit()
        itog['разобрано'] += 1
        if fakty.get('продукция'):
            itog['с_продукцией'] += 1
        if fakty.get('новости'):
            itog['с_новостями'] += 1
    c.close()
    return itog


def peresprosit(predel=100):
    """Пустые карточки, у которых страницы в кэше УЖЕ есть, — собрать заново.

    Пустая карточка появлялась двумя путями: разбор шёл раньше обхода («страниц в
    кэше нет») или провайдер отвечал ошибкой. Обе помечали компанию разобранной
    навсегда — 102 такие карточки на 1611, и у 101 страницы к этому моменту уже
    лежали. Здесь мы их и добираем.
    """
    c = _bd()
    c.row_factory = sqlite3.Row
    imena = {str(r['inn']): (r['name'] or '', (r['site'] or r['cand'] or ''))
             for r in c.execute("select inn, coalesce(name,'') name, coalesce(site,'') site, "
                                "coalesce(cand_site,'') cand from companies")}
    spisok = []
    for r in c.execute("select inn, coalesce(site,'') site from site_facts "
                       "where coalesce(facts_json,'')='' and coalesce(popytok,0) < 3"):
        inn = str(r['inn'])
        if not os.path.exists(os.path.join(KESH, inn + '.json.gz')):
            continue
        nm, st = imena.get(inn, ('', ''))
        spisok.append({'inn': inn, 'name': nm, 'site': r['site'] or st})
        if len(spisok) >= predel:
            break
    c.close()
    if not spisok:
        return {'нечего_переспрашивать': True}
    itog = sobrat(predel=len(spisok), spisok=spisok)
    itog['переспрошено_компаний'] = len(spisok)
    return itog


def stat():
    c = _bd()
    c.row_factory = sqlite3.Row
    vsego = c.execute('select count(*) from site_facts').fetchone()[0]
    s_faktami = c.execute("select count(*) from site_facts where coalesce(facts_json,'')<>''"
                          ).fetchone()[0]
    prim = [dict(r) for r in c.execute(
        "select inn, site, substr(coalesce(facts_json,''),1,300) f, note "
        "from site_facts order by ts desc limit 3")]
    c.close()
    return {'записей': vsego, 'с_фактами': s_faktami, 'последние': prim}


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        print(json.dumps(stat(), ensure_ascii=False, indent=1))
    elif a[0] == '--ochered':
        print(json.dumps(ochered(int(a[1]) if len(a) > 1 else 100),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--sobrat':
        print(json.dumps(sobrat(int(a[1]) if len(a) > 1 else 50),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--peresprosit':
        print(json.dumps(peresprosit(int(a[1]) if len(a) > 1 else 100),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--sobrat-kesh':
        print(json.dumps(sobrat(int(a[1]) if len(a) > 1 else 30, iz_kesha=True),
                         ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
