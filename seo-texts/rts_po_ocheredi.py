# -*- coding: utf-8 -*-
"""Закупки РТС-тендера по КАЖДОМУ предприятию очереди.

Шестая площадка. Вход — слаг `ИНН-КПП`, поэтому КПП обязателен; берём его из ЕГРЮЛ
(`centro/ochered-egrul.csv`, 829 предприятий очереди из 788 в очереди имеют КПП).

    https://www.rts-tender.ru/poisk/organizator/<ИНН>-<КПП>/?page=N

Обычный server-rendered HTML: ни `__NEXT_DATA__`, ни XHR для лотов нет. Внутренний ajax
(`/poisk/organizator/ajax/search`, `/poisk/api/organization/`) требует antiforgery-токен и
уводит на капчу — программного резолвера ИНН→КПП на самой площадке нет.

ДВЕ ЛОВУШКИ ЭТОЙ ПЛОЩАДКИ, обе стоят прогона:

1. `http_status` от раннера ВСЕГДА 503, даже когда страница пришла целиком (title верный,
   ИНН в теле, 10 карточек). Это артефакт обёртки, а не отказ площадки. Гейт по статусу
   выбросил бы всю выдачу. Поэтому решение принимается по СОДЕРЖИМОМУ, а не по статусу.
2. Первым ответом приходит страница «Anti-DDoS защита» (33 КБ). Она сама уходит на
   настоящую через несколько секунд, поэтому `wait_ms` = 20 000. С `wait_ms` 5 000
   стабильно приходит заглушка, и площадка выглядит закрытой.

Модуль сознательно НЕ использует `eval_js`: 03.08 около 19:45 раннер перестал его выполнять
(ключей `eval_js_*` в ответе нет при живой странице), и на этом разом встали два обхода.
Здесь скрипты не нужны — только разметка.

РАЗМЕТКА. 10 карточек на страницу. У каждой кнопки «ПОДРОБНЕЕ» атрибут `data-purchase-info`
с готовым JSON (`PurchaseId`, `RegistrationNumber`, `FederalLaw`), но `PurchaseName` там
ВСЕГДА null — название лежит отдельно в `card-item__title`. Атрибут встречается по два раза
на карточку, поэтому дедуп по `PurchaseId` обязателен, иначе выдача удваивается.

ОСТАНОВКА: первая страница, где 0 карточек (площадка отдаёт её как 25 КБ вместо 160 КБ).
Проверено: у Мосводоканала 11 страниц по 10 лотов, страницы 12…99 пусты.

КОНТРОЛЬ СУЖЕНИЯ, оба конца, на каждом прогоне:
    7701984274-770101001 (Мосводоканал) → 10 карточек на странице, все ИНН свои
    9999999999-999999999 (бессмыслица)  → 0 карточек
Плюс на каждой странице сверяется, что ИНН в блоках заказчика — только запрошенный.

ЧЕГО ЖДАТЬ ЧЕСТНО: не все предприятия найдутся по головному КПП из ЕГРЮЛ. У ТОАЗ
(6320004728) страницы нет ни по одному из пяти КПП — это проверено, и это не ошибка
подбора: предприятия на площадке нет вовсе. Такие уходят в журнал с пометкой, а не молча.

Использование:
    python3 rts_po_ocheredi.py --kontrol
    python3 rts_po_ocheredi.py --predel 20 --parallel 8
"""
import csv
import html as htmlmod
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
EGRUL = os.path.join(C, 'ochered-egrul.csv')
SBER = os.path.join(C, 'sber-inn-kpp.csv')
# Третий источник КПП — карта 3-й сессии (2 342 ИНН, через DaData). Она закрыла 4 из 23
# предприятий, которых не знали ни справочник Сбербанк-АСТ, ни наш ЕГРЮЛ-файл. Взято 04.08
# по прямой просьбе: вход на РТС возможен ТОЛЬКО по слагу ИНН-КПП, и без КПП канал закрыт.
KARTA_3S = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad/VAZHNOE-3s-KARTA-INN-KPP.csv'
VYHOD = os.path.join(C, 'rts-po-kompaniyam.csv')
KARTA = os.path.join(C, 'rts-obhod-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'nomer', 'predmet', 'zakon', 'summa', 'stadiya', 'data',
        'data_konca', 'ssylka', 'ssylka_eis']
