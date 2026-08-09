# -*- coding: utf-8 -*-
"""Вынуть ОБЛАСТЬ аттестации из графиков Ростехнадзора (source_url людей 'протокол РТН').

Документы — .docx/.xlsx/.rtf/.doc/.pdf, а не страницы. Читаем таблицу по ячейкам,
находим колонку «Область аттестации» по шапке, берём строку человека по ФИО.
"""
import sys, os, io, re, ssl, csv, json, gzip, time, hashlib, zipfile, sqlite3
import urllib.request, urllib.parse, collections, traceback
from concurrent.futures import ThreadPoolExecutor

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
KESH = r'C:\sender\_ops\rtn_cache'
os.makedirs(KESH, exist_ok=True)
VYHOD = r'C:\sender\_ops\PARK-ATTESTACIYA-OBLAST-2S.csv'
TC, TR = '\x01', '\x02'


def kachat(u):
    p = urllib.parse.urlsplit(u)
    url = urllib.parse.urlunsplit((p.scheme, p.netloc,
                                   urllib.parse.quote(p.path, safe='/%'), p.query, ''))
    r = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(r, timeout=90, context=CTX) as f:
        return f.read()


def vzyat(u):
    """Скачать с кешем на диск. Возвращает (bytes, откуда) либо (None, ошибка)."""
    p = os.path.join(KESH, hashlib.md5(u.encode()).hexdigest() + '.bin')
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return open(p, 'rb').read(), 'кеш'
    for popytka in range(3):
        try:
            b = kachat(u)
            open(p, 'wb').write(b)
            return b, 'сеть'
        except Exception as e:  # noqa: BLE001
            oshibka = '%s: %s' % (type(e).__name__, str(e)[:80])
            time.sleep(1.5 * (popytka + 1))
    return None, oshibka


