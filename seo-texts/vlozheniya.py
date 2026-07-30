# -*- coding: utf-8 -*-
"""Вложения закупок ЕИС: техзадания, извещения, протоколы — там, где живёт свободный текст.

Зачем. Перенос приёма Tender.pro на ЕИС проверен и **в теле карточки не работает**: блок
«Дополнительная информация» отсутствует у 43 карточек из 48 и содержит прочерк у пяти
(`engineers-lens/centro/eis/ZAMER-svobodnyy-tekst.md`). Но вывод там сужен до объекта замера:
свободного текста нет **в карточке**, а у ЕИС он живёт во **вложениях**. Живой образец уже
есть: у Газпром нефтехим Салавата в документе стояло «Инициатор мероприятия: Начальник УЭПБ и
ОТ В. А. Кузнецов», а в листе согласования «Главный механик (первичной переработки НПЗ)
Э. В. Ваганов».

Путь до файла найден в коде уже скачанных карточек, а не угадан:
    карточка → href «/epz/order/notice/notice223/documents.html?purchaseNoticeNumber=…&noticeGuid=…»
    страница документов → href «https://zakupki.gov.ru/223/filestore/public/1.0/download/fz223/file.html?uid=…»

Заслоны, каждый по конкретной ошибке прошлых прогонов:

- **Текст из PDF берётся библиотекой, а не разбором сырых байт.** В прошлом массовом обогащении
  регулярка по десяти цифрам собрала 3 815 ложных телефонов из координат векторной графики
  (`M8892 7.44042 1`). Библиотека отдаёт текстовый слой, координат в нём нет.
- **Порог распознавания по длине, а не «если пусто»:** меньше 200 знаков на файл — помечаем
  сканом. У соседней сессии 39 из 74 PDF оказались сканами с обрывком текстового слоя из
  колонтитула, и порог «если пусто» их пропустил бы.
- **Расширение врёт.** Тип определяется по сигнатуре первых байт (`%PDF`, `PK`, `\\xd0\\xcf`),
  потому что из 69 «доков» у соседей 33 оказались HTML внутри.
- **Номер принимается только рядом со словом связи** (тел/моб/контакт/сот) и **не принимается,
  если совпал с ИНН или ОГРН, напечатанным в том же файле**.

Шаги (каждый отдельно, результат на диске, повтор не переделывает сделанное):
    python3 vlozheniya.py --doki      # карточки → страницы документов
    python3 vlozheniya.py --fajly     # страницы документов → скачанные вложения
    python3 vlozheniya.py --tekst     # вложения → текст + пометка «скан»
    python3 vlozheniya.py --lica      # текст → люди, провайдером
"""
import csv
import glob
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

BAZA = os.path.dirname(os.path.abspath(__file__))
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
DROP = os.path.join(BAZA, 'server', 'drop_client.sh')
RAB = ('/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad')
KART = os.path.join(RAB, 'eis')
DOKI = os.path.join(RAB, 'eis_doki')
FAJLY = os.path.join(RAB, 'eis_fajly')
OUT = os.path.join(BAZA, 'engineers-lens', 'centro', 'eis')

SSYLKA_DOK = re.compile(r'href="(/epz/order/notice/notice223/documents\.html\?[^"]+)"')
SSYLKA_FAJL = re.compile(r'href="(https://zakupki\.gov\.ru/223/filestore/public/1\.0/download/'
                         r'fz223/file\.html\?uid=[0-9A-F]+)"', re.I)
# Должность рядом с ФИО — то, ради чего всё делается.
#
# Оба шаблона расширены 30.07.2026 после контроля на эталонах. Прежние проваливали два случая
# из пяти, и оба — живые записи из наших же данных:
#   «Вопросы технического характера: **Александр Владимирович Лосев**, Заместитель главного
#    механика» — фамилия стоит ПОСЛЕДНЕЙ, а шаблон ждал её первой;
#   «Инициатор мероприятия: **Начальник УЭПБ и ОТ** В. А. Кузнецов» — должности-аббревиатуры
#    (УЭПБ, ОГМ, ОГЭ, УГЭ, КИПиА, ОТиПБ) в списке не было вовсе.
# Это ровно то, из-за чего первый замер вложений дал одну пару на 106 файлов: мерился не
# источник, а собственный шаблон.
DOLZH = re.compile(
    r'((?:главн\w+|ведущ\w+|старш\w+|заместител\w+\s+главн\w+|зам\.?\s*главн\w+|'
    r'и\.?\s*о\.?\s*главн\w+)?\s*'
    r'(?:инженер\w*|механик\w*|энергетик\w*|технолог\w*|метролог\w*)'
    r'(?:\s+(?:по\s+[\w\-]+|цеха|производства|участка|управления)){0,2}'
    r'|начальник\w*\s+(?:цеха|компрессорн\w+|отдела\s+глав\w+|управления\s+глав\w+|'
    r'производств\w+|участка|службы\s+\w+|[А-ЯЁ]{2,6}(?:\s+и\s+[А-ЯЁ]{2,4})?)'
    r'|(?:главн\w+|ведущ\w+)\s+специалист\w*'
    r'|технически\w+\s+(?:директор\w*|руководител\w*)'
    r'|руководител\w+\s+(?:технической\s+службы|службы\s+глав\w+))', re.I)