STRANIC_MAX = 40          # 400 лотов на предприятие
ZHDAT = 20000             # мс: меньше — стабильно приходит заглушка Anti-DDoS


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def probe(url, tayminaut=400):
    zad = {'url': url, 'screenshot': False, 'proxy': '', 'return_html': True,
           'html_cap': 1500000, 'wait_ms': ZHDAT}
    try:
        p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                            json.dumps(zad, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=tayminaut)
    except subprocess.TimeoutExpired:
        return None, f'раннер не ответил за {tayminaut} с'
    try:
        d = json.loads(p.stdout[p.stdout.index('{'):]).get('data') or {}
    except (ValueError, json.JSONDecodeError):
        return None, (p.stdout or p.stderr or 'пустой ответ раннера')[-200:]
    h = d.get('html') or ''
    if not h:
        return None, (f"тело пусто. ключи: {','.join(sorted(d.keys()))} | "
                      f"http_status={d.get('http_status')} | error={str(d.get('error'))[:120]}")
    # По статусу не судим — он тут всегда 503. Судим по содержимому.
    if 'Anti-DDoS' in h and 'card-item__title' not in h:
        return None, 'вернулась заглушка Anti-DDoS — поднять wait_ms'
    return h, ''


KARTOCHKA = re.compile(r'data-purchase-info="([^"]{10,900})"')
NAZVANIE = re.compile(r'card-item__title"[^>]*>\s*(.*?)\s*</div>', re.S)
CENA = re.compile(r'itemprop="price" content="([\d.]+)"')
STATUS = re.compile(r'>СТАТУС</div>\s*<div class="card-item__properties-desc">\s*(.*?)\s*</div>',
                    re.S)
NACHALO = re.compile(r'availabilityStarts"\s*datetime="([^"]+)"')
KONEC = re.compile(r'availabilityEnds"\s*datetime="([^"]+)"')
EIS = re.compile(r'regNumber=(\d{9,25})')
INN_V_BLOKE = re.compile(r'ИНН\s*</b>\s*(\d{10,12})')


def bez_tegov(t):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', htmlmod.unescape(t or ''))).strip()


def razobrat(h):
    """Карточки страницы. Дедуп по PurchaseId обязателен: атрибут встречается дважды."""
    rows, bylo = [], set()
    mest = [m for m in KARTOCHKA.finditer(h)]
    for n, m in enumerate(mest):
        try:
            info = json.loads(htmlmod.unescape(m.group(1)))
        except json.JSONDecodeError:
            continue
        pid = info.get('PurchaseId') or ''
        if not pid or pid in bylo:
            continue
        bylo.add(pid)
        # Название и свойства лежат ПОСЛЕ кнопки, до следующей карточки.
        konec = mest[n + 1].start() if n + 1 < len(mest) else min(len(h), m.end() + 8000)
        blok = h[m.end():konec]
        nz = NAZVANIE.search(blok)
        st = STATUS.search(blok)
        c = CENA.search(blok)
        d1, d2 = NACHALO.search(blok), KONEC.search(blok)
        e = EIS.search(blok)
        rows.append({'nomer': info.get('RegistrationNumber') or '',
                     'predmet': bez_tegov(nz.group(1))[:300] if nz else '',
                     'zakon': {1: '223-ФЗ', 0: '44-ФЗ'}.get(info.get('FederalLaw'),
                                                            str(info.get('FederalLaw') or '')),
                     'summa': c.group(1) if c else '',
                     'stadiya': bez_tegov(st.group(1)) if st else '',
                     'data': (d1.group(1)[:10] if d1 else ''),
                     'data_konca': (d2.group(1)[:10] if d2 else ''),
                     'ssylka': 'https://www.rts-tender.ru/poisk/id/' + pid + '/',
                     'ssylka_eis': ('https://zakupki.gov.ru/epz/order/notice/notice223/'
                                    'common-info.html?regNumber=' + e.group(1)) if e else ''})
    return rows


def odno_predpriyatie(inn, kpp, stranic):
    baza = f'https://www.rts-tender.ru/poisk/organizator/{inn}-{kpp}/'
    rows, chuzhih, oborvano = [], 0, ''
    for p in range(1, stranic + 1):
        h, err = probe(baza + f'?page={p}')
        if h is None:
            if p == 1:
                return None, err
            oborvano = err
            break
        kus = razobrat(h)
        if not kus:
            if p == 1 and str(inn) not in h:
                # ни карточек, ни ИНН в теле — предприятия по этому КПП на площадке нет
                return {'vsego': 0, 'rows': [], 'net_stranicy': True, 'chuzhih': 0,
                        'oborvano': ''}, ''
            break
        chuzhih += sum(1 for x in set(INN_V_BLOKE.findall(h)) if x != str(inn))
        rows.extend(kus)
        time.sleep(0.4)
    return {'vsego': len(rows), 'rows': rows, 'net_stranicy': False, 'chuzhih': chuzhih,
            'oborvano': oborvano}, ''


