# -*- coding: utf-8 -*-
"""Закупки ТЭК-Торга по КАЖДОМУ предприятию очереди.

Четвёртая площадка после Tender.pro, ЭТП ГПБ и Росэлторга. Вход, как и у Росэлторга,
ПРЯМО ПО ИНН — справочник площадки не нужен, адресуемы все предприятия очереди.

ЧЕМ БЕРЁМ. Площадка на Next.js, и разбирать HTML не нужно: у неё есть чистый data-route,
отдающий тот же JSON без разметки (снято агентом живыми запросами 03.08):

    https://www.tektorg.ru/_next/data/<buildId>/ru/procedures.json?organizer[]=<ИНН>&page=<N>
    → pageProps.initialReduxState.listingProcedures.{total, totalPages, limitPage, data[]}

`buildId` берётся ДИНАМИЧЕСКИ из `__NEXT_DATA__.buildId` открытой страницы: при редеплое
площадки он меняется, зашитый в код превратится в 404 и это будет выглядеть как «площадка
закрылась». Сегодняшнее значение 1b96cdab… в код НЕ записано намеренно.

Сквозной раздел `/procedures` индексирует все семь секций сразу (1 423 969 процедур против
169 802 в 223-ФЗ), поэтому ходим по нему, а не по секциям по очереди — в отличие от ЭТП ГПБ,
где секции пришлось спрашивать поштучно.

КОНТРОЛЬ СУЖЕНИЯ пройден агентом до написания модуля, но повторяется здесь на каждом прогоне,
потому что дважды за сутки площадки меняли поведение молча:
    без фильтра                 1 423 969
    organizer[]=7708503727            604   (РЖД)
    organizer[]=9999999999              0   ← бессмыслица, фильтр настоящий
    organizer[]=                        0   ← ПУСТОЕ значение НЕ снимает фильтр, а обнуляет
Последняя строка — обратная ловушка к ЭТП ГПБ и Tender.pro, где пустое значение отдавало
реестр целиком. Здесь наоборот, но вывод тот же: пустое значение недопустимо.

ЛОВУШКИ, найденные при снятии разметки (каждая стоила бы прогона):
  * `currentPage` в ответе ВСЕГДА 1, какую бы страницу ни запросили. Ориентир — запрошенный
    номер, а не это поле.
  * `limit` / `limitPage` / `perPage` игнорируются: 15 записей на страницу снять нельзя.
  * ИНН организатора в карточке НЕТ — только `organizerName`. Принадлежность подтверждается
    тем, что фильтр применён (проверяем: все `organizerName` в выдаче одинаковы).
  * Ссылка строится по-разному: `/org/<subsectionAlias>/procedures/<id>` у организаторов со
    своей витриной (РЖД, Юнипро, Росморпорт), иначе `/<sectionAlias>/procedures/<id>`.
    Регулярка по одному лишь второму виду даёт ноль на крупных заказчиках.
  * Антибот включается примерно после 15 быстрых запросов подряд. Паузы 2,5 с безопасны.

Ноль процедур — нормальный ответ, а не сбой разбора: у АО «СИБУРТЮМЕНЬГАЗ» (7202116628)
карточка организатора на площадке есть, а закупок ноль во всех семи секциях.

ПОЧЕМУ БЕЗ eval_js. 03.08 около 19:45 раннер перестал выполнять `eval_js` — ключей
`eval_js_*` в ответе просто нет, при `http_status: 200` и живой странице. Оборвались разом
и этот обход (на 30-м предприятии), и обход Портала Москвы. Модуль переписан на ход, который
работает без выполнения скриптов вообще: браузер ВЕДЁТСЯ на сам data-route, тело ответа —
чистый JSON в `<pre>`, разбор на нашей стороне. Заодно это устойчивее: одна точка отказа
вместо двух.

ЛОВУШКА РАЗБОРА, поймана здесь же: регулярка `"total":(\d+)` по телу ответа даёт 36 421 для
запроса, где процедур 604 — первым в JSON лежит чужой `total`. Поэтому JSON разбирается
целиком и число берётся строго по пути `pageProps.initialReduxState.listingProcedures.total`.

Использование:
    python3 tektorg_po_ocheredi.py --kontrol
    python3 tektorg_po_ocheredi.py --predel 20
    python3 tektorg_po_ocheredi.py --stranic 60 --parallel 4
"""
import csv
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
VYHOD = os.path.join(C, 'tektorg-po-kompaniyam.csv')
KARTA = os.path.join(C, 'tektorg-obhod-zhurnal.csv')