FIO = re.compile(r'([А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'          # Иванов И. И.
                 r'|[А-ЯЁ]\.\s?[А-ЯЁ]\.\s?[А-ЯЁ][а-яё\-]{2,}'          # И. И. Иванов
                 r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}(?:вич|вна)\b'   # Иванов Иванович
                 r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}(?:вич|вна)\s+'
                 r'[А-ЯЁ][а-яё\-]{2,}\b'                               # Иван Иванович Иванов
                 r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}\s+'
                 r'[А-ЯЁ][а-яё\-]{2,}(?:вич|вна)\b)')                  # Иванов Иван Иванович
SVYAZ = re.compile(r'(?:тел|моб|сот|контакт|факс|т\.)\D{0,12}'
                   r'((?:\+7|\b8)?[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2})', re.I)
INN_OGRN = re.compile(r'\b(\d{10}|\d{12}|\d{13}|\d{15})\b')


def cifry(s):
    return re.sub(r'\D', '', s or '')


def podpis(b):
    """Тип по сигнатуре, а не по расширению: расширение врёт."""
    if b[:4] == b'%PDF':
        return 'pdf'
    if b[:2] == b'PK':
        return 'zip/docx/xlsx'
    if b[:4] == b'\xd0\xcf\x11\xe0':
        return 'doc/xls'
    if b[:15].lower().lstrip().startswith((b'<html', b'<!doctype')):
        return 'html'
    if b[:5] == b'{\\rtf':
        return 'rtf'
    return 'иное'


def runner_many(zad, threads=6):
    p = subprocess.run([sys.executable, KLIENT, '--many', json.dumps(zad, ensure_ascii=False),
                        '--threads', str(threads)], capture_output=True, text=True, timeout=1800)
    m = re.search(r'\[.*\]', p.stdout, re.S)
    return json.loads(m.group(0)) if m else []


def skachat(imya, kuda):
    os.makedirs(kuda, exist_ok=True)
    subprocess.run(['bash', DROP, 'down', imya], cwd=kuda, capture_output=True, timeout=600)
    p = os.path.join(kuda, imya)
    return p if os.path.exists(p) else ''


def shag_doki(pachka=6):
    os.makedirs(DOKI, exist_ok=True)
    zad = []
    for p in sorted(glob.glob(os.path.join(KART, 'eis_c_*.html'))):
        n = re.search(r'eis_c_(\d+)', p).group(1)
        if os.path.exists(os.path.join(DOKI, f'eis_d_{n}.html')):
            continue
        h = open(p, encoding='utf-8', errors='replace').read()
        m = SSYLKA_DOK.search(h)
        if m:
            zad.append({'task': 'fetch_url',
                        'args': {'url': 'https://zakupki.gov.ru' + m.group(1).replace('&amp;', '&'),
                                 'insecure': True, 'name': f'eis_d_{n}.html'}})
    print(f'страниц документов к обходу: {len(zad)}', file=sys.stderr)
    for i in range(0, len(zad), pachka):
        for r in runner_many(zad[i:i + pachka], pachka):
            d = (r or {}).get('data') or {}
            if d.get('drop_name'):
                skachat(d['drop_name'], DOKI)
        print(f'  {min(i + pachka, len(zad))}/{len(zad)}', file=sys.stderr, flush=True)


