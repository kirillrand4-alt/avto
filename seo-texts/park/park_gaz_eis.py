# -*- coding: utf-8 -*-
"""Сбор ДОКАЗАТЕЛЬСТВА РАСХОДА газа из ЕИС (zakupki.gov.ru). Работает НА СЕРВЕРЕ владельца.

Зачем: целевой покупатель генератора азота/кислорода — это тот, кто ГАЗ ПОКУПАЕТ
(баллоны, жидкий, криоцистерна, аренда), а не тот, у кого генератор уже стоит.
На троих эта ось была закрыта на 2 предприятиях: её никто не собирал.

Почему браузером: у zakupki.gov.ru сертификат от НУЦ Минцифры, обычный клиент рвётся.
Приём 2-й сессии — Playwright с ignore_https_errors. Проверено: страница отдаётся, 200.

ДОЛГОВЕЧНОСТЬ (урок смены): пишем в СЕРВЕРНЫЙ C:\\sender\\park_gaz.jsonl построчно
с fsync, а не только в возвращаемый JSON. Песочница при рестарте откатывается — сервер нет.
РЕЗЮМИРУЕМОСТЬ: уже виденные реестровые номера пропускаем, страницы-запросы отмечаем
в C:\\sender\\park_gaz_progress.json.

Запуск: panel_py, argv = [<индекс первого запроса>, <сколько запросов за вызов>]
"""
import json, os, re, sys, time, urllib.parse

BAZA = r'C:\sender'
OUT = os.path.join(BAZA, 'park_gaz.jsonl')
PROG = os.path.join(BAZA, 'park_gaz_progress.json')
OTVAL = os.path.join(BAZA, 'park_gaz_otval.jsonl')   # урок 2-й: счётчик выхода
                                                     # не знает про отвал
STRANIC = 20           # страниц на запрос, по 50 записей
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

# Запросы: только ПОКУПКА/АРЕНДА газа. Слова про генераторы и станции сюда не берём —
# это другая ось, она у нас уже собрана.
ZAPROSY = [
    'кислород жидкий технический',
    'кислород газообразный технический',
    'кислород медицинский газообразный',
    'поставка кислорода в баллонах',
    'азот жидкий',
    'азот газообразный технический',
    'поставка азота в баллонах',
    'аренда баллонов кислородных',
    'криоцистерна',
    'заправка кислородных баллонов',
    'моноблок кислородный',
    'азот особой чистоты',
    'кислород технический в баллонах 40 л',
    'жидкий азот поставка',
    'поставка технических газов',
    'газы технические поставка',
    'кислород медицинский',
    'газификатор холодный',
]

# Строгий отбор по ОБЪЕКТУ закупки: поиск ЕИС с морфологией тащит мусор
# (ремонт автотранспорта, обрезка деревьев) — тот же капкан, на котором 3-я собрала 40% брака.
#
# ЗАМЕР 09.08: первая версия заслона выбросила ЗРЯ 3 704 строки из 7 157. Причина —
# ЕИС РВЁТ СЛОВА ПРОБЕЛАМИ для подсветки совпадений: «жидк ого азот а», «техническ их
# газов», «кислород а газообразн ого». Регэксп требовал целых слов и не видел цели.
# Лечение: сравниваем по строке БЕЗ пробелов вовсе — тогда разрыв слова не мешает.
def _bez_probelov(t):
    return re.sub(r'\s+', '', (t or '').lower().replace('\u0451', '\u0435'))


GAZ = re.compile(
    r'(жидк\w{0,4}(азот|кислород|аргон|гелий))|((азот|кислород)\w{0,4}жидк)|'
    r'(газообразн\w{0,4}(азот|кислород))|((азот|кислород)\w{0,4}газообразн)|'
    r'баллон|криоцистерн|моноблок|газификатор|'
    r'(техническ\w{0,4}газ)|(газ\w{0,4}техническ)|'
    r'(поставкагазов)|(газовойпродукции)|(промышленныхгазов)|(газовособойчистоты)|'
    r'((кислород|азот)\w{0,4}техническ)|(техническ\w{0,4}(кислород|азот))|'
    r'((кислород|азот)\w{0,4}медицинск)|(медицинск\w{0,4}(кислород|азот))')
# Явные исключения: покупка САМОЙ машины, её ремонт и однокоренной чужой мусор.
NE_RASHOD = re.compile(
    r'(генератор\w{0,4}(азота|кислорода))|(кислородн\w{0,4}станци)|(азотн\w{0,4}станци)|'
    r'воздухоразделительн|концентратор|компрессор|(ремонт\w{0,4}баллон)|поверк|'
    r'освидетельствован|хроматограф|лекарственн|(техническ\w{0,4}жидкост)')
_ZAP = re.compile(r'(?i)(?:\bслов[оа]\b|искать)')


