# -*- coding: utf-8 -*-
"""Ранний источник 1: ФРП (frprf.ru). Реестр профинансированных проектов + лента.

ЧТО ЭТО ДАЁТ. Выданный заём ФРП - подтверждённый капекс на стадии финансирования:
деньги на цех уже выделены, оборудование ещё не куплено.

ГДЕ ЛЕЖИТ РЕЕСТР, и почему не там, где ожидалось (замер 16.09.2026):

    /zaymy/                 200, 58 812 байт - это ОПИСАНИЕ ПРОГРАММ (условия,
                            ставки, документы). Ни одного ИНН, ни одного заёмщика.
                            Реестром не является
    /klienty/  и  /klienty/<id>/     **301 -> https://frprf.ru**. Раздел снят с сайта.
                            В sitemap-iblock-31.xml он ещё числится, 706 адресов,
                            и все 706 сегодня редиректят на главную. Отдельно
                            отмечаю ловушку: с автоматическим следованием за
                            редиректом это выглядит как «200, 207 595 байт»,
                            то есть как живая страница, и ровно так я и ошиблась
                            в первый раз. Различается только запросом БЕЗ следования
    /istorii-uspekha/<id>/  200, ~60 000 байт. ВОТ ЭТО РЕЕСТР: структурированная
                            карточка профинансированного проекта
    /proekty-i-zayavki/     301 -> главная (адрес взят из /asset/vmap/vmap_fact2.js,
                            то есть в коде фронта он устарел)

ЧТО В КАРТОЧКЕ ЕСТЬ (проверено поимённо на живых карточках):

    заёмщик ............. h1, например АО "ДМЗ", ООО "НАНОЛЕК"
    назначение .......... «Производство вакцины против вируса папилломы человека»
    программа ........... «Проекты развития», «Транспортное машиностроение»
    год выдачи займа .... 2022, 2025
    регион, муниципалитет «Кировская область», «Лёвинцы»
    отрасль ............. «Машиностроение», «Медбиофарма» - ложится прямо на
                          список приоритетных отраслей владельца
    бюджет проекта ...... «2.4 млрд руб»
    сумма займа ......... «949 млн руб»
    ЧЕЛОВЕК ............. блок div.item-review-rep: div.name + div.post + цитата,
                          например «Евгений Баринов / Генеральный директор».
                          Это ЛПР по имени, с должностью и цитатой
    ИНН ................. НЕТ. Добывается вторым шагом через dadata по названию

МАШИННОГО ИНТЕРФЕЙСА У САЙТА НЕТ, и это проверено, а не предположено:
    - сайт на Bitrix, в html только /bitrix/tools/conversion/ajax_counter.php;
    - /bitrix/services/main/ajax.php отвечает 200 и телом
      {"status":"error", ... "Could not find des...} - то есть точка жива,
      но зарегистрированных под неё компонентов нет;
    - /api/, /opendata/, /zaymy/reestr/ - 404;
    - собственные скрипты фронта (/asset/js/main.js, /asset/vmap/*.js) адресов
      данных не содержат, карта регионов рисуется по переменной region_js,
      которую в html не кладут;
    - ЕДИНСТВЕННЫЕ найденные API-хосты - bod.frprf.ru и id-api.frprf.ru.
      Это ВНУТРЕННЯЯ система фонда: Vue-приложение с OIDC-авторизацией,
      в бандле VUE_APP_LOAN_*_API_URL, VUE_APP_TRANCHES_API_URL,
      VUE_APP_TROUBLED_BORROWER_API_URL, VUE_APP_HR_KPI_API_URL.
      Туда не ходила и ходить нельзя: это не открытые данные, это бэк-офис.

ЗАСЛОН ХОСТА, И ПОЧЕМУ ЕГО НАДО ВИДЕТЬ. DDoS-Guard держит частотный лимит:
подряд без пауз из 150 карточек открылось 31, с паузой 1,5 с из 70 открылось 8.
Старый коллектор `col_frp` в news_scan.py делал `if not html: continue`, то есть
**отказ хоста превращался в пустой список и был неотличим от «новостей нет»**.
Здесь это вылечено: каждый запрос считается, отказы копятся по кодам, есть ретрай
с растущей паузой, и в конце печатается строка
«запрошено N, отдано 200 у M, отказов: {503: K}». Пока K не ноль, любые числа
канала ЗАНИЖЕНЫ, и клиент говорит об этом прямо.

ЗАПУСК (только с сервера владельца; из песочницы будет 403 - геоблок DDoS-Guard):

    python3 seo-texts/zapusk_na_servere.py seo-texts/rannie_frp.py reestr 3.0
    python3 seo-texts/zapusk_na_servere.py seo-texts/rannie_frp.py lenta 60 3.0

Первый аргумент - режим (`reestr` или `lenta`), дальше пауза в секундах
(для `lenta` сначала сколько карточек). Результат кладётся в C:\\sender\\_ops\\,
в репозиторий крупные выгрузки не пишутся.
"""
import csv
import html as _html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
SAYT = 'https://frprf.ru'
OPS = r'C:\sender\_ops'
KONTROL_PUT = '/istorii-uspekha/shvartskopfer-net-takogo/'
KONTROL_SLOVO = 'щварцкопфер'