# --- P25 (покупатели 2025) ---------------------------------------------------------------
# Та же площадка, другой список предприятий и другие файлы. Пути переопределяются ОКРУЖЕНИЕМ,
# а не форком модуля: форк разошёлся бы с оригиналом на первой же правке ловушек площадки, а
# ловушки здесь — половина ценности файла. Без переменных поведение прежнее, байт в байт.
OCHERED = os.environ.get('P25_OCHERED', OCHERED)
VYHOD = os.environ.get('P25_VYHOD', VYHOD)
KARTA = os.environ.get('P25_KARTA', KARTA)

COLS = ['inn', 'predpriyatie', 'nomer', 'predmet', 'organizator', 'vid', 'summa', 'data',
        'data_konca', 'stadiya', 'sekciya', 'podsekciya', 'id_processa', 'ssylka',
        'ssylka_etp']
STRANIC_MAX = 40          # 600 процедур на предприятие; крупнее в очереди почти никого


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


BUILD_URL = 'https://www.tektorg.ru/procedures'
PAUZA = 2.5              # антибот площадки: включается примерно после 15 быстрых запросов


def probe(url, cap=900000, wait=4000, tayminaut=400):
    """Один заход браузера. Возвращает (telo, oshibka). Тело — то, что реально пришло."""
    zad = {'url': url, 'screenshot': False, 'proxy': '', 'return_html': True,
           'html_cap': cap, 'wait_ms': wait}
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
    if d.get('html_truncated'):
        return None, (f'ответ обрезан: {d.get("html_full_len")} знаков при потолке {cap} — '
                      'поднять html_cap, иначе JSON не разберётся')
    return h, ''


def json_iz_tela(h):
    """Браузер показывает JSON внутри <pre>. Разбираем целиком, а не регуляркой по полям:
    первым в этом JSON лежит ЧУЖОЙ ключ `total`, и регулярка возвращала 36 421 вместо 604."""
    i, j = h.find('<pre>'), h.rfind('</pre>')
    kus = h[i + 5:j] if (i >= 0 and j > i) else h
    kus = (kus.replace('&quot;', '"').replace('&amp;', '&')
              .replace('&lt;', '<').replace('&gt;', '>'))
    try:
        return json.loads(kus), ''
    except json.JSONDecodeError as e:
        return None, f'JSON не разобран: {str(e)[:80]} | начало: {kus[:120]}'


def spisok(o):
    """Строго по пути, а не поиском по имени поля."""
    return ((o.get('pageProps') or {}).get('initialReduxState') or {}).get('listingProcedures')


def vzyat_build():
    h, err = probe(BUILD_URL, cap=1200000, wait=6000)
    if h is None:
        return None, err
    m = re.search(r'"buildId":"([0-9a-f]{8,})"', h)
    return (m.group(1), '') if m else (None, 'buildId не найден в __NEXT_DATA__')


def stranica(build, inn, p):
    u = ('https://www.tektorg.ru/_next/data/' + build +
         '/ru/procedures.json?organizer%5B%5D=' + str(inn) + '&page=' + str(p))
    h, err = probe(u)
    if h is None:
        return None, err
    o, err = json_iz_tela(h)
    if o is None:
        return None, err
    l = spisok(o)
    if l is None:
        return None, 'в ответе нет listingProcedures — сменился путь или устарел buildId'
    return l, ''


