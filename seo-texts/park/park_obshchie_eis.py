# -*- coding: utf-8 -*-
"""ОБЩИЕ ЗАПРОСЫ ПО ТИПУ МАШИНЫ с нарезкой по окну публикации.

Владелец спросил прямо: «а общие запросы по типу винтовой компрессор используете?» —
не использовали. Собирали по маркам, а марка есть не в каждом объявлении: «Ремонт
винтового компрессора», «Поставка компрессорной установки» марки не называют вовсе.

Потолок выдачи ЕИС — 20 страниц по 50 = 1 000 записей на запрос. Замер пробником:

    «винтовой компрессор»  без окна 3 500   -> берём 1 000, теряем 71%
    «компрессор»           без окна 70 000  -> берём 1 000, теряем 98.6%

Поэтому нарезаем по дате публикации. Пробник подтвердил, что параметр применяется
(счётчики по годам разные и осмысленные). Нарезка АДАПТИВНАЯ: сначала год, и если
в год попадает больше 900 записей — тот же год дробится на месяцы. Иначе повторится
ошибка «выбрали 1 000 из 5 900 и не заметили».

Урок 3-й сессии, взят в правило: **счётчик новизны стоит ПОСЛЕ заслона.** Отбракованное
пишем в отдельный файл-отвал с причиной, чтобы «принято 0» нельзя было спутать с
«ничего не нашлось».

Долговечность: пишем в C:\\sender построчно с fsync. Резюмируемость: пройденные окна
и страницы отмечаем в прогресс-файле, уже виденные реестровые номера пропускаем.

Запуск: panel_py, argv = [<индекс первого запроса>, <сколько запросов за вызов>]
"""
import json, os, re, sys, time, urllib.parse

BAZA = r'C:\sender'
OUT = os.path.join(BAZA, 'park_obshchie.jsonl')
PROG = os.path.join(BAZA, 'park_obshchie_progress.json')
OTVAL = os.path.join(BAZA, 'park_obshchie_otval.jsonl')
STRANIC = 20
GODY = list(range(2015, 2027))
PREDEL_OKNA = 900          # больше — дробим год на месяцы
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

ZAPROSY = [
    'винтовой компрессор', 'поршневой компрессор', 'центробежный компрессор',
    'безмасляный компрессор', 'компрессорная установка', 'компрессорная станция',
    'воздушный компрессор', 'модульная компрессорная станция', 'передвижной компрессор',
    'дизельный компрессор', 'генератор азота', 'азотная станция', 'генератор кислорода',
    'кислородная станция', 'воздухоразделительная установка', 'воздуходувка', 'газодувка',
    'турбокомпрессор', 'нагнетатель воздуха', 'ресивер сжатого воздуха',
    'осушитель сжатого воздуха', 'винтовой блок', 'компрессорное оборудование',
    'ремонт компрессора', 'запасные части к компрессору', 'компрессор',
]


def _bez_probelov(t):
    """ЕИС рвёт слова пробелами для подсветки: «винтов ой компрессор а».
    Сравниваем по строке без пробелов вовсе — иначе заслон выбрасывает своё же."""
    return re.sub(r'\s+', '', (t or '').lower().replace('\u0451', '\u0435'))


# Замер на первой тысяче отвала: заслон выбросил «Поставка комплекса подготовки сжатого
# воздуха» — а это ровно наша обвязка (осушитель, фильтры, ресивер). Добавлены слова,
# которыми нашу машину и её обвязку называют, не произнося слова «компрессор».
# Отвал пишется в файл, поэтому старые страницы пересеиваются без повторного сбора.
NASHE = re.compile(
    r'компрессор|воздуходувк|газодувк|турбокомпрессор|нагнетател|воздухораздел|'
    r'(генератор\w{0,4}(азота|кислорода))|(азотн\w{0,4}станци)|(кислородн\w{0,4}станци)|'
    r'ресивер|осушител|(винтов\w{0,4}(блок|пар))|компрессорн|мотокомпрессор|'
    r'(сжат\w{0,4}воздух)|воздухосборник|пневмосет|влагоотделител|маслоотделител|'
    r'(концев\w{0,4}холодильник)|(дожимн\w{0,4}(компрессор|станци|установк))|'
    r'(азотн\w{0,4}установк)|(кислородн\w{0,4}установк)|(криогенн\w{0,4}(установк|блок))|'
    r'(мембранн\w{0,4}(азот|газоразделит))|(адсорбцион\w{0,4}(азот|кислород))|'
    r'воздухоснабжен|(станци\w{0,4}компримирован)|компримирован')