# Счётчик отказов. Это и есть лечение молчаливого continue: отказ не теряется,
# а становится числом, которое печатается в конце каждого прогона.
STAT = {'zapros': 0, 'ok': 0, 'otkaz': {}, 'retray': 0, 'kontrol': 0}


class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_OP_BEZ = urllib.request.build_opener(BezRedirekta)


def vzyat(url, timeout=40, popytok=3, pauza=3.0, bez_redirekta=False, kontrol=False):
    """Код ответа и тело, с ретраем и ВИДИМЫМ учётом отказов.

    Возвращает (код, тело). Код 0 значит «хост не ответил вовсе» и только это
    означает недоступность: 403, 503 и 301 - это ОТВЕТЫ.
    """
    zag = {'User-Agent': UA, 'Accept': 'text/html,application/json,*/*;q=0.8',
           'Accept-Language': 'ru-RU,ru;q=0.9'}
    posledniy = (0, b'')
    for popytka in range(popytok):
        STAT['zapros'] += 1
        if popytka:
            STAT['retray'] += 1
            time.sleep(pauza * (popytka + 1))
        try:
            req = urllib.request.Request(url, headers=zag)
            f = (_OP_BEZ.open(req, timeout=timeout) if bez_redirekta
                 else urllib.request.urlopen(req, timeout=timeout))
            with f as ff:
                telo = ff.read(3000000)
            STAT['ok'] += 1
            return ff.status, telo
        except urllib.error.HTTPError as e:
            telo = e.read(3000) if e.fp else b''
            if kontrol:
                STAT['kontrol'] += 1
            else:
                STAT['otkaz'][e.code] = STAT['otkaz'].get(e.code, 0) + 1
            posledniy = (e.code, telo)
            if e.code in (301, 302, 404, 403):
                return posledniy          # повторять бессмысленно
        except Exception as e:  # noqa: BLE001
            if kontrol:
                STAT['kontrol'] += 1
            else:
                STAT['otkaz'][0] = STAT['otkaz'].get(0, 0) + 1
            posledniy = (0, ('%s: %s' % (type(e).__name__, e)).encode())
    return posledniy


def itog_pribora():
    """Строка, без которой числам канала верить нельзя."""
    otkaz = ', '.join('%s: %d' % (k, v) for k, v in sorted(STAT['otkaz'].items())) or 'нет'
    print('ПРИБОР: запрошено %d, отдано 200 у %d, ретраев %d, отказов {%s}, '
          'контрольных отказов %d (они ожидаемы и в счёт не идут)'
          % (STAT['zapros'], STAT['ok'], STAT['retray'], otkaz, STAT['kontrol']))
    if STAT['otkaz']:
        print('ВНИМАНИЕ: отказы были, значит числа выгрузки ЗАНИЖЕНЫ. '
              'Это заслон хоста, а не пустота в источнике.')


def raskodirovat(b):
    t = b.decode('utf-8', 'replace')
    return b.decode('cp1251', 'replace') if t.count('\ufffd') > 300 else t


def chisto(s):
    return ' '.join(_html.unescape(re.sub(r'<[^>]+>', ' ', s or '')).split())


def imya_chisto(s):
    """Название заёмщика без кавычек.

    ЯМА, стоившая 16 ИНН из 21: h1 приходит как «АО &quot;ДМЗ&quot;», после unescape
    это «АО "ДМЗ"», а .strip('"« »') снимает кавычку только с краёв и оставляет
    «АО "ДМЗ» - строку с непарной кавычкой. dadata на такой запрос отдавала 0 карточек,
    и это выглядело как «у ФРП нет ИНН», хотя ИНН не было у ЗАПРОСА. Убираем кавычки
    везде и схлопываем пробелы."""
    return ' '.join(re.sub(r'["\u00ab\u00bb\u201c\u201d\u2018\u2019\']+', ' ', s or '').split())