# Настоящие маршруты сняты с _buildManifest.js самой площадки, а не угаданы по alias.
# Проверено: `/org/vitrine/procedures/<id>` и `/44fz/procedures/<id>` отдают 404 —
# в манифесте таких путей нет вовсе, есть `/44-fz/` через ДЕФИС и `/vitrina/`, не `/vitrine/`.
# Из-за угаданной формы 3 347 уже собранных ссылок ведут в никуда. Поэтому теперь в файл
# кладутся сырой id и оба алиаса: ссылку можно пересобрать, не переобходя площадку.
MARSHRUTY = {'44fz': '44-fz', '44_fz': '44-fz', '223fz': '223-fz', '223_fz': '223-fz',
             'zakupki': '223-fz', 'vitrine': 'vitrina'}


def szhat(d):
    sek = d.get('sectionAlias') or ''
    pod = d.get('subsectionAlias') or ''
    marshrut = MARSHRUTY.get(sek, sek)
    put = '/%s/procedures/%s' % (marshrut or 'procedures', d.get('id'))
    dates = d.get('dates') or {}
    return {'n': d.get('registryNumber') or '', 't': (d.get('title') or '')[:300],
            'o': d.get('organizerName') or '', 'v': d.get('typeName') or '',
            's': d.get('sumPrice') or '', 'dp': (dates.get('datePublished') or '')[:10],
            'dk': (dates.get('dateEndRegistration') or '')[:10],
            'st': d.get('statusName') or '', 'sek': sek, 'pod': pod,
            'id': d.get('id') or '', 'u': put, 'etp': d.get('etpLink') or ''}