CHUZHOE = re.compile(
    r'стоматолог|аквариум|(медицинск\w{0,4}компрессор)|(компрессор\w{0,4}(матрас|ингалятор|'
    r'небулайзер|тонометр))|(садов\w{0,4}воздуходувк)|ранцев|(бытов\w{0,4}компрессор)|'
    r'(автомобильн\w{0,4}компрессор)|(холодильн\w{0,4}(витрин|ларь|шкаф|агрегат))|'
    r'(компрессор\w{0,4}кондиционер)|(компрессор\w{0,4}холодильник)|автошин|'
    r'(компрессор\w{0,4}сплит)')

_BLOK = re.compile(r'search-registry-entry-block.*?(?=search-registry-entry-block|$)', re.S)
_NOMER = re.compile(r'regNumber=(\d{8,})')
_OBJEKT = re.compile(r'Объект закупки\s*</div>\s*<div[^>]*>\s*(?:<a[^>]*>)?\s*(.*?)\s*(?:</a>)?\s*</div>', re.S)
_ZAKAZ = re.compile(r'(?:Заказчик|Организация, осуществляющая закупку)\s*</div>\s*<div[^>]*>\s*<a[^>]*>\s*(.*?)\s*</a>', re.S)
_TEG = re.compile(r'<[^>]+>')


def _chisto(s):
    s = _TEG.sub(' ', s or '')
    for a, b in (('&quot;', '"'), ('&laquo;', '«'), ('&raquo;', '»'), ('&nbsp;', ' '),
                 ('&amp;', '&'), ('&#39;', "'")):
        s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip()


def _kartochka(nomer):
    """Формы проверены пробой: 11 знаков -> 223-ФЗ, 19 знаков -> 44-ФЗ.
    Форма /epz/order/notice/notice-info/ отдаёт 404 — её не используем."""
    if len(nomer) == 11:
        return ('https://zakupki.gov.ru/223/purchase/public/purchase/info/'
                'common-info.html?regNumber=' + nomer)
    return ('https://zakupki.gov.ru/epz/order/notice/ea44/view/'
            'common-info.html?regNumber=' + nomer)


def _hrom():
    for k in (r'C:\sender\pw-browsers', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')):
        if not k or not os.path.isdir(k):
            continue
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


def _zapisat(fayl, stroki):
    if not stroki:
        return
    with open(fayl, 'a', encoding='utf-8') as f:
        for s in stroki:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _vidennye():
    v = set()
    for fayl in (OUT, OTVAL):
        if os.path.exists(fayl):
            with open(fayl, encoding='utf-8') as f:
                for ln in f:
                    try:
                        v.add(json.loads(ln)['nomer'])
                    except Exception:
                        pass
    return v


def _url(q, ot, do, stranica):
    u = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
         '?searchString=%s&morphology=on&pageNumber=%d&recordsPerPage=_50'
         '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on'
         % (urllib.parse.quote(q), stranica))
    if ot:
        u += '&publishDateFrom=%s&publishDateTo=%s' % (ot, do)
    return u


def _schetchik(t):
    t = re.sub(r'\s+', ' ', t or '')
    m = (re.search(r'Результаты поиска\s*([\d \u00a0]{1,14})\s*запис', t)
         or re.search(r'([\d \u00a0]{2,14})\s*запис(?:ей|и|ь)', t))
    return int(re.sub(r'\D', '', m.group(1)) or 0) if m else None


def _okna(page, q, itog):
    """Год целиком, а где записей больше предела — тот же год по месяцам."""
    spisok = []
    for g in GODY:
        ot, do = '01.01.%d' % g, '31.12.%d' % g
        try:
            page.goto(_url(q, ot, do, 1), timeout=90000, wait_until='domcontentloaded')
            page.wait_for_timeout(2500)
            n = _schetchik(page.inner_text('body'))
        except Exception as e:
            itog['oshibki'].append('счёт %s %d: %s' % (q, g, str(e)[:100]))
            n = None
        if n is not None and n <= PREDEL_OKNA:
            if n:
                spisok.append((ot, do, n))
            continue
        # дробим на месяцы: 900 в год перебрано, месячное окно влезает в потолок
        for m in range(1, 13):
            posl = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
            spisok.append(('01.%02d.%d' % (m, g), '%02d.%02d.%d' % (posl, m, g), None))
    return spisok


