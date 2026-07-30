# -*- coding: utf-8 -*-
"""Tender.pro: поиск по всей площадке и вытаскивание ТЕХНИЧЕСКОГО контакта из карточки.

Зачем. Обе сессии записали вывод «Tender.pro технических людей не даёт»: в поле «куратор
закупки» стоит снабженец. Вывод неверен — технарь стоит в **свободном комментарии** той же
карточки, и с прямым мобильным:

    «По всем тех. вопросам просьба обращаться к Артемьеву Дмитрию:
     моб. тел. +7(962)205-11-47, моб. раб. +7(920)144-58-78»

Это ошибка класса «пустое поле принято за отсутствие данных»: смотрели поле, а данные лежат
в примечании.

Второе, что было упущено: соседняя сессия ходила по карточкам **своего списка ИНН** и скачала
77 карточек. А у площадки есть поиск по всей площадке — форма главной страницы бьёт в
`/api/tenders/list` (найдено в коде страницы, не угадыванием). По слову «компрессор» он даёт
203 страницы по 25 записей. Контрольная бессмыслица «кастрюлякастрюля» даёт ноль, то есть
фильтр действительно применяется (правило В8).

Как устроено:
  1. `--zamer` — счётчики по ключам и режимам. Гонять первым: он же проверяет, что фильтр жив.
  2. `--spisok` — обход страниц выдачи: id, предмет, даты, компания и её id.
  3. `--kartochki` — карточка `/api/tender/<id>/view_public`: комментарий, телефоны, почты.
     Телефон берётся **из разметки площадки** `<span class="wmi-callto">`, а не регуляркой по
     тексту: в архиве прошлого обогащения регулярка по десяти цифрам собрала 3 815 ложных
     номеров из координат векторной графики. Регулярка оставлена вторым слоем и помечает,
     что номер взят не из разметки.
  4. `--inn` — ИНН компании со страницы `/api/company/<cid>/view` (ИНН там напечатан).

Разбор «кто этот человек» (ФИО + должность) отдаётся провайдеру отдельным шагом
(`tenderpro_lica.py`): формат свободный, регуляркой берутся только телефон и почта.

Использование:
    python3 tenderpro_harvest.py --zamer
    python3 tenderpro_harvest.py --spisok  [--threads 8] [--stranic 400]
    python3 tenderpro_harvest.py --kartochki [--threads 10]
    python3 tenderpro_harvest.py --inn [--threads 8]
"""
import csv
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BAZA = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BAZA, 'engineers-lens', 'centro', 'tenderpro')
SPISOK = os.path.join(OUT, 'tp-spisok.csv')
KART = os.path.join(OUT, 'tp-kartochki.csv')
INN = os.path.join(OUT, 'tp-inn.csv')

LIST_URL = 'https://www.tender.pro/api/tenders/list'
CARD_URL = 'https://www.tender.pro/api/tender/%s/view_public'
COMP_URL = 'https://www.tender.pro/api/company/%s/view'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

# Ключи гоняются по одному слову. На Сбербанк-АСТ фраза из двух слов режет выдачу в сто раз,
# на Портале поставщиков наоборот расширяет — то есть это свойство площадки, а не правило.
# Поэтому в `--zamer` есть контрольная пара, и режим выбирается по замеру, а не по памяти.
#
# Ключи — ПОЛНЫЕ словоформы, и это не стилистика. Замер 30.07.2026: площадка приводит слово
# к лемме («центробежный» = «центробежная» = «центробежные» = 775 записей; «компрессор» =
# «компрессора» = 5 075), но **обрезанная основа даёт ноль**: «центробежн» 0, «воздуходувн» 0,
# «компрессорн» 3. То есть привычный приём «искать по основе» здесь возвращает пустоту, которая
# выглядит как «на площадке этого нет». Ловушка ровно правила В8.
# Разные леммы считаются отдельно: «воздуходувка» 325, «воздуходувный» 75.
KLYUCHI = ['компрессор', 'компрессорная', 'центробежный', 'воздуходувка', 'воздуходувный',
           'турбокомпрессор', 'турбоагрегат', 'нагнетатель', 'газодувка', 'турбовоздуходувка']