def _snyat_tegi(x):
    x = re.sub(r'<[^>]+>', '', x)
    for a, b in (('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'")):
        x = x.replace(a, b)
    return x


def tablica_docx(b):
    z = zipfile.ZipFile(io.BytesIO(b))
    x = z.read('word/document.xml').decode('utf-8', 'replace')
    x = x.replace('<w:tab/>', ' ').replace('<w:br/>', ' ')
    x = re.sub(r'</w:p>', ' ', x)
    x = re.sub(r'</w:tc>', TC, x)
    x = re.sub(r'</w:tr>', TR, x)
    x = _snyat_tegi(x)
    return [[re.sub(r'\s+', ' ', c).strip() for c in r.split(TC)]
            for r in x.split(TR) if r.strip()]


def tablica_xlsx(b):
    z = zipfile.ZipFile(io.BytesIO(b))
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        s = z.read('xl/sharedStrings.xml').decode('utf-8', 'replace')
        ss = [re.sub(r'\s+', ' ', _snyat_tegi(m)).strip()
              for m in re.findall(r'<si>(.*?)</si>', s, re.S)]
    listy = sorted(n for n in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$', n))
    itog = []
    for n in listy:
        s = z.read(n).decode('utf-8', 'replace')
        for rw in re.findall(r'<row[^>]*>(.*?)</row>', s, re.S):
            yach = []
            for c in re.findall(r'<c\b([^>]*)>(.*?)</c>|<c\b([^>]*)/>', rw, re.S):
                atr, telo = (c[0], c[1]) if c[1] or c[0] else (c[2], '')
                v = re.search(r'<v>(.*?)</v>', telo, re.S)
                t = re.search(r'<is>(.*?)</is>', telo, re.S)
                if t:
                    yach.append(re.sub(r'\s+', ' ', _snyat_tegi(t.group(1))).strip())
                elif v:
                    z_ = v.group(1)
                    if 't="s"' in atr:
                        yach.append(ss[int(z_)] if z_.isdigit() and int(z_) < len(ss) else '')
                    else:
                        yach.append(_snyat_tegi(z_).strip())
                else:
                    yach.append('')
            if any(yach):
                itog.append(yach)
    return itog


def tablica_rtf(b):
    s = b.decode('cp1251', 'replace')
    s = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode('cp1251', 'replace'), s)
    s = s.replace('\\cell', TC).replace('\\row', TR).replace('\\par', ' ')
    s = re.sub(r'\{\\\*[^{}]*\}', ' ', s)
    s = re.sub(r'\\[a-zA-Z]+-?\d* ?', ' ', s)
    s = s.replace('{', ' ').replace('}', ' ')
    return [[re.sub(r'\s+', ' ', c).strip() for c in r.split(TC)]
            for r in s.split(TR) if r.strip()]


def tablica_html(b):
    s = b.decode('utf-8', 'replace')
    if s.count('�') > 40:
        s = b.decode('cp1251', 'replace')
    s = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', s, flags=re.S | re.I)
    s = re.sub(r'</t[dh]>', TC, s, flags=re.I)
    s = re.sub(r'</tr>', TR, s, flags=re.I)
    s = re.sub(r'</(p|div|br|li)>|<br\s*/?>', TR, s, flags=re.I)
    s = _snyat_tegi(s)
    return [[re.sub(r'\s+', ' ', c).strip() for c in r.split(TC)]
            for r in s.split(TR) if r.strip()]


def tablica(u, b):
    if b[:2] == b'PK':
        try:
            imena = zipfile.ZipFile(io.BytesIO(b)).namelist()
        except Exception:  # noqa: BLE001
            return None, 'zip не читается'
        if 'word/document.xml' in imena:
            return tablica_docx(b), 'docx'
        if any(n.startswith('xl/') for n in imena):
            return tablica_xlsx(b), 'xlsx'
        return None, 'zip неизвестного вида'
    if b[:5] == b'%PDF-':
        return None, 'PDF — таблица не читается стандартной библиотекой'
    if b[:5] == b'{\\rtf':
        return tablica_rtf(b), 'rtf'
    if b[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return None, 'старый .doc (OLE) — не читается стандартной библиотекой'
    nach = b[:600].decode('utf-8', 'replace').lower()
    if '<html' in nach or '<!doctype' in nach:
        return tablica_html(b), 'html'
    return None, 'формат не опознан: ' + repr(b[:12])


# ---------- расшифровка кода области ----------
GRUPPY = {
    'А.1': 'Основы промышленной безопасности (общие требования)',
    'Б.1': 'Химическая, нефтехимическая и нефтеперерабатывающая промышленность',
    'Б.2': 'Нефтяная и газовая промышленность',
    'Б.3': 'Металлургическая промышленность',
    'Б.4': 'Горнорудная промышленность',
    'Б.5': 'Угольная промышленность, ведение горных работ',
    'Б.6': 'Маркшейдерское обеспечение горных работ',
    'Б.7': 'Объекты газораспределения и газопотребления (ГАЗ)',
    'Б.8': 'Оборудование, работающее под ИЗБЫТОЧНЫМ ДАВЛЕНИЕМ (котлы, сосуды, трубопроводы пара)',
    'Б.9': 'Подъёмные сооружения',
    'Б.10': 'Транспортирование опасных веществ',
    'Б.11': 'Объекты хранения и переработки растительного сырья',
    'Б.12': 'Взрывные работы',
    'В.1': 'Гидротехнические сооружения',
    'В.2': 'Гидротехнические сооружения',
    'Г.1': 'Электроустановки потребителей (энергобезопасность)',
    'Г.2': 'Тепловые энергоустановки и тепловые сети',
    'Г.3': 'Электрические станции и сети',
}
KOD = re.compile(r'(?<![А-ЯЁA-Z0-9])([АБВГД])\.(\d{1,2})(?:\.(\d{1,3}))?')


def rasshifrovka(tekst, tema):
    najd, vidno = [], []
    for m in KOD.finditer(tekst or ''):
        bukva, grup, pod = m.group(1), m.group(2), m.group(3)
        kluch = '%s.%s' % (bukva, grup)
        if bukva == 'А':
            kluch = 'А.1'
        z = GRUPPY.get(kluch)
        if z and z not in najd:
            najd.append(z)
        vidno.append(m.group(0))
    if najd:
        return '; '.join(najd)
    if (tekst or '').strip():
        return ('энергобезопасность, код проверки знаний — расшифровка не подтверждена; тема документа: '
                + (tema or 'не найдена')[:150]) if tema else 'код не расшифрован'
    return ''


# ---------- разбор таблицы ----------
SHAPKA_OBL = re.compile(r'област[ьи]\s+аттестац|област[ьи]\s+провер|наименование\s+област', re.I)
SHAPKA_FIO = re.compile(r'фамилия|ф\.?\s*и\.?\s*о', re.I)
SHAPKA_DOL = re.compile(r'должност', re.I)
SHAPKA_ORG = re.compile(r'наименование\s+организац|организац|предприят', re.I)
# Запасная шапка: у Средне-Поволжского управления колонка называется не «область
# аттестации», а «Группа, категория персонала» — это группа по электробезопасности.
# Берём её ТОЛЬКО когда колонки «область» в документе нет, и подписываем как группу.
SHAPKA_GRUP = re.compile(r'групп[аы][,\s]+категори|группа\s+по\s+электробез', re.I)
TEMA = re.compile(r'(Список[^\x01\x02]{20,400}|График[^\x01\x02]{20,400})')


def norm(s):
    s = (s or '').lower().replace('ё', 'е')
    s = re.sub(r'[^а-яa-z]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def familiya(s):
    ch = norm(s).split()
    return ch[0] if ch else ''


def shapka(rows):
    """Индексы колонок по строке-шапке.

    Возвращает (i_fio, i_obl, i_dol, i_org, nomer_stroki, vid_kolonki), где vid_kolonki —
    'область' или 'группа'. Сначала ищем настоящую «Область аттестации» по ВСЕМ строкам
    шапки и только потом соглашаемся на «Группу, категорию персонала»: иначе документ, где
    есть обе, был бы разобран по второстепенной колонке."""
    for shablon, vid in ((SHAPKA_OBL, 'область'), (SHAPKA_GRUP, 'группа')):
        for i, r in enumerate(rows[:40]):
            i_obl = next((j for j, c in enumerate(r) if shablon.search(c)), None)
            if i_obl is None:
                continue
            i_fio = next((j for j, c in enumerate(r) if SHAPKA_FIO.search(c)), None)
            i_dol = next((j for j, c in enumerate(r) if SHAPKA_DOL.search(c)), None)
            i_org = next((j for j, c in enumerate(r) if SHAPKA_ORG.search(c)), None)
            return i_fio, i_obl, i_dol, i_org, i, vid
    return None, None, None, None, None, None


def main():
    drop_url, drop_token = sys.argv[1], sys.argv[2]
    predel = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True); c.row_factory = sqlite3.Row
    cur = c.cursor()
    cur.execute("""select inn, person, post, coalesce(source_url,'') u
                   from people where prinadlezhnost_chem like 'протокол РТН%'""")
    lyudi = [dict(r) for r in cur.fetchall()]
    po_url = collections.defaultdict(list)
    for l in lyudi:
        po_url[l['u']].append(l)
    urls = sorted(po_url, key=lambda u: -len(po_url[u]))
    if predel:
        urls = urls[:predel]

    dok = {}
    def rabota(u):
        b, otkuda = vzyat(u)
        if b is None:
            dok[u] = ('скачивание: ' + otkuda, None, None, None)
            return
        try:
            rows, vid = tablica(u, b)
        except Exception:  # noqa: BLE001
            dok[u] = ('разбор упал: ' + traceback.format_exc().splitlines()[-1][:90], None, None, None)
            return
        if rows is None:
            dok[u] = (vid, None, None, len(b))
            return
        ploskiy = ' '.join(' '.join(r) for r in rows)
        m = TEMA.search(ploskiy)
        tema = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
        dok[u] = ('', rows, (vid, tema), len(b))

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(rabota, urls))

    itog, bez = [], collections.Counter()
    pokryto_url = 0
    for u in urls:
        oshibka, rows, meta, razmer = dok[u]
        if rows is None:
            bez['документ не прочитан: ' + oshibka[:60]] += len(po_url[u])
            continue
        vid, tema = meta
        i_fio, i_obl, i_dol, i_org, i_sh, vid_kol = shapka(rows)
        if i_obl is None:
            bez['в документе нет колонки «Область аттестации» (%s)' % vid] += len(po_url[u])
            continue
        # индекс: фамилия -> строки таблицы
        po_fam = collections.defaultdict(list)
        for r in rows[(i_sh or 0) + 1:]:
            for j, cl in enumerate(r):
                if i_fio is not None and j != i_fio:
                    continue
                f = familiya(cl)
                if f and len(f) > 2 and len(norm(cl).split()) >= 2:
                    po_fam[f].append((j, r))
        nashli_zdes = 0
        for l in po_url[u]:
            nc = norm(l['person'])
            f = familiya(l['person'])
            kand = po_fam.get(f, [])
            tochno = [(j, r) for j, r in kand if norm(r[j]) == nc]
            if not tochno:
                tochno = [(j, r) for j, r in kand
                          if nc and (nc in norm(r[j]) or norm(r[j]) in nc) and len(norm(r[j]).split()) >= 2]
            if not tochno and len(kand) == 1:
                tochno = kand
            if not tochno:
                bez['ФИО не найдено в документе' if not kand else 'однофамильцы, не различить'] += 1
                continue
            j, r = tochno[0]
            obl = r[i_obl].strip() if i_obl < len(r) else ''
            if vid_kol == 'группа' and re.match(r'^[IVX2-5]{1,3}$', obl):
                obl = 'группа по электробезопасности ' + obl
            if not obl or re.match(r'^\d{1,2}[:.]\d{2}$', obl):
                # колонка не та либо пустая — ищем код в самой строке
                kody = KOD.findall(' '.join(r))
                obl = ' '.join(m.group(0) for m in KOD.finditer(' '.join(r))) if kody else ''
            if not obl:
                bez['строка человека найдена, но область пуста'] += 1
                continue
            citata = ' | '.join(x for x in r if x)[:400]
            itog.append({
                'inn': l['inn'], 'chelovek': l['person'], 'dolzhnost': l['post'],
                'oblast': re.sub(r'\s+', ' ', obl)[:200],
                'chto_znachit_oblast': (
                    'группа по электробезопасности (колонка документа «Группа, категория '
                    'персонала»); тема документа: ' + (tema or '')[:150]
                    if vid_kol == 'группа' else rasshifrovka(obl, tema)),
                'ssylka': u, 'citata': re.sub(r'\s+', ' ', citata),
            })
            nashli_zdes += 1
        if nashli_zdes:
            pokryto_url += 1

    COLS = ['inn', 'chelovek', 'dolzhnost', 'oblast', 'chto_znachit_oblast', 'ssylka', 'citata']
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=';')
        w.writeheader()
        for r in itog:
            w.writerow(r)
    syr = open(VYHOD, 'rb').read()
    gz = gzip.compress(syr)
    try:
        rq = urllib.request.Request(drop_url.rstrip('/') + '/PARK-ATTESTACIYA-OBLAST-2S.csv.gz',
                                    data=gz, method='PUT',
                                    headers={'X-Drop-Token': drop_token})
        with urllib.request.urlopen(rq, timeout=180, context=CTX) as rr:
            zagruzka = 'дроп %s' % rr.getcode()
    except Exception as e:  # noqa: BLE001
        zagruzka = 'дроп НЕ вышло: %s %s' % (type(e).__name__, str(e)[:120])

    print('=== ПРИМЕРЫ ===')
    for r in itog[:6]:
        print(json.dumps(r, ensure_ascii=False)[:400])
    print('=== ПОЧЕМУ НЕ ВЫШЛО ===')
    for k, v in bez.most_common(14):
        print('%6d  %s' % (v, k))
    prichiny = collections.Counter()
    for u in urls:
        o, rows, meta, _ = dok[u]
        prichiny[(o[:55] if rows is None else 'прочитан ' + meta[0])] += 1
    print('=== ДОКУМЕНТЫ ===')
    for k, v in prichiny.most_common(12):
        print('%6d  %s' % (v, k))
    print('=== СЧЁТЧИКИ ===')
    print('ссылок всего        %d' % len(urls))
    print('людей всего         %d' % sum(len(po_url[u]) for u in urls))
    print('строк с областью    %d' % len(itog))
    print('ИНН покрыто         %d из %d' % (len({r['inn'] for r in itog}),
                                            len({l['inn'] for l in lyudi})))
    print('ссылок дали данные  %d' % pokryto_url)
    print('csv %d байт, gz %d, %s' % (len(syr), len(gz), zagruzka))


main()