def main():
    nach = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    skolko = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    moi = ZAPROSY[nach:nach + skolko]
    vid = _vidennye()
    prog = {}
    if os.path.exists(PROG):
        try:
            prog = json.load(open(PROG, encoding='utf-8'))
        except Exception:
            prog = {}
    itog = {'zaprosov': len(moi), 'okon': 0, 'stranic': 0, 'kartochek': 0,
            'prinyato': 0, 'otbrakovano': {}, 'oshibki': [], 'po_zaprosam': {}}
    from playwright.sync_api import sync_playwright
    exe = _hrom()
    with sync_playwright() as p:
        kw = {'headless': True, 'args': ['--no-sandbox',
                                         '--disable-blink-features=AutomationControlled']}
        if exe:
            kw['executable_path'] = exe
        br = p.chromium.launch(**kw)
        ctx = br.new_context(user_agent=UA, locale='ru-RU',
                             viewport={'width': 1366, 'height': 900},
                             ignore_https_errors=True)
        page = ctx.new_page()
        for q in moi:
            bylo = itog['prinyato']
            for (ot, do, skol) in _okna(page, q, itog):
                itog['okon'] += 1
                for n in range(1, STRANIC + 1):
                    klyuch = '%s|%s|%d' % (q, ot, n)
                    if prog.get(klyuch) == 'ok':
                        continue
                    try:
                        page.goto(_url(q, ot, do, n), timeout=90000,
                                  wait_until='domcontentloaded')
                        page.wait_for_timeout(2200)
                        html = page.content()
                    except Exception as e:
                        itog['oshibki'].append('%s %s стр.%d: %s' % (q, ot, n, str(e)[:100]))
                        continue
                    itog['stranic'] += 1
                    bloki = _BLOK.findall(html)
                    if not bloki:
                        prog[klyuch] = 'пусто'
                        break
                    paket, otval = [], []
                    for b in bloki:
                        itog['kartochek'] += 1
                        mn = _NOMER.search(b)
                        if not mn:
                            itog['otbrakovano']['нет реестрового номера'] = \
                                itog['otbrakovano'].get('нет реестрового номера', 0) + 1
                            continue
                        nomer = mn.group(1)
                        if nomer in vid:
                            itog['otbrakovano']['уже собран'] = \
                                itog['otbrakovano'].get('уже собран', 0) + 1
                            continue
                        mo = _OBJEKT.search(b)
                        mz = _ZAKAZ.search(b)
                        obj = _chisto(mo.group(1) if mo else '')
                        zak = _chisto(mz.group(1) if mz else '')
                        if not obj:
                            itog['otbrakovano']['объект закупки не распознан'] = \
                                itog['otbrakovano'].get('объект закупки не распознан', 0) + 1
                            continue
                        nobj = _bez_probelov(obj)
                        prichina = None
                        if not NASHE.search(nobj):
                            prichina = 'в объекте нет наших слов'
                        elif CHUZHOE.search(nobj):
                            prichina = 'чужое под тем же словом (быт/медицина/авто/холод)'
                        vid.add(nomer)
                        if prichina:
                            itog['otbrakovano'][prichina] = \
                                itog['otbrakovano'].get(prichina, 0) + 1
                            otval.append({'nomer': nomer, 'predmet': obj[:300],
                                          'prichina': prichina, 'zapros': q, 'okno': ot})
                            continue
                        paket.append({
                            'nomer': nomer, 'zakazchik': zak, 'predmet': obj[:600],
                            'zapros': q, 'okno': ot, 'stranica': n,
                            'ssylka_kartochka': _kartochka(nomer),
                            'ssylka_poisk':
                                'https://zakupki.gov.ru/epz/order/extendedsearch/'
                                'results.html?searchString=' + nomer,
                            'os': 'парк машин',
                            'kto': '1-я сессия, общий запрос по типу, окно публикации',
                            'ts': time.strftime('%Y-%m-%d %H:%M:%S')})
                    _zapisat(OUT, paket)
                    _zapisat(OTVAL, otval)
                    itog['prinyato'] += len(paket)
                    prog[klyuch] = 'ok'
                    json.dump(prog, open(PROG, 'w', encoding='utf-8'))
            itog['po_zaprosam'][q] = itog['prinyato'] - bylo
        br.close()
    json.dump(prog, open(PROG, 'w', encoding='utf-8'))
    itog['oshibki'] = itog['oshibki'][:10]
    print(json.dumps(itog, ensure_ascii=False))


if __name__ == '__main__':
    main()