# Слова, по которым в комментарии видно техническую роль, а не снабжение.
TEH = re.compile(r'тех\w*\s+(?:вопрос|характер|част)|техническ|главн\w+\s+(?:инженер|механик|'
                 r'энергетик|технолог)|гл\.?\s*(?:инженер|механик|энергетик)|начальник\s+'
                 r'(?:цеха|управлен|отдела\s+глав|компрессорн|энерго|производств)|'
                 r'механик|энергетик|инженер|КИПиА|ОГМ|ОГЭ|УГЭ|УГМ', re.I)
# Телефон из разметки площадки — основной путь. Регулярка по тексту — второй слой.
CALLTO = re.compile(r'class="wmi-callto"[^>]*>([^<]{5,40})<')
#
# Регулярка телефона по тексту переписана 30.07.2026 после замера: **прежняя пропускала
# пятизначный код города.** Она требовала после кода минимум две цифры
# (`\d{3,5}[\s)\-]*\d{2,3}…`), а в живой записи `+7 (34350) 4-00-88` после кода идёт `4-00-88`.
# Из 3 761 карточки, отсечённой от разбора как «без телефона и без технического слова», телефон
# на самом деле есть у **264**, и у **241** из них рядом стоит ФИО. Потеряны были живые
# контакты: «Обращаться к Колясниковой Татьяне Николаевне тел. 8 3439 395 360» (АО КУМЗ),
# «Ответственный сотрудник Южакова Екатерина Николаевна, +7 (34350) 4-00-88».
#
# Второй случай, тот же по природе — номер в скобках **без кода страны**: `тел. (8482) 56-10-44`.
# Прежняя регулярка съедала восьмёрку как код страны, и оставалось девять цифр вместо десяти.
# Два уровня, и это не украшение. Первая версия починки требовала слово связи рядом со ВСЯКИМ
# номером — сухой прогон показал, что она **теряет 2 498 телефонов из 4 504**: у большинства
# живых записей вида `+7(962)205-11-47` никакого «тел.» в сорока знаках перед ними нет.
# Требование контекста верно только для неоднозначного шаблона.
#
# Уровень 1, однозначный: код страны и ровно десять цифр после него. Контекст не нужен, такую
# запись ни с чем не спутать. Отсекается только реквизитный префикс.
TEL_YASNO = re.compile(r'(?:\+7|\b8)[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
# Уровень 2, неоднозначный: пятизначный код с коротким номером (`+7 (34350) 4-00-88`) и номер в
# скобках без кода страны (`тел. (8482) 56-10-44`). Тут контекст обязателен, иначе шаблон ловит
# `Remeza (id1190815)`: первая попытка без рубежей дала 299 вместо 264.
TEL_SPORNO = re.compile(r'(?:\+?7|\b8)[\s\-]*\(?\d{4,5}\)?[\s\-]*\d[\d\s\-]{4,8}\d'
                        r'|(?<![\d+])\(\d{3,5}\)[\s\-]*\d[\d\s\-]{4,8}\d')
TEL_PERED = re.compile(r'(?:id|ИНН|ОГРН|КПП|р/с|к/с|БИК|цена|сумма|№|лот|тендер|заказ|инв)'
                       r'\D{0,4}$', re.I)
TEL_SVYAZ = re.compile(r'тел|моб|сот|факс|контакт|обращат|звон|т\.', re.I)
# «№» в списке реквизитных знаков стоит правильно, но он же встречается в записи телефона:
# «По вопросам осмотра — Жарков Сергей Юрьевич (**моб.№ 89085719649**)». Замер поймал ровно
# один такой случай на девять тысяч карточек, и это был настоящий мобильный технического
# контакта. Поэтому реквизитный знак отменяется, если рядом же стоит слово связи.
TEL_PERED_OTMENA = re.compile(r'(?:тел|моб|сот|факс)\w*\.?\s*№?\s*$', re.I)


def telefony_iz_teksta(txt):
    """Номера из свободного текста двумя уровнями строгости.

    Однозначная запись берётся как есть, спорная — только при слове связи рядом. Порядок
    важен: сначала однозначные, потом спорные, и спорная не добавляется, если те же десять
    цифр уже взяты уровнем 1 (иначе `8 (8482) 56-10-44` попадёт дважды).
    """
    txt = txt or ''

    def cif(s):
        d = re.sub(r'\D', '', s)
        return d[-10:] if len(d) in (10, 11) else ''

    out, vzyato = [], set()
    for m in TEL_YASNO.finditer(txt):
        c = cif(m.group(0))
        if not c or c in vzyato:
            continue
        pered = txt[max(0, m.start() - 14):m.start()]
        if TEL_PERED.search(pered) and not TEL_PERED_OTMENA.search(pered):
            continue
        vzyato.add(c)
        out.append(m.group(0).strip())
    for m in TEL_SPORNO.finditer(txt):
        c = cif(m.group(0))
        if not c or c in vzyato:
            continue
        pered = txt[max(0, m.start() - 14):m.start()]
        if TEL_PERED.search(pered) and not TEL_PERED_OTMENA.search(pered):
            continue
        if not TEL_SVYAZ.search(txt[max(0, m.start() - 45):m.start()]):
            continue
        vzyato.add(c)
        out.append(m.group(0).strip())
    return out
MAIL = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
ID_TENDER = re.compile(r'/api/tender/(\d+)/view')
ROW = re.compile(
    r'<td[^>]*class="pr-0 tender__name"[^>]*>.*?href="/api/tender/(\d+)/view_public"[^>]*>'
    r'(.*?)</a>.*?</td>\s*<td[^>]*>([\d.]{0,10})</td>\s*<td[^>]*>([^<]{0,30})</td>'
    r'.*?href="/api/company/(\d+)/view[^"]*"[^>]*>([^<]{0,200})</a>', re.S)
INN_RE = re.compile(r'ИНН[^0-9]{0,20}(\d{10}|\d{12})')
STRANIC = re.compile(r'page=(\d+)')


def bez_tegov(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip()


def vzyat(url, popytok=4):
    for p in range(popytok):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA,
                                                       'Accept-Language': 'ru,en;q=0.8'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return f'__ОШИБКА__ {type(e).__name__}: {str(e)[:80]}'
            time.sleep(1.5 * (p + 1))


def url_spiska(klyuch, page=1, state='100'):
    q = {'sid': '', 'good_name': '', 'tender_name': klyuch, 'dateb': '', 'datee': '',
         'tender_type': '100', 'company_name': '', 'tender_state': state,
         'tender_show_own': '0', 'tender_id': '', 'country': '1', 'region': '0_0',
         'basis': '1', 'tender_promoter': '1', 'tender_officer': '0', 'company_id': '',
         'by': '25', 'order': '3', 'page': str(page)}
    return LIST_URL + '?' + urllib.parse.urlencode(q)


def zamer():
    """Счётчики по ключам. Первым делом контрольная бессмыслица: если она даёт не ноль,
    фильтр не применяется и все остальные числа бессмысленны."""
    print('ключ;страниц;записей_на_1_стр;оценка_записей', flush=True)
    kontrol = KLYUCHI + ['кастрюлякастрюля', 'центробежный компрессор']
    for k in kontrol:
        h = vzyat(url_spiska(k))
        ids = set(ID_TENDER.findall(h or ''))
        stranic = max([int(x) for x in STRANIC.findall(h or '')] or [0])
        print(f'{k};{stranic};{len(ids)};{stranic * 25 if stranic else len(ids)}', flush=True)


def spisok(threads, max_stranic):
    os.makedirs(OUT, exist_ok=True)
    zadaniya = []
    for k in KLYUCHI:
        h = vzyat(url_spiska(k))
        stranic = max([int(x) for x in STRANIC.findall(h or '')] or [1])
        stranic = min(stranic, max_stranic)
        print(f'  {k}: {stranic} страниц', file=sys.stderr, flush=True)
        zadaniya += [(k, p) for p in range(1, stranic + 1)]
    print(f'страниц всего: {len(zadaniya)}', file=sys.stderr)

    cols = ['klyuch', 'tender_id', 'predmet', 'sozdan', 'do', 'company_id', 'company']
    f = open(SPISOK, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()
    lock = threading.Lock()
    vsego = {'n': 0, 'pusto': 0}

    def odna(z):
        k, p = z
        h = vzyat(url_spiska(k, p))
        out = []
        for tid, predmet, sozdan, do, cid, comp in ROW.findall(h or ''):
            out.append({'klyuch': k, 'tender_id': tid, 'predmet': bez_tegov(predmet),
                        'sozdan': sozdan.strip(), 'do': do.strip(),
                        'company_id': cid, 'company': bez_tegov(comp)})
        return k, p, out, len(set(ID_TENDER.findall(h or '')))

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, (k, p, rows, syro) in enumerate(pool.map(odna, zadaniya), 1):
            with lock:
                for r in rows:
                    w.writerow(r)
                vsego['n'] += len(rows)
                # Расхождение «ссылок на тендеры на странице» и «разобранных строк» — признак,
                # что шаблон строки отстал от разметки. Молчать об этом нельзя.
                if syro and not rows:
                    vsego['pusto'] += 1
                if i % 100 == 0:
                    f.flush()
                    print(f'  {i}/{len(zadaniya)} страниц, строк {vsego["n"]}, '
                          f'страниц без разбора {vsego["pusto"]}', file=sys.stderr, flush=True)
    f.close()
    print(f'готово: строк {vsego["n"]}, страниц со ссылками но без разбора {vsego["pusto"]} '
          f'→ {SPISOK}', file=sys.stderr)


def kartochki(threads, peresobrat=None):
    """peresobrat: путь к файлу со списком tender_id, которые надо взять ЗАНОВО и заменить
    в накопителе. Нужен, когда меняется не источник, а наш разбор: пересобирать девять тысяч
    карточек ради трёх с половиной тысяч исправлений расточительно."""
    ids, meta = [], {}
    for r in csv.DictReader(open(SPISOK, encoding='utf-8-sig'), delimiter=';'):
        t = r['tender_id']
        if t not in meta:
            ids.append(t)
            meta[t] = r
    zanovo = set()
    if peresobrat:
        zanovo = {l.strip() for l in open(peresobrat, encoding='utf-8') if l.strip()}
        print(f'заказано пересобрать: {len(zanovo)}', file=sys.stderr)
    gotovo = set()
    staryе_stroki = []
    if os.path.exists(KART):
        for r in csv.DictReader(open(KART, encoding='utf-8-sig'), delimiter=';'):
            if r['tender_id'] in zanovo:
                continue          # эту строку заменим свежей
            gotovo.add(r['tender_id'])
            staryе_stroki.append(r)
    if zanovo:
        # накопитель перезаписываем без заменяемых строк, чтобы не было двух версий одной карточки
        import shutil
        shutil.copy(KART, KART + '.do-peresborki')
        with open(KART, 'w', encoding='utf-8-sig', newline='') as f0:
            w0 = csv.DictWriter(f0, fieldnames=list(staryе_stroki[0].keys()), delimiter=';',
                                extrasaction='ignore')
            w0.writeheader()
            for r in staryе_stroki:
                w0.writerow(r)
        print(f'в накопителе оставлено {len(staryе_stroki)} строк, прежняя версия в '
              f'{os.path.basename(KART)}.do-peresborki', file=sys.stderr)
    ids = [t for t in ids if t not in gotovo]
    print(f'карточек к обходу: {len(ids)} (уже есть {len(gotovo)})', file=sys.stderr)

    cols = ['tender_id', 'company_id', 'company', 'predmet', 'sozdan', 'organizator',
            'est_teh', 'telefony_razmetka', 'telefony_tekst', 'pochty', 'comment']
    novyy = not os.path.exists(KART)
    f = open(KART, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    lock = threading.Lock()
    sch = {'n': 0, 'teh': 0, 'tel': 0, 'err': 0}

    def odna(tid):
        h = vzyat(CARD_URL % tid)
        if not h or h.startswith('__ОШИБКА__'):
            return tid, None
        i = h.find('Комментарий:')
        com = ''
        if i > 0:
            j = h.find('<!-- div -->', h.find('tender-comment__wrapper', i))
            com = h[i:j if j > i else i + 4000]
        org = ''
        m = re.search(r'Организатор[^<]{0,20}:</div><!-- div --><a[^>]*>([^<]{0,300})</a>', h)
        if m:
            org = bez_tegov(m.group(1))
        tel_r = [t.strip() for t in CALLTO.findall(com)]
        txt = bez_tegov(com)
        tel_t = [t for t in telefony_iz_teksta(txt) if t.strip() not in tel_r]
        # Комментарий сохраняется целиком, но история этой строки поучительнее самой правки.
        #
        # Я решил, что предел 2 000 знаков режет данные: 3 597 карточек имели длину ровно у
        # предела, и скопление длин у границы — обычный признак обрезки. Замер на неусечённой
        # группе (1 665 карточек длиной 1 000-1 900) дал, что телефон живёт только в последних
        # 500 знаках у 11,8 %, и я посчитал ожидание в ~423 потерянных номера.
        #
        # **Пересборка 3 597 карточек с пределом 60 000 дала ноль прибавки.** Ни один комментарий
        # не стал длиннее, ни одного нового номера. Причина: связывающим был не этот предел, а
        # окно вырезания блока (`com = h[i:j]`), а сам блок комментария на площадке кончается
        # примерно на двух тысячах знаков текста. Проверено на карточке с самым длинным
        # комментарием: блок занимает 5 450 знаков HTML, после снятия тегов 2 005 знаков текста,
        # в CSV лежало 1 987 — то есть предел срезал пять знаков, а не половину текста.
        #
        # Урок, который дороже правки: **скопление значений у предела доказывает, что предел
        # достигается, но не доказывает, что за ним что-то есть.** Прежде чем чинить предел,
        # надо найти естественную границу данных. Стоило это 3 597 напрасных запросов к
        # площадке (денег владельца не тронуло, только время).
        return tid, {'organizator': org, 'comment': txt[:60000],
                     'est_teh': '1' if TEH.search(txt) else '',
                     'telefony_razmetka': ' | '.join(dict.fromkeys(tel_r)),
                     'telefony_tekst': ' | '.join(dict.fromkeys(tel_t)),
                     'pochty': ' | '.join(dict.fromkeys(MAIL.findall(txt)))}

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, (tid, d) in enumerate(pool.map(odna, ids), 1):
            with lock:
                if d is None:
                    sch['err'] += 1
                else:
                    m = meta[tid]
                    w.writerow({**d, 'tender_id': tid, 'company_id': m['company_id'],
                                'company': m['company'], 'predmet': m['predmet'],
                                'sozdan': m['sozdan']})
                    sch['n'] += 1
                    if d['est_teh']:
                        sch['teh'] += 1
                    if d['telefony_razmetka'] or d['telefony_tekst']:
                        sch['tel'] += 1
                if i % 200 == 0:
                    f.flush()
                    print(f'  {i}/{len(ids)}: карточек {sch["n"]}, с техническим словом '
                          f'{sch["teh"]}, с телефоном {sch["tel"]}, ошибок {sch["err"]}',
                          file=sys.stderr, flush=True)
    f.close()
    print(f'готово: {sch["n"]} карточек, техническое слово в {sch["teh"]}, телефон в '
          f'{sch["tel"]}, ошибок {sch["err"]} → {KART}', file=sys.stderr)


def inn(threads):
    cids = []
    for r in csv.DictReader(open(SPISOK, encoding='utf-8-sig'), delimiter=';'):
        if r['company_id'] not in cids:
            cids.append(r['company_id'])
    print(f'компаний: {len(cids)}', file=sys.stderr)
    f = open(INN, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=['company_id', 'company', 'inn', 'kpp'], delimiter=';',
                       extrasaction='ignore')
    w.writeheader()
    lock = threading.Lock()
    sch = {'ok': 0}

    def odna(cid):
        h = vzyat(COMP_URL % cid)
        if not h or h.startswith('__ОШИБКА__'):
            return cid, '', '', ''
        t = bez_tegov(h)
        m = INN_RE.search(t)
        k = re.search(r'КПП[^0-9]{0,20}(\d{9})', t)
        nm = re.search(r'<title>([^<]{0,200})</title>', h)
        return cid, (m.group(1) if m else ''), (k.group(1) if k else ''), \
            (nm.group(1).strip() if nm else '')

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, (cid, i_, k_, nm) in enumerate(pool.map(odna, cids), 1):
            with lock:
                w.writerow({'company_id': cid, 'company': nm, 'inn': i_, 'kpp': k_})
                if i_:
                    sch['ok'] += 1
                if i % 200 == 0:
                    f.flush()
                    print(f'  {i}/{len(cids)}: с ИНН {sch["ok"]}', file=sys.stderr, flush=True)
    f.close()
    print(f'готово: с ИНН {sch["ok"]} из {len(cids)} → {INN}', file=sys.stderr)


def main():
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 8
    stranic = int(sys.argv[sys.argv.index('--stranic') + 1]) if '--stranic' in sys.argv else 400
    os.makedirs(OUT, exist_ok=True)
    if '--zamer' in sys.argv:
        zamer()
    elif '--spisok' in sys.argv:
        spisok(threads, stranic)
    elif '--kartochki' in sys.argv:
        kartochki(threads, peresobrat=(sys.argv[sys.argv.index('--peresobrat') + 1]
                                       if '--peresobrat' in sys.argv else None))
    elif '--inn' in sys.argv:
        inn(threads)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