def shag_fajly(pachka=6, predel=200, tolko=None):
    os.makedirs(FAJLY, exist_ok=True)
    zad, karta, imena = [], {}, {}
    for p in sorted(glob.glob(os.path.join(DOKI, 'eis_d_*.html'))):
        n = re.search(r'eis_d_(\d+)', p).group(1)
        h = open(p, encoding='utf-8', errors='replace').read()
        # Имя файла, как его печатает страница документов, — оно и решает, нужен ли файл.
        podpisi = {m.group(1): m.group(2).strip() for m in re.finditer(
            r'href="(https://zakupki\.gov\.ru/223/filestore[^"]+)"[^>]*>([^<]{0,120})', h)}
        for j, u in enumerate(dict.fromkeys(SSYLKA_FAJL.findall(h)), 1):
            imya = f'eis_f_{n}_{j}.bin'
            imena[imya] = podpisi.get(u, '')
            if os.path.exists(os.path.join(FAJLY, imya)):
                continue
            zad.append({'task': 'fetch_url',
                        'args': {'url': u.replace('&amp;', '&'), 'insecure': True, 'name': imya}})
            karta[imya] = n
    # Отбор по имени файла: техзадание и документация нужнее протокола, а предел не бесконечный.
    # В первом заходе предел 240 срезал ровно нужное — «Приложение № 1 Техническое задание.docx»
    # и «Документация о закупке МСП (Компрессор).pdf» не скачались вовсе, и вывод «во вложениях
    # ничего нет» был сделан по протоколам и разъяснениям.
    if tolko:
        vazhno = re.compile(tolko, re.I)
        zad = [z for z in zad if vazhno.search(imena.get(z["args"]["name"], ""))] +               [z for z in zad if not vazhno.search(imena.get(z["args"]["name"], ""))]
    zad = zad[:predel]
    print(f'вложений к скачиванию: {len(zad)}', file=sys.stderr)
    for i in range(0, len(zad), pachka):
        for r in runner_many(zad[i:i + pachka], pachka):
            d = (r or {}).get('data') or {}
            if d.get('drop_name'):
                skachat(d['drop_name'], FAJLY)
        print(f'  {min(i + pachka, len(zad))}/{len(zad)}', file=sys.stderr, flush=True)
    json.dump(karta, open(os.path.join(FAJLY, 'karta.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)


def tekst_iz(p):
    b = open(p, 'rb').read()
    t = podpis(b)
    if t == 'pdf':
        try:
            import fitz
            with fitz.open(p) as d:
                return t, '\n'.join(s.get_text() for s in d), len(d)
        except Exception as e:  # noqa: BLE001
            return t, f'__ОШИБКА__ {type(e).__name__}: {str(e)[:60]}', 0
    if t == 'zip/docx/xlsx':
        # Сигнатура `PK` — это и docx, и xlsx, и **обычный zip-архив с вложенными файлами**.
        # Замер 30.07.2026: «Документация.zip» на 553 КБ прошла как «пусто», потому что её
        # разбирали как docx. А внутри таких архивов лежит ровно то, что нам нужно: техзадание
        # и приложения. Поэтому сначала смотрим, что внутри, и только потом решаем.
        import zipfile
        try:
            with zipfile.ZipFile(p) as z:
                imena = z.namelist()
                if 'word/document.xml' in imena:      # это docx
                    # **Текст таблиц обязателен.** `docx.Document().paragraphs` отдаёт только
                    # абзацы, а в извещениях и техзаданиях почти всё лежит в таблицах, поэтому
                    # «Извещение СГИ-01_2025_а.docx» выглядело пустым и попало в сканы.
                    # Надёжнее и проще — снять теги с самого `word/document.xml`: там и абзацы,
                    # и таблицы, и колонтитулы.
                    xml = z.read('word/document.xml')
                    tekst = re.sub(r'<[^>]+>', ' ', xml.decode('utf-8', 'replace'))
                    tekst = re.sub(r'[ \t]{2,}', ' ', tekst)
                    return t, tekst, 0
                if any(n.startswith('xl/') for n in imena):   # это xlsx
                    try:
                        import openpyxl
                        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
                        kus = []
                        for ws in wb.worksheets:
                            for row in ws.iter_rows(values_only=True):
                                kus.append(' '.join(str(c) for c in row if c is not None))
                        return 'xlsx', '\n'.join(kus), 0
                    except Exception:  # noqa: BLE001
                        pass
                # обычный архив: разбираем вложенные файлы по одному, рекурсией на один уровень
                kus, vlozh = [], 0
                for n in imena:
                    if n.endswith('/') or z.getinfo(n).file_size > 40_000_000:
                        continue
                    b2 = z.read(n)
                    vremya = p + '.__vlozh'
                    open(vremya, 'wb').write(b2)
                    try:
                        t2, txt2, _ = tekst_iz(vremya)
                        if len(txt2.strip()) > 40:
                            kus.append(f'=== {n} ({t2}) ===\n{txt2}')
                            vlozh += 1
                    finally:
                        os.path.exists(vremya) and os.remove(vremya)
                return f'архив({vlozh} файлов)', '\n'.join(kus), 0
        except Exception as e:  # noqa: BLE001
            return t, f'__ОШИБКА__ {str(e)[:60]}', 0
    if t == 'иное' and b[:6] == b"7z\xbc\xaf'\x1c":
        return '7z', '__НЕ_РАСПАКОВАН__ 7z требует внешней утилиты', 0
    if t == 'html':
        return t, re.sub(r'<[^>]+>', ' ', b.decode('utf-8', 'replace')), 0
    if t in ('doc/xls', 'rtf'):
        # Без внешних утилит достаём хотя бы кириллицу из потока: этого хватает,
        # чтобы увидеть «Главный механик Иванов И.И.» и телефон.
        s = b.decode('cp1251', 'replace')
        return t, re.sub(r'[^\wа-яёА-ЯЁ.,()@+\-/ \n]', ' ', s), 0
    return t, '', 0


def shag_tekst():
    os.makedirs(OUT, exist_ok=True)
    karta = {}
    kp = os.path.join(FAJLY, 'karta.json')
    if os.path.exists(kp):
        karta = json.load(open(kp, encoding='utf-8'))
    # Имя файла со страницы документов — оно объясняет, чем файл является: техзадание,
    # протокол или разъяснение. Без него замер нельзя разложить по типу документа, а именно
    # это и оказалось решающим: первый вывод «во вложениях ничего нет» был сделан по
    # протоколам, потому что техзадания не скачались.
    imena = {}
    ip = os.path.join(FAJLY, 'imena.json')
    if os.path.exists(ip):
        imena = json.load(open(ip, encoding='utf-8'))
    rows = []
    for p in sorted(glob.glob(os.path.join(FAJLY, 'eis_f_*.bin'))):
        imya = os.path.basename(p)
        tip, t, stranic = tekst_iz(p)
        # Порог по длине, а не «если пусто»: скан с колонтитулом даёт короткий текстовый слой.
        skan = len(t.strip()) < 200
        rows.append({'fajl': imya, 'zakupka': karta.get(imya, ''),
                     'imya_dokumenta': imena.get(imya, ''), 'tip': tip,
                     'bajt': os.path.getsize(p), 'stranic': stranic,
                     'znakov': len(t.strip()), 'skan_ili_pusto': '1' if skan else '',
                     'tekst': t[:200000]})
    with open(os.path.join(OUT, 'vlozheniya-tekst.jsonl'), 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    import collections
    print(f'файлов: {len(rows)}')
    print('  по типу:', dict(collections.Counter(r['tip'] for r in rows)))
    print(f'  скан или пусто (<200 знаков): {sum(1 for r in rows if r["skan_ili_pusto"])}')
    print(f'  с текстом: {sum(1 for r in rows if not r["skan_ili_pusto"])}')
    # Быстрый механический замер: есть ли вообще пары «должность + ФИО»
    par, tel = 0, 0
    for r in rows:
        if r['skan_ili_pusto']:
            continue
        t = r['tekst']
        inn = {cifry(x) for x in INN_OGRN.findall(t)}
        for m in DOLZH.finditer(t):
            # Окно СИММЕТРИЧНОЕ, и это исправление по контролю на эталонах. Прежде окно шло
            # только вперёд от должности, и запись «Александр Владимирович Лосев, Заместитель
            # главного механика» не находилась вовсе: имя стоит ПЕРЕД должностью. В документах
            # встречаются оба порядка — «УТВЕРЖДАЮ Главный инженер Иванов И.И.» и «Иванов И.И.,
            # главный инженер», — поэтому смотреть надо в обе стороны.
            okno = t[max(0, m.start() - 250):m.start() + 250]
            if FIO.search(okno):
                par += 1
                for c in SVYAZ.findall(okno):
                    if cifry(c) not in inn:
                        tel += 1
    print(f'  пар «должность рядом с ФИО»: {par}, из них с телефоном рядом: {tel}')
    print(f'→ {os.path.join(OUT, "vlozheniya-tekst.jsonl")}')


def shag_lica(threads=8, pachka=3):
    import gen_provider as G
    G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                     'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL',
                                                         'https://router.cheap')}
    src = os.path.join(OUT, 'vlozheniya-tekst.jsonl')
    rows = [json.loads(l) for l in open(src, encoding='utf-8')]
    # Провайдеру отдаём только куски вокруг должностей: целиком техзадание это сотни страниц
    # труб и болтов, а нам нужны подписи и контакты. Это же бережёт баланс.
    zadaniya = []
    for r in rows:
        if r['skan_ili_pusto']:
            continue
        t = r['tekst']
        kuski = []
        for m in DOLZH.finditer(t):
            kuski.append(t[max(0, m.start() - 300):m.start() + 400])
            if len(kuski) >= 8:
                break
        if kuski:
            zadaniya.append((r['fajl'], r['zakupka'], '\n---\n'.join(kuski)[:9000]))
    print(f'файлов с должностями: {len(zadaniya)}', file=sys.stderr)

    PROMPT = """Ты читаешь куски документов закупки промышленного предприятия (техзадание,
извещение, протокол, лист согласования). Нужны люди в ТЕХНИЧЕСКИХ ролях: главный инженер,
главный механик, главный энергетик, начальник цеха или компрессорной, их заместители, инженер
ОГМ/ОГЭ/КИПиА, технический директор. Снабженец помечается отдельно и стоит ниже.

ПРАВИЛА, нарушать нельзя:
1. **Ни одного телефона и ни одной фамилии, которых нет во входном тексте.** Выдуманный
   контакт хуже пропуска: по нему позвонят чужому человеку.
2. Число из десяти цифр — не обязательно телефон. Если рядом стоит «ИНН», «ОГРН», «р/с»,
   «КПП» или это номер документа — это не телефон, не пиши его.
3. Не считай технической ролью «главный инженер проекта» и «ГИП»: это проектировщик, машину
   на площадке он не выбирает. Также не считай «механик гаража», «начальник транспортного
   цеха», «инженер по закупкам», «инженер-сметчик».
4. Если людей в тексте нет — верни пустой список. Не угадывай.

ОТВЕТ — строго JSON, без пояснений:
{"lyudi":[{"imya":"","dolzhnost":"","rol":"техническая|снабжение|неясно","telefon":"",
"pochta":"","citata":"кусок текста, где это написано, до 150 знаков"}],
 "pochemu":"одно-два предложения: что это за документ и почему людей столько, сколько ты назвал;
 если список пуст, скажи, что в тексте есть вместо людей"}

Поле `pochemu` обязательно и когда людей нет. Причина техническая: наш клиент считает слишком
короткий ответ признаком сбоя провайдера и уходит в повторные попытки, поэтому честный ответ
«людей нет» без объяснения выглядит как поломка и тратит деньги владельца впустую.

ТЕКСТ:
"""
    lock = threading.Lock()
    client = G.make_client()
    itog, sch = [], {'lyudey': 0, 'teh': 0, 'vydumka': 0, 'err': 0}

    def odin(z):
        fajl, zak, telo = z
        try:
            o = G.call(client, [{'role': 'user', 'content': PROMPT + telo}],
                       model='claude-fable-5', attempts=4)
            txt = ''.join(b.text for b in o.content if b.type == 'text')
            m = re.search(r'\{.*\}', txt, re.S)
            return fajl, zak, telo, (json.loads(m.group(0)) if m else None)
        except Exception as e:  # noqa: BLE001
            return fajl, zak, telo, {'__err': f'{type(e).__name__}: {str(e)[:60]}'}

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for fajl, zak, telo, res in pool.map(odin, zadaniya):
            with lock:
                if not res or '__err' in (res or {}):
                    sch['err'] += 1
                    continue
                cif_vhod = cifry(telo)
                for ch in res.get('lyudi') or []:
                    t = ch.get('telefon') or ''
                    est = (not t) or (cifry(t)[-10:] and cifry(t)[-10:] in cif_vhod)
                    if t and not est:
                        sch['vydumka'] += 1
                    itog.append({**ch, 'fajl': fajl, 'zakupka': zak,
                                 'telefon_est_v_tekste': '1' if est else ''})
                    sch['lyudey'] += 1
                    if ch.get('rol') == 'техническая':
                        sch['teh'] += 1

    out = os.path.join(OUT, 'vlozheniya-lica.csv')
    cols = ['zakupka', 'fajl', 'imya', 'dolzhnost', 'rol', 'telefon', 'pochta',
            'telefon_est_v_tekste', 'citata']
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in itog:
            w.writerow(r)
    print(f'людей: {sch["lyudey"]}, технических: {sch["teh"]}, '
          f'номеров не из текста: {sch["vydumka"]}, сбоев: {sch["err"]} → {out}', file=sys.stderr)


if __name__ == '__main__':
    if '--doki' in sys.argv:
        shag_doki()
    elif '--fajly' in sys.argv:
        shag_fajly(predel=int(sys.argv[sys.argv.index('--predel') + 1])
                   if '--predel' in sys.argv else 200,
                   tolko=(sys.argv[sys.argv.index('--tolko') + 1]
                          if '--tolko' in sys.argv else None))
    elif '--tekst' in sys.argv:
        shag_tekst()
    elif '--lica' in sys.argv:
        shag_lica()
    else:
        sys.exit(__doc__)