# ---------------------------------------------------------------- реестр

def sobrat_adresa(pauza):
    """Все достижимые карточки реестра. Обходим пагинацию, пока появляются новые."""
    najdeno, stranic = {}, 0
    for pg in range(1, 40):
        url = SAYT + '/istorii-uspekha/' + ('' if pg == 1 else '?PAGEN_1=%d' % pg)
        kod, telo = vzyat(url, pauza=pauza)
        stranic += 1
        if kod != 200:
            break
        t = raskodirovat(telo)
        novye = set(re.findall(r'/istorii-uspekha/(\d+)/', t)) - set(najdeno)
        for i in novye:
            najdeno[i] = pg
        print('  список стр.%-2d код=%s размер=%-6d новых карточек=%d всего=%d'
              % (pg, kod, len(telo), len(novye), len(najdeno)))
        if not novye:
            break                      # пагинатор закольцевался на первую страницу
        time.sleep(pauza)
    # главная тоже носит ссылки на карточки
    kod, telo = vzyat(SAYT + '/', pauza=pauza)
    if kod == 200:
        for i in set(re.findall(r'/istorii-uspekha/(\d+)/', raskodirovat(telo))):
            najdeno.setdefault(i, 0)
    print('  списков пройдено: %d, карточек найдено: %d' % (stranic, len(najdeno)))
    return sorted(najdeno)


POLYA = [('programma', r'Программа:\s*([^:]{2,60}?)\s+Год выдачи'),
         ('god_zayma', r'Год выдачи займа:\s*(\d{4})'),
         ('region', r'Регион:\s*(.{2,50}?)\s+Муниципалитет'),
         ('municipalitet', r'Муниципалитет:\s*(.{2,50}?)\s+Отрасль'),
         ('otrasl', r'Отрасль:\s*(.{2,50}?)\s+Бюджет проекта'),
         ('byudzhet', r'Бюджет проекта:\s*([\d.,]+\s*(?:млн|млрд)\s*.)'),
         ('summa_zayma', r'Сумма займа от ФРП:\s*([\d.,]+\s*(?:млн|млрд)\s*.)')]


def razobrat_kartochku(nomer, telo):
    t = raskodirovat(telo)
    zg = re.search(r'<h1[^>]*>(.*?)</h1>', t, re.S)
    zayomshchik = chisto(zg.group(1)) if zg else ''
    ploskiy = chisto(re.sub(r'<script.*?</script>', '', t, flags=re.S))
    zap = {'nomer': nomer, 'url': '%s/istorii-uspekha/%s/' % (SAYT, nomer),
           'zayomshchik': imya_chisto(zayomshchik), 'inn': '', 'inn_istochnik': ''}
    for imya, pat in POLYA:
        m = re.search(pat, ploskiy)
        zap[imya] = chisto(m.group(1)) if m else ''
    # назначение: то, что стоит между названием и словом «Подробнее»
    m = re.search(re.escape(zayomshchik) + r'\s*(.{5,200}?)\s*Подробнее', ploskiy)
    zap['naznachenie'] = chisto(m.group(1)) if m else ''
    # человек: блок div.item-review-rep -> div.name + div.post + цитата
    m = re.search(r'item-review-rep.*?<div class="name">(.*?)</div>\s*'
                  r'<div class="post">(.*?)</div>\s*<p>(.*?)</p>', t, re.S)
    zap['chelovek'] = chisto(m.group(1)) if m else ''
    zap['dolzhnost'] = chisto(m.group(2)) if m else ''
    zap['citata'] = (chisto(m.group(3))[:400]) if m else ''
    return zap