def _hrom():
    for k in (r'C:\sender\pw-browsers', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')):
        if not k or not os.path.isdir(k):
            continue
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


def _zapisat(stroki):
    """Долговечная запись: строка -> файл -> flush -> fsync. Иначе рестарт съест."""
    if not stroki:
        return
    with open(OUT, 'a', encoding='utf-8') as f:
        for s in stroki:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _vidennye():
    v = set()
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            for ln in f:
                try:
                    v.add(json.loads(ln)['nomer'])
                except Exception:
                    pass
    return v


# карточки в выдаче ЕИС: номер -> ссылка, объект закупки, заказчик
_BLOK = re.compile(r'search-registry-entry-block.*?(?=search-registry-entry-block|$)', re.S)
_NOMER = re.compile(r'regNumber=(\d{8,})')
_OBJEKT = re.compile(r'Объект закупки\s*</div>\s*<div[^>]*>\s*(?:<a[^>]*>)?\s*(.*?)\s*(?:</a>)?\s*</div>', re.S)
_ZAKAZ = re.compile(r'(?:Заказчик|Организация, осуществляющая закупку)\s*</div>\s*<div[^>]*>\s*<a[^>]*>\s*(.*?)\s*</a>', re.S)
_TEG = re.compile(r'<[^>]+>')


def _chisto(s):
    s = _TEG.sub(' ', s or '')
    s = s.replace('&quot;', '"').replace('&laquo;', '«').replace('&raquo;', '»')
    s = s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#39;', "'")
    return re.sub(r'\s+', ' ', s).strip()


def main():
    nach = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    skolko = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    moi = ZAPROSY[nach:nach + skolko]
    vid = _vidennye()
    prog = {}
    if os.path.exists(PROG):
        try:
            prog = json.load(open(PROG, encoding='utf-8'))
        except Exception:
            prog = {}
    itog = {'zaprosov': len(moi), 'stranic': 0, 'kartochek': 0, 'prinyato': 0,
            'otbrakovano': {}, 'oshibki': []}
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
            for n in range(1, STRANIC + 1):
                klyuch = '%s|%d' % (q, n)
                if prog.get(klyuch) == 'ok':
                    continue
                u = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
                     '?searchString=%s&morphology=on&pageNumber=%d&recordsPerPage=_50'
                     '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on'
                     % (urllib.parse.quote(q), n))
                try:
                    page.goto(u, timeout=60000, wait_until='domcontentloaded')
                    page.wait_for_timeout(2500)
                    html = page.content()
                except Exception as e:
                    itog['oshibki'].append('%s стр.%d: %s' % (q, n, str(e)[:120]))
                    continue
                itog['stranic'] += 1
                bloki = _BLOK.findall(html)
                if not bloki:
                    prog[klyuch] = 'пусто'
                    break
                paket = []
                otval = []
                for b in bloki:
                    itog['kartochek'] += 1
                    mn = _NOMER.search(b)
                    mo = _OBJEKT.search(b)
                    mz = _ZAKAZ.search(b)
                    if not mn:
                        itog['otbrakovano']['нет реестрового номера'] = \
                            itog['otbrakovano'].get('нет реестрового номера', 0) + 1
                        continue
                    nomer = mn.group(1)
                    obj = _chisto(mo.group(1) if mo else '')
                    zak = _chisto(mz.group(1) if mz else '')
                    if nomer in vid:
                        itog['otbrakovano']['уже собран'] = \
                            itog['otbrakovano'].get('уже собран', 0) + 1
                        continue
                    if not obj:
                        itog['otbrakovano']['объект закупки не распознан'] = \
                            itog['otbrakovano'].get('объект закупки не распознан', 0) + 1
                        continue
                    nobj = _bez_probelov(obj)
                    if not GAZ.search(nobj):
                        itog['otbrakovano']['в объекте нет слов о газе'] = \
                            itog['otbrakovano'].get('в объекте нет слов о газе', 0) + 1
                        otval.append({'nomer': nomer, 'predmet': obj[:300],
                                      'prichina': 'в объекте нет слов о газе', 'zapros': q})
                        continue
                    if NE_RASHOD.search(nobj):
                        itog['otbrakovano']['это машина/сервис, не расход'] = \
                            itog['otbrakovano'].get('это машина/сервис, не расход', 0) + 1
                        otval.append({'nomer': nomer, 'predmet': obj[:300],
                                      'prichina': 'это машина/сервис, не расход', 'zapros': q})
                        continue
                    vid.add(nomer)
                    paket.append({
                        'nomer': nomer, 'zakazchik': zak, 'predmet': obj[:600],
                        'zapros': q, 'stranica': n,
                        'ssylka_kartochka':
                            'https://zakupki.gov.ru/epz/order/notice/notice-info/common-info.html?noticeInfoId=&regNumber=' + nomer,
                        'ssylka_poisk':
                            'https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=' + nomer,
                        'os': 'расход газа',
                        'kto': '1-я сессия, ЕИС через серверный браузер (ignore_https_errors)',
                        'ts': time.strftime('%Y-%m-%d %H:%M:%S')})
                _zapisat(paket)
                if otval:
                    with open(OTVAL, 'a', encoding='utf-8') as f:
                        for o in otval[:60]:
                            f.write(json.dumps(o, ensure_ascii=False) + '\n')
                        f.flush(); os.fsync(f.fileno())
                itog['prinyato'] += len(paket)
                prog[klyuch] = 'ok'
                with open(PROG, 'w', encoding='utf-8') as f:
                    json.dump(prog, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
        br.close()
    itog['vsego_v_fayle'] = len(_vidennye())
    print(json.dumps(itog, ensure_ascii=False))


if __name__ == '__main__':
    main()
