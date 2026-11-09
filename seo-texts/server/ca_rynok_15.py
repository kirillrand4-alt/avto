# -*- coding: utf-8 -*-
r"""Рынок «похожих на покупателей» с порогом выручки 15 млн (09.11, владелец: «у ядровых Meyer выручку снизим до
15 млн, а у КЦ для всех снизим до 15 млн») + ИП по видам деятельности.

По направлениям КЦ и Meyer: покупатели (выигранная сделка) -> основной ОКВЭД (реестр МСП для ЮЛ и ИП, свои базы
и добор для не-МСП) -> класс XX.XX. По каждому классу: покупателей всего / ЮЛ / ИП / ЮЛ от 15 млн; в РФ ЮЛ от 15 и
от 30 млн; ИП в реестре МСП (всего и по численности ССЧР); проникновение = покупатели-ЮЛ от 15 млн / ЮЛ от 15 млн
(одна база сравнения); группы проникновения >=3 % (ядро) / 1–3 % / <1 %; рынок для 80 и 95 % покупателей.
Сверка ЮЛ от 15 млн с базой обзвона (base_label) и сделками: в базе, сделка, купили, провал > года, новые.
ИП — только счётчики, ИНН и ФИО ИП не сохраняются. Только чтение баз. Выход: ca\ca-rynok-15.json (+ дроп).
"""
import collections, glob, io, json, os, re, sqlite3, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