def odno_predpriyatie(build, inn, stranic):
    """Все процедуры одного ИНН. Возвращает (svodka, oshibka)."""
    l, err = stranica(build, inn, 1)
    if l is None:
        return None, err
    vsego = l.get('total') or 0
    vsego_str = l.get('totalPages') or 0
    rows = [szhat(d) for d in (l.get('data') or [])]
    berem = min(vsego_str, stranic)
    for p in range(2, berem + 1):
        time.sleep(PAUZA)
        l2, err2 = stranica(build, inn, p)
        if l2 is None:
            return {'vsego': vsego, 'stranic_vsego': vsego_str, 'vzyato_stranic': p - 1,
                    'rows': rows, 'oborvano': err2}, ''
        rows.extend(szhat(d) for d in (l2.get('data') or []))
    imena = sorted({r['o'] for r in rows if r['o']})
    return {'vsego': vsego, 'stranic_vsego': vsego_str, 'vzyato_stranic': berem,
            'rows': rows, 'imen': len(imena), 'imya': imena[0] if imena else ''}, ''


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
    proydeno = {r['inn'] for r in chitat(KARTA)}
    celi = [{'inn': r['inn'], 'predpriyatie': r.get('predpriyatie') or ''}
            for r in och if r['inn'] not in proydeno][:predel]

    build, err = vzyat_build()
    if not build:
        sys.exit(f'ОСТАНОВКА: не взят buildId — {err}')
    print(f'[ТЭК-Торг] build={build}, к обходу {len(celi)} (пройдено {len(proydeno)})',
          file=sys.stderr)

    # КОНТРОЛЬ СУЖЕНИЯ на каждом прогоне, оба конца: бессмыслица обязана дать 0, а заведомо
    # непустой организатор — не 0. Один только первый конец не ловит случай «площадка молча
    # отдаёт пусто всем подряд», а он у нас уже был на трёх площадках.
    bred, err = stranica(build, '9999999999', 1)
    if bred is None:
        sys.exit(f'ОСТАНОВКА: контрольный запрос не прошёл — {err}')
    if (bred.get('total') or 0) > 0:
        sys.exit(f'КОНТРОЛЬ ПРОВАЛЕН: бессмыслица вернула total={bred.get("total")}')
    time.sleep(PAUZA)
    zhivoy, err = stranica(build, '7708503727', 1)
    if zhivoy is None or (zhivoy.get('total') or 0) == 0:
        sys.exit('КОНТРОЛЬ ПРОВАЛЕН: заведомо непустой организатор (РЖД) дал ноль — '
                 f'площадка отдаёт пусто всем. {err}')
    print(f'контроль: бессмыслица {bred.get("total")}, РЖД {zhivoy.get("total")}',
          file=sys.stderr)
    if '--kontrol' in sys.argv or not celi:
        return

    novyy_v = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    novyy_k = not os.path.exists(KARTA) or os.path.getsize(KARTA) == 0
    fv = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    fk = open(KARTA, 'a', encoding='utf-8-sig', newline='')
    wk = csv.DictWriter(fk, fieldnames=['inn', 'predpriyatie', 'vsego', 'vzyato', 'pochemu'],
                        delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'предприятий': 0, 'процедур': 0, 'пусто': 0, 'обрезано потолком': 0,
           'чужие в выдаче': 0, 'сбоев': 0}
    lock = threading.Lock()

    def odno(c):
        return c, odno_predpriyatie(build, c['inn'], stranic)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for nomer, (c, (sv, err)) in enumerate(pool.map(odno, celi), 1):
            with lock:
                if sv is None:
                    sch['сбоев'] += 1
                    print(f'  СБОЙ {c["inn"]}: {err[:150]}', file=sys.stderr, flush=True)
                    if nomer % 20 == 0:
                        print(f'  [tektorg] {nomer}/{len(celi)}: {sch}',
                              file=sys.stderr, flush=True)
                    continue
                sch['предприятий'] += 1
                rows = sv['rows']
                sch['процедур'] += len(rows)
                if not rows:
                    sch['пусто'] += 1
                # Молчаливых потолков не бывает: недобор всегда попадает в журнал.
                obrezano = sv['stranic_vsego'] > sv['vzyato_stranic']
                if obrezano:
                    sch['обрезано потолком'] += 1
                if (sv.get('imen') or 0) > 1:
                    sch['чужие в выдаче'] += 1
                pochemu = 'обойдено'
                if sv.get('oborvano'):
                    pochemu = 'ОБОРВАЛОСЬ на середине: ' + str(sv['oborvano'])[:120]
                elif obrezano:
                    pochemu = (f'ВЗЯТО НЕ ВСЁ: страниц {sv["stranic_vsego"]}, '
                               f'взято {sv["vzyato_stranic"]} — поднять --stranic')
                elif (sv.get('imen') or 0) > 1:
                    pochemu = f'в выдаче {sv["imen"]} разных организаторов — проверить'
                wk.writerow({'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                             'vsego': sv['vsego'], 'vzyato': len(rows), 'pochemu': pochemu})
                for x in rows:
                    wv.writerow({'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                                 'nomer': x['n'], 'predmet': x['t'], 'organizator': x['o'],
                                 'vid': x['v'], 'summa': x['s'], 'data': x['dp'],
                                 'data_konca': x['dk'], 'stadiya': x['st'],
                                 'sekciya': x['sek'], 'podsekciya': x['pod'],
                                 'id_processa': x['id'],
                                 'ssylka': 'https://www.tektorg.ru' + x['u'],
                                 'ssylka_etp': x['etp']})
                fv.flush()
                fk.flush()
                if nomer % 20 == 0 or sv['vsego']:
                    print(f'  [tektorg] {nomer}/{len(celi)}: {sch}', file=sys.stderr, flush=True)

    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}\n→ {KARTA}', file=sys.stderr)
    if sch['обрезано потолком']:
        print(f'ВНИМАНИЕ: у {sch["обрезано потолком"]} предприятий взято не всё — '
              'перезапустить с большим --stranic', file=sys.stderr)


if __name__ == '__main__':
    main()