def main():
    predel = dovod('--predel', 10 ** 9)
    parallel = dovod('--parallel', 8)
    # Предел раннера: сверх 30 воркеров задачи не работают, а ждут.
    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    stranic = dovod('--stranic', STRANIC_MAX)

    och = chitat(OCHERED)
    if len(och) < 300:
        sys.exit(f'ОСТАНОВКА: очередь {len(och)} строк — пересоберите базу перед обходом.')
    imena = {r['inn']: r.get('predpriyatie') or '' for r in och}
    # КПП: сначала справочник Сбербанк-АСТ (там КПП именно площадочные), потом ЕГРЮЛ.
    kpp = {}
    for r in chitat(SBER):
        if r.get('kpp') and r['inn'] in imena:
            kpp.setdefault(r['inn'], r['kpp'])
    iz_egrul = 0
    for r in chitat(EGRUL):
        if r['inn'] in imena and r['inn'] not in kpp and (r.get('kpp') or '').strip():
            kpp[r['inn']] = r['kpp'].strip()
            iz_egrul += 1
    iz_3s = 0
    for r in chitat(KARTA_3S):
        if r['inn'] in imena and r['inn'] not in kpp and (r.get('kpp') or '').strip():
            kpp[r['inn']] = r['kpp'].strip()
            iz_3s += 1

    proydeno = {r['inn'] for r in chitat(KARTA)}
    celi = [{'inn': i, 'kpp': k, 'predpriyatie': imena[i]}
            for i, k in kpp.items() if i not in proydeno][:predel]
    bez_kpp = [i for i in imena if i not in kpp]

    bred, err = probe('https://www.rts-tender.ru/poisk/organizator/9999999999-999999999/?page=1')
    if bred is not None and razobrat(bred):
        sys.exit(f'КОНТРОЛЬ ПРОВАЛЕН: бессмыслица вернула {len(razobrat(bred))} карточек')
    zhivoy, err2 = probe('https://www.rts-tender.ru/poisk/organizator/'
                         '7701984274-770101001/?page=1')
    if zhivoy is None or not razobrat(zhivoy):
        sys.exit('КОНТРОЛЬ ПРОВАЛЕН: заведомо непустой организатор (Мосводоканал) дал ноль '
                 f'карточек — площадка отдаёт пусто всем. {err2}')
    print(f'[РТС-тендер] контроль: бессмыслица 0, Мосводоканал {len(razobrat(zhivoy))} '
          f'карточек на странице | к обходу {len(celi)} (из ЕГРЮЛ {iz_egrul}), '
          f'без КПП вообще {len(bez_kpp)}, пройдено {len(proydeno)}', file=sys.stderr)
    if '--kontrol' in sys.argv or not celi:
        return

    novyy_v = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    novyy_k = not os.path.exists(KARTA) or os.path.getsize(KARTA) == 0
    fv = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    fk = open(KARTA, 'a', encoding='utf-8-sig', newline='')
    wk = csv.DictWriter(fk, fieldnames=['inn', 'kpp', 'predpriyatie', 'vzyato', 'pochemu'],
                        delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'предприятий': 0, 'лотов': 0, 'нет на площадке': 0, 'обрезано потолком': 0,
           'чужих ИНН': 0, 'сбоев': 0}
    lock = threading.Lock()

    def odno(c):
        return c, odno_predpriyatie(c['inn'], c['kpp'], stranic)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for nomer, (c, (sv, err)) in enumerate(pool.map(odno, celi), 1):
            with lock:
                if sv is None:
                    sch['сбоев'] += 1
                    print(f'  СБОЙ {c["inn"]}: {err[:140]}', file=sys.stderr, flush=True)
                    continue
                sch['предприятий'] += 1
                rows = sv['rows']
                sch['лотов'] += len(rows)
                if sv['net_stranicy']:
                    sch['нет на площадке'] += 1
                sch['чужих ИНН'] += sv['chuzhih']
                obrezano = len(rows) >= stranic * 10
                if obrezano:
                    sch['обрезано потолком'] += 1
                pochemu = 'обойдено'
                if sv['net_stranicy']:
                    pochemu = f'нет страницы по КПП {c["kpp"]} — предприятия на площадке нет'
                elif sv['oborvano']:
                    pochemu = 'ОБОРВАЛОСЬ: ' + str(sv['oborvano'])[:120]
                elif obrezano:
                    pochemu = f'ВЗЯТО НЕ ВСЁ: упёрлись в потолок {stranic} страниц'
                elif sv['chuzhih']:
                    pochemu = f'в выдаче {sv["chuzhih"]} чужих ИНН — проверить'
                wk.writerow({'inn': c['inn'], 'kpp': c['kpp'],
                             'predpriyatie': c['predpriyatie'], 'vzyato': len(rows),
                             'pochemu': pochemu})
                for x in rows:
                    wv.writerow(dict(x, inn=c['inn'], predpriyatie=c['predpriyatie']))
                fv.flush()
                fk.flush()
                if nomer % 20 == 0 or rows:
                    print(f'  [rts] {nomer}/{len(celi)}: {sch}', file=sys.stderr, flush=True)

    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}\n→ {KARTA}', file=sys.stderr)
    if bez_kpp:
        print(f'НЕ СПРОШЕНЫ {len(bez_kpp)} предприятий: КПП неизвестен ни площадке Сбера, '
              'ни ЕГРЮЛ', file=sys.stderr)


if __name__ == '__main__':
    main()