import collections, glob, io, json, os, re, sqlite3, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
FNS = r'C:\sender\_ops\ak\fns'
D = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    os.makedirs(ПАПКА, exist_ok=True)
    лог = os.path.join(ПАПКА, 'ca_rynok_15_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(20)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-600:])
    sys.exit(0)

ПРОГ = os.path.join(ПАПКА, 'ca-rynok-15-progress.json')
ЗАМОК = os.path.join(ПАПКА, 'ca_rynok_15.lock')
try:
    _fd = os.open(ЗАМОК, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(_fd, str(os.getpid()).encode())
    os.close(_fd)
except FileExistsError:
    _pid = open(ЗАМОК).read().strip()
    if _pid and _pid in subprocess.run(['tasklist', '/FI', 'PID eq %s' % _pid], capture_output=True, text=True).stdout:
        print('уже запущен, pid', _pid)
        sys.exit(0)
    open(ЗАМОК, 'w').write(str(os.getpid()))

ГОД_НАЗАД = '2025-11-09'


def отметка(**k):
    k['обновлено'] = time.strftime('%H:%M:%S')
    with open(ПРОГ, 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)
    print(json.dumps(k, ensure_ascii=False)[:300], flush=True)


def документы(fh):
    корень = None
    for ev, el in ET.iterparse(fh, events=('start', 'end')):
        if корень is None:
            корень = el
        if ev == 'end' and el.tag.endswith('Документ'):
            yield el
            корень.clear()


def класс(код):
    return '.'.join(str(код or '').split('.')[:2])


ПОРОГ = 15e6
НАПР = {'kc': 'КЦ', 'meyer': 'Meyer'}


def ссч_полоса(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 'нет'
    return '0' if v <= 0 else '1–4' if v < 5 else '5–14' if v < 15 else '15+'


def main():
    # ---------- 1. сделки (выгрузка 14.10 по всем направлениям + CSV КЦ/СЦ) ----------
    vse = json.load(io.open(os.path.join(D, 'sdelki-vse-1410.json'), encoding='utf-8'))
    сд = collections.defaultdict(set)   # инн -> метки
    купили = collections.defaultdict(set)  # напр -> {инн}
    for инн, сс in vse.items():
        for к, н in НАПР.items():
            m = [x for x in сс if x[0] == к]
            if not m:
                continue
            сд[инн].add('сделка ' + н)
            if any(x[1] == 'Успешна' for x in m):
                сд[инн].add('купили ' + н)
                купили[н].add(инн)
            посл = max(max(x[2] or '', x[3] or '') for x in m)
            if any(x[1] == 'Провалена' for x in m) and not any(x[1] == 'В работе' for x in сс) and посл < ГОД_НАЗАД:
                сд[инн].add('провал %s > года, активных нет' % н)
        if any(x[0] == 'sc' for x in сс):
            сд[инн].add('сделка СЦ')
    нужные = set().union(*купили.values())
    отметка(этап='сделки', **{н: len(v) for н, v in купили.items()})
    # ---------- 2. доходы ----------
    доход = {}
    with zipfile.ZipFile(os.path.join(FNS, 'revexp.zip')) as z:
        for имя in z.namelist():
            with z.open(имя) as fh:
                for el in документы(fh):
                    инн, v = '', 0.0
                    for ch in el:
                        if 'СведНП' in ch.tag:
                            инн = ch.get('ИННЮЛ') or ''
                        elif 'ДохРасх' in ch.tag:
                            try:
                                v = float(ch.get('СумДоход') or 0)
                            except ValueError:
                                pass
                    if инн.isdigit() and (v >= ПОРОГ or инн in нужные):
                        доход[инн] = v
    отметка(этап='revexp', от_15млн=sum(1 for v in доход.values() if v >= ПОРОГ))
    # ---------- 3. реестр МСП: ОКВЭД ЮЛ, ИП по классам ----------
    фф = [f for f in glob.glob(os.path.join(FNS, 'data-*-structure-*.zip')) if os.path.exists(f + '.ok')]
    rsmp = max(фф, key=os.path.getmtime)
    окв = {}  # инн ЮЛ (от 15 млн или покупатель) / ИП-покупатель -> осн
    ип_кл = collections.defaultdict(collections.Counter)  # класс -> полоса ССЧ -> число ИП
    ип_пок_ссч = collections.defaultdict(collections.Counter)  # напр -> полоса ССЧ (ИП-покупатели)
    with zipfile.ZipFile(rsmp) as z:
        for i, имя in enumerate([x for x in z.namelist() if x.lower().endswith('.xml')]):
            with z.open(имя) as fh:
                for el in документы(fh):
                    инн, осн, ип = '', '', False
                    ссч = el.get('ССЧР')
                    for ch in el.iter():
                        т = ch.tag
                        if т.endswith('ОргВклМСП'):
                            инн = ch.get('ИННЮЛ') or ''
                        elif т.endswith('ИПВклМСП'):
                            инн, ип = ch.get('ИННФЛ') or '', True
                        elif т.endswith('СвОКВЭДОсн'):
                            осн = ch.get('КодОКВЭД') or ''
                    if not осн:
                        continue
                    if ип:
                        ип_кл[класс(осн)][ссч_полоса(ссч)] += 1
                        if инн in нужные:
                            окв[инн] = осн
                            for н, мн in купили.items():
                                if инн in мн:
                                    ип_пок_ссч[н][ссч_полоса(ссч)] += 1
                    elif доход.get(инн, 0) >= ПОРОГ or инн in нужные:
                        окв[инн] = осн
            if i % 200 == 0:
                отметка(этап='rsmp', файл=i, с_оквэд=len(окв))
    # ---------- 4. не-МСП: свои базы и добор ----------
    def взять(инн, о):
        инн = str(инн or '').strip()
        м = re.match(r'\s*(\d{2}(?:\.\d{1,2}){0,2})', str(о or ''))
        if м and инн not in окв and (доход.get(инн, 0) >= ПОРОГ or инн in нужные):
            окв[инн] = м.group(1)
    for бд, q in ((r'C:/sender/obzvon-index.db', 'select inn, okved_main from obzvon'),
                  (r'C:/sender/enrich.db', 'select inn, okved_main from requisites'),
                  (r'C:/sender/enrich.db', 'select inn, okved from companies')):
        try:
            con = sqlite3.connect('file:%s?mode=ro' % бд, uri=True, timeout=120)
            for инн, о in con.execute(q):
                взять(инн, о)
            con.close()
        except Exception as e:  # noqa: BLE001
            отметка(ошибка=repr(e)[:200], q=q)
    for путь in sorted(set(glob.glob(os.path.join(DIR, '*okved*.jsonl')) + glob.glob(os.path.join(DIR, '*checko*.jsonl')) +
                           glob.glob(os.path.join(DIR, '*dadata*.jsonl')) + [os.path.join(ПАПКА, 'ca-okved-dobor.jsonl')])):
        if not os.path.exists(путь):
            continue
        for s in io.open(путь, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
            except ValueError:
                continue
            if isinstance(y, dict):
                взять(y.get('inn') or y.get('инн'), y.get('оквэд') or y.get('okved'))
    юл15 = {инн for инн, v in доход.items() if v >= ПОРОГ}
    рф = collections.defaultdict(collections.Counter)  # класс -> 'юл15'/'юл30'
    for инн in юл15:
        if инн in окв:
            рф[класс(окв[инн])]['юл15'] += 1
            if доход[инн] >= 3e7:
                рф[класс(окв[инн])]['юл30'] += 1
    отметка(этап='оквэд', юл_от_15=len(юл15), юл_от_15_с_оквэд=sum(1 for и in юл15 if и in окв))
    # ---------- 5. база обзвона ----------
    база = {}
    try:
        con = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=120)
        for инн, н in con.execute('select inn, base_label from obzvon'):
            база[str(инн or '').strip()] = str(н or '?')[:30]
        con.close()
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_база=repr(e)[:200])
    # ---------- 6. по направлениям ----------
    итог = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'порог': ПОРОГ, 'юл_от_15': len(юл15),
            'юл_от_15_без_оквэд': sum(1 for и in юл15 if и not in окв), 'направления': {}}
    for н, мн in купили.items():
        пк = collections.defaultdict(collections.Counter)
        for инн in мн:
            if инн not in окв:
                пк['?']['всего'] += 1
                continue
            к = пк[класс(окв[инн])]
            к['всего'] += 1
            к['ИП' if len(инн) == 12 else 'ЮЛ'] += 1
            if len(инн) == 10 and доход.get(инн, 0) >= ПОРОГ:
                к['ЮЛ от 15'] += 1
        без = пк.pop('?', {}).get('всего', 0)
        всего_с_окв = sum(к['всего'] for к in пк.values())
        строки, накоп = [], 0
        for кл, к in sorted(пк.items(), key=lambda x: -x[1]['всего']):
            накоп += к['всего']
            ю15 = рф[кл]['юл15']
            пр = 100 * к['ЮЛ от 15'] / ю15 if ю15 else 0
            строки.append({'класс': кл, 'покупателей': к['всего'], 'ЮЛ': к['ЮЛ'], 'ИП': к['ИП'], 'ЮЛ_от_15': к['ЮЛ от 15'],
                           'накоп_%': round(100 * накоп / всего_с_окв, 1), 'доля_%': round(100 * к['всего'] / всего_с_окв, 1),
                           'рф_юл_от_15': ю15, 'рф_юл_от_30': рф[кл]['юл30'], 'проникновение_%': round(пр, 2),
                           'группа': 'ядро ≥3%' if пр >= 3 else '1–3%' if пр >= 1 else '<1%',
                           'рф_ип': dict(ип_кл[кл])})
        # сверка ЮЛ от 15 млн в классах до 95 % покупателей
        классы95 = {r['класс']: r for r in строки if r['накоп_%'] - r['доля_%'] < 95}
        св = collections.defaultdict(collections.Counter)
        for инн in юл15:
            if инн not in окв:
                continue
            r = классы95.get(класс(окв[инн]))
            if not r:
                continue
            for гр in (r['класс'], 'группа ' + r['группа'], 'все 95%') + (('все 80%',) if r['накоп_%'] - r['доля_%'] < 80 else ()):
                к = св[гр]
                к['всего'] += 1
                if инн in база:
                    к['в базе обзвона'] += 1
                    к['в базе: ' + база[инн]] += 1
                for м in сд.get(инн, ()):
                    к[м] += 1
                if инн not in база and not сд.get(инн):
                    к['новые'] += 1
        for r in строки:
            if r['класс'] in св:
                r['сверка'] = dict(св[r['класс']])
        итог['направления'][н] = {
            'покупателей': len(мн), 'без_оквэд': без, 'ИП_покупатели_по_ССЧ': dict(ип_пок_ссч[н]),
            'рынок': {гр: dict(св[гр]) for гр in св if not re.match(r'\d', гр)},
            'ип_в_классах_ядра': dict(sum((collections.Counter(ип_кл[r['класс']]) for r in строки if r['группа'] == 'ядро ≥3%'
                                           and r['класс'] in классы95), collections.Counter())),
            'классы': строки[:150]}
    п = os.path.join(ПАПКА, 'ca-rynok-15.json')
    with open(п, 'w', encoding='utf-8') as f:
        json.dump(итог, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    if os.path.isdir(D):
        import shutil
        shutil.copyfile(п, os.path.join(D, 'ca-rynok-15.json'))
    отметка(этап='готово')


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:  # noqa: BLE001
        отметка(этап='ошибка', ошибка=repr(e)[:500])
        raise
    finally:
        try:
            os.remove(ЗАМОК)
        except OSError:
            pass