def dadata_inn(nazvanie, region=''):
    """ИНН по названию через dadata, с проверкой принадлежности по региону.

    ЯМА, стоившая 16 ИНН из 21 и ПЕРЕЖИВШАЯ первую починку: я склеивал название с
    регионом в одну строку запроса. Замер по семи целям: «АО ДМЗ» -> 4 карточки,
    «АО ДМЗ Московская область» -> 0. И так у шести из семи. То есть suggest ищет
    по названию, ИНН и ОГРН, а лишние слова обнуляют выдачу: ИНН не было у ЗАПРОСА,
    а не у мира. Первый раз я списал это на кавычки, починил кавычки, и число не
    сдвинулось - одинаковый результат при разном входе и был диагнозом прибору.

    Регион теперь не в запросе, а заслон принадлежности: из карточек dadata берём ту,
    в адресе которой стоит регион из карточки ФРП. Это важно не только ради полноты:
    на «ООО ПСВ» dadata отдаёт 5 разных юрлиц с разными ИНН, и взять первое попавшееся
    значило бы приписать заводу чужой ИНН.

    Значение токена не печатается НИКОГДА, только «есть/нет» и длина.
    """
    tok = os.environ.get('DADATA_TOKEN', '')
    if not tok and os.path.exists(r'C:\sender\rs.env'):
        for l in open(r'C:\sender\rs.env', encoding='utf-8', errors='replace'):
            if l.startswith('DADATA_TOKEN='):
                tok = l.split('=', 1)[1].strip()
    if not tok:
        return '', 'токена нет'
    telo = json.dumps({'query': nazvanie, 'count': 10}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
        data=telo, headers={'Content-Type': 'application/json',
                            'Accept': 'application/json', 'Authorization': 'Token ' + tok})
    try:
        with urllib.request.urlopen(req, timeout=25) as f:
            d = json.loads(f.read())
    except Exception as e:  # noqa: BLE001
        return '', 'ошибка %s' % type(e).__name__
    kand = [s for s in (d.get('suggestions') or []) if (s.get('data') or {}).get('inn')]
    if not kand:
        return '', 'dadata: 0 карточек по названию'
    # ядро региона: «Кировская область» -> «киров», «Чувашская Республика» -> «чувашск»
    yadro = re.sub(r'\s*(область|обл\.?|край|республика|респ\.?|автономный округ|'
                   r'ао|г\.)\s*', ' ', (region or '').lower()).strip()
    yadro = yadro.split()[0][:6] if yadro else ''
    po_regionu = []
    for s in kand:
        adres = ((s.get('data') or {}).get('address') or {}).get('value') or ''
        if yadro and yadro in adres.lower():
            po_regionu.append(s)
    if len(po_regionu) == 1:
        s = po_regionu[0]
        return s['data']['inn'], 'dadata, регион совпал: ' + (s.get('value') or '')[:60]
    if len(po_regionu) > 1:
        return '', ('неоднозначно: %d карточек в регионе «%s», принадлежность не доказана'
                    % (len(po_regionu), region))
    if len(kand) == 1:
        # ЯМА ТРЕТЬЯ, поймана на живой выгрузке: «ООО МЕБЕЛЬНЫЙ КОМБИНАТ № 7,
        # Костромская область» получил ИНН 5027123778, а префикс 50 - это Московская
        # область. Единственный кандидат НЕ означает «тот самый»: правило «агрегатор не
        # доказывает принадлежность» действует и когда карточка одна. ИНН оставляем
        # (выброшенное заново не добывается), но принадлежность называем честно.
        s = kand[0]
        adres = ((s.get('data') or {}).get('address') or {}).get('value') or ''
        if not yadro:
            prich = 'единственная карточка, регион в источнике не указан'
        elif yadro in adres.lower():
            prich = 'единственная карточка, регион совпал'
        else:
            prich = 'единственная карточка, регион НЕ совпал (%s против «%s»)' % (
                adres[:40], region)
        return s['data']['inn'], 'dadata, ' + prich
    return '', ('неоднозначно: %d карточек, ни одна не в регионе «%s»' % (len(kand), region))


def rezhim_reestr(pauza):
    print('РЕЖИМ: реестр профинансированных проектов')
    # КОНТРОЛЬ 1: заведомо негодный адрес обязан дать не-200
    kod, _ = vzyat(SAYT + KONTROL_PUT, popytok=1, pauza=pauza, kontrol=True)
    print('КОНТРОЛЬ негодный адрес: код=%s (200 означал бы сломанный прибор)' % kod)
    # КОНТРОЛЬ 2: снятый раздел обязан дать именно 301, а не 200
    kod2, _ = vzyat(SAYT + '/klienty/42484/', popytok=1, bez_redirekta=True, kontrol=True)
    print('КОНТРОЛЬ снятый раздел /klienty/: код=%s (ожидается 301)' % kod2)
    time.sleep(pauza)

    adresa = sobrat_adresa(pauza)
    zapisi = []
    for nomer in adresa:
        kod, telo = vzyat('%s/istorii-uspekha/%s/' % (SAYT, nomer), pauza=pauza)
        time.sleep(pauza)
        if kod != 200:
            continue
        zapisi.append(razobrat_kartochku(nomer, telo))

    # ИНН вторым шагом
    poluchen = 0
    for z in zapisi:
        if z['zayomshchik']:
            z['inn'], z['inn_istochnik'] = dadata_inn(z['zayomshchik'], z.get('region', ''))
            poluchen += 1 if z['inn'] else 0
            time.sleep(0.3)
    # КОНТРОЛЬ 3: выдуманное предприятие обязано дать пустой ИНН
    k_inn, k_ist = dadata_inn('ООО «Щварцкопферный завод имени Щварцкопфера»')
    print('КОНТРОЛЬ выдуманное предприятие в dadata: ИНН=«%s» (%s), обязан быть пуст'
          % (k_inn, k_ist))

    put = os.path.join(OPS, '3s_frp_reestr.csv')
    polya = ['nomer', 'url', 'zayomshchik', 'inn', 'inn_istochnik', 'naznachenie',
             'programma', 'god_zayma', 'region', 'municipalitet', 'otrasl',
             'byudzhet', 'summa_zayma', 'chelovek', 'dolzhnost', 'citata']
    with open(put, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=polya, delimiter=';')
        w.writeheader()
        for z in zapisi:
            w.writerow({k: z.get(k, '') for k in polya})

    est = lambda k: sum(1 for z in zapisi if z.get(k))  # noqa: E731
    dokaz = sum(1 for z in zapisi if z.get('inn') and 'регион совпал' in z.get('inn_istochnik', ''))
    somnit = sum(1 for z in zapisi if z.get('inn') and 'НЕ совпал' in z.get('inn_istochnik', ''))
    print('ИТОГ РЕЕСТРА: карточек %d' % len(zapisi))
    print('   ИНН: всего %d, из них принадлежность ДОКАЗАНА регионом %d, '
          'регион НЕ совпал %d (эти брать нельзя без доп. проверки)'
          % (est('inn'), dokaz, somnit))
    for k in ('zayomshchik', 'inn', 'naznachenie', 'god_zayma', 'region',
              'otrasl', 'summa_zayma', 'chelovek'):
        print('   %-14s есть у %d из %d' % (k, est(k), len(zapisi)))
    ploskiy = ' '.join(json.dumps(z, ensure_ascii=False) for z in zapisi).lower()
    print('КОНТРОЛЬ «%s» в выгрузке: %d (обязан быть 0)'
          % (KONTROL_SLOVO, ploskiy.count(KONTROL_SLOVO)))
    print('записано:', put, os.path.getsize(put))
    for z in zapisi[:12]:
        print('  * %s | ИНН %s | %s | %s | %s | %s | %s'
              % (z['zayomshchik'][:26], z['inn'] or '-', z['god_zayma'], z['otrasl'][:16],
                 z['region'][:18], z['summa_zayma'], (z['chelovek'] + ' / ' + z['dolzhnost'])[:34]))
    svorka_s_bazoy(zapisi)
    return zapisi


def svorka_s_bazoy(zapisi):
    baza = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
    if not os.path.exists(baza):
        print('СВЕРКА: живого файла базы нет по адресу', baza)
        return
    print('СВЕРКА С ЖИВОЙ БАЗОЙ: %s, %d байт, время %s'
          % (baza, os.path.getsize(baza), time.ctime(os.path.getmtime(baza))))
    inny, nazv = set(), set()
    with open(baza, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            if (r.get('inn') or '').strip():
                inny.add(r['inn'].strip())
            n = re.sub(r'[«»"\s\-]+', '', (r.get('predpriyatie') or '').strip().lower())
            if n:
                nazv.add(n)
    print('  в базе: ИНН %d, названий %d' % (len(inny), len(nazv)))
    s_inn = [z for z in zapisi if z['inn'] and 'НЕ совпал' not in z.get('inn_istochnik', '')]
    somnit = [z for z in zapisi if z['inn'] and 'НЕ совпал' in z.get('inn_istochnik', '')]
    print('  ИНН отложено как недоказанные (регион не совпал): %d' % len(somnit))
    for z in somnit:
        print('    ОТЛОЖЕНО: %s ИНН %s | %s' % (z['zayomshchik'][:32], z['inn'],
                                                z['inn_istochnik'][:70]))
    est_inn = [z for z in s_inn if z['inn'] in inny]
    bez = [z for z in zapisi if not z['inn']]
    est_naz = [z for z in bez
               if re.sub(r'[«»"\s\-]+', '', z['zayomshchik'].lower()) in nazv]
    print('  с ИНН из ФРП: %d | уже в базе по ИНН: %d | НОВЫХ по ИНН: %d'
          % (len(s_inn), len(est_inn), len(s_inn) - len(est_inn)))
    print('  без ИНН: %d | из них совпало по названию: %d' % (len(bez), len(est_naz)))
    print('  КОНТРОЛЬ: выдуманный ИНН 0000000000 в базе: %d'
          % (1 if '0000000000' in inny else 0))
    for z in s_inn:
        if z['inn'] not in inny:
            print('    НОВОЕ: %s ИНН %s | %s | %s' % (z['zayomshchik'][:34], z['inn'],
                                                      z['otrasl'][:18], z['region'][:20]))


# ---------------------------------------------------------------- лента

def rezhim_lenta(skolko, pauza):
    print('РЕЖИМ: пресс-лента (новость о займе, ИНН в источнике нет)')
    kod, telo = vzyat(SAYT + '/sitemap-iblock-9.xml', timeout=60, pauza=pauza)
    print('sitemap: код=%s размер=%d' % (kod, len(telo)))
    if kod != 200:
        itog_pribora()
        return []
    xml = raskodirovat(telo)
    pary = []
    for z in re.findall(r'<url>(.*?)</url>', xml, re.S):
        u = re.search(r'<loc>([^<]+)</loc>', z)
        lm = re.search(r'<lastmod>([^<]*)</lastmod>', z)
        if u and '/novosti/' in u.group(1) and u.group(1).rstrip('/').count('/') > 4:
            pary.append((u.group(1), lm.group(1) if lm else ''))
    print('карточек новостей: %d (ВНИМАНИЕ: lastmod протухший, верхние значения 2020,'
          ' сортировать по нему нельзя)' % len(pary))
    komp = re.compile(r'(?:ООО|АО|ПАО|ЗАО|ОАО|НПО|НПП|ГК|АПХ)\s*[«"]([^»"]{2,60})[»"]')
    summa = re.compile(r'(\d[\d\s.,]{0,12})\s*(млн|млрд)\s*(?:руб|рублей)')
    data = re.compile(r'(\d{1,2}\s+(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|'
                      r'сентябр|октябр|ноябр|декабр)\w*\s+20\d\d)')
    stroki = []
    for u, lm in pary[:skolko]:
        kod, telo = vzyat(u, pauza=pauza)
        time.sleep(pauza)
        if kod != 200:
            continue
        h = re.sub(r'<script.*?</script>', '', raskodirovat(telo), flags=re.S)
        x = chisto(h)
        zg = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
        zagolovok = chisto(zg.group(1)) if zg else ''
        i = max(x.find(zagolovok), 0) if zagolovok else 0
        tel = x[i:i + 3000]
        d, s = data.search(x), summa.search(tel)
        stroki.append({'url': u, 'lastmod': lm, 'data': d.group(1) if d else '',
                       'zagolovok': zagolovok[:200],
                       'kompanii': ' | '.join(dict.fromkeys(komp.findall(tel)))[:220],
                       'summa': s.group(0) if s else ''})
    put = os.path.join(OPS, '3s_frp_lenta.csv')
    with open(put, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, delimiter=';',
                           fieldnames=['url', 'lastmod', 'data', 'zagolovok', 'kompanii', 'summa'])
        w.writeheader()
        for r in stroki:
            w.writerow(r)
    print('ИТОГ ЛЕНТЫ: карточек %d | с датой %d | с названием %d | с суммой %d'
          % (len(stroki), sum(1 for r in stroki if r['data']),
             sum(1 for r in stroki if r['kompanii']), sum(1 for r in stroki if r['summa'])))
    print('КОНТРОЛЬ «%s»: %d (обязан быть 0)' % (KONTROL_SLOVO,
          sum(1 for r in stroki if KONTROL_SLOVO in (r['zagolovok'] + r['kompanii']).lower())))
    print('записано:', put, os.path.getsize(put))
    return stroki


def main():
    rezhim = sys.argv[1] if len(sys.argv) > 1 else 'reestr'
    if rezhim == 'lenta':
        skolko = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        pauza = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
        rezhim_lenta(skolko, pauza)
    else:
        pauza = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
        rezhim_reestr(pauza)
    itog_pribora()
    return 0


if __name__ == '__main__':
    sys.exit(main())
