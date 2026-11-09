# -*- coding: utf-8 -*-
r"""Сверка «рынка Meyer» с тем, что мы уже нашли (09.11, владелец: «162к компаний Meyer — это какие, градация,
особенно по тем, какие мы уже находили, сколько мы нашли из них?»).

Рынок = юрлица с доходом от 30 млн (revexp) с основным ОКВЭД из классов, которые дают ~95 % покупателей Meyer
(ca\ca-pokupateli.json, первые 60 классов). ОКВЭД: реестр МСП (rsmp), не-МСП — свои базы и добор ca_okved_dobor.
По каждому классу: всего; в базе обзвона (по направлению, если в таблице есть такая колонка); со сделкой Meyer
(любой), купили у Meyer, провал Meyer больше года без активных сделок; со сделкой КЦ/СЦ.
Заодно — ca\ca-inn-okved-30.jsonl (ИНН, основной ОКВЭД, доход, МСП) для следующих шагов без повторного разбора.
Только чтение баз. Выход: ca\ca-meyer-sverka.json (+ дроп). Запуск: python ca_meyer_sverka.py (сам в фон).
"""
import collections, glob, io, json, os, re, sqlite3, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
FNS = r'C:\sender\_ops\ak\fns'
D = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    os.makedirs(ПАПКА, exist_ok=True)
    лог = os.path.join(ПАПКА, 'ca_meyer_sverka_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(20)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-600:])
    sys.exit(0)

ПРОГ = os.path.join(ПАПКА, 'ca-meyer-sverka-progress.json')
ЗАМОК = os.path.join(ПАПКА, 'ca_meyer_sverka.lock')
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


def main():
    # ---------- 1. классы рынка Meyer ----------
    пк = json.load(io.open(os.path.join(ПАПКА, 'ca-pokupateli.json'), encoding='utf-8'))
    строки = пк['направления']['Meyer']['купили']['классы']
    классы = {r['класс']: r['покупателей'] for r in строки if r['накоп_%'] - r['доля_%'] < 95}
    # ---------- 2. сделки ----------
    vse = json.load(io.open(os.path.join(D, 'sdelki-vse-1410.json'), encoding='utf-8'))
    сд = {}
    for инн, сс in vse.items():
        m = [x for x in сс if x[0] == 'meyer']
        к = set()
        if m:
            к.add('сделка Meyer')
            if any(x[1] == 'Успешна' for x in m):
                к.add('купили у Meyer')
            провал = [x for x in m if x[1] == 'Провалена']
            посл = max(max(x[2] or '', x[3] or '') for x in m)
            if провал and not any(x[1] == 'В работе' for x in сс) and посл < ГОД_НАЗАД:
                к.add('провал Meyer > года, активных нет')
        if any(x[0] in ('kc', 'sc') for x in сс):
            к.add('сделка КЦ/СЦ')
        сд[инн] = к
    отметка(этап='сделки', инн=len(сд))
    # ---------- 3. доходы от 30 млн ----------
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
                    if инн.isdigit() and v >= 3e7:
                        доход[инн] = v
    отметка(этап='revexp', от_30млн=len(доход))
    # ---------- 4. ОКВЭД: МСП ----------
    фф = [f for f in glob.glob(os.path.join(FNS, 'data-*-structure-*.zip')) if os.path.exists(f + '.ok')]
    rsmp = max(фф, key=os.path.getmtime)
    окв = {}  # инн -> (осн, откуда)
    with zipfile.ZipFile(rsmp) as z:
        for i, имя in enumerate([x for x in z.namelist() if x.lower().endswith('.xml')]):
            with z.open(имя) as fh:
                for el in документы(fh):
                    инн, осн = '', ''
                    for ch in el.iter():
                        т = ch.tag
                        if т.endswith('ОргВклМСП'):
                            инн = ch.get('ИННЮЛ') or ''
                        elif т.endswith('СвОКВЭДОсн'):
                            осн = ch.get('КодОКВЭД') or ''
                    if инн in доход and осн:
                        окв[инн] = (осн, 'МСП')
            if i % 200 == 0:
                отметка(этап='rsmp', файл=i, с_оквэд=len(окв))
    # ---------- 5. ОКВЭД: не-МСП из своих баз и добора ----------
    def взять(инн, о, ист):
        инн = str(инн or '').strip()
        м = re.match(r'\s*(\d{2}(?:\.\d{1,2}){0,2})', str(о or ''))
        if м and инн in доход and инн not in окв:
            окв[инн] = (м.group(1), ист)
    for бд, q, ист in ((r'C:/sender/obzvon-index.db', 'select inn, okved_main from obzvon', 'обзвон'),
                       (r'C:/sender/enrich.db', 'select inn, okved_main from requisites', 'enrich'),
                       (r'C:/sender/enrich.db', 'select inn, okved from companies', 'enrich')):
        try:
            con = sqlite3.connect('file:%s?mode=ro' % бд, uri=True, timeout=120)
            for инн, о in con.execute(q):
                взять(инн, о, ист)
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
                взять(y.get('inn') or y.get('инн'), y.get('оквэд') or y.get('okved'), 'checko/dadata')
    п = os.path.join(ПАПКА, 'ca-inn-okved-30.jsonl')
    with io.open(п, 'w', encoding='utf-8') as f:
        for инн, (о, ист) in окв.items():
            f.write(json.dumps({'inn': инн, 'оквэд': о, 'доход': доход[инн], 'откуда': ист}, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    отметка(этап='оквэд', от_30млн=len(доход), с_оквэд=len(окв))
    # ---------- 6. база обзвона: направление ----------
    база, колонки, кол_напр = {}, [], None
    try:
        con = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=120)
        колонки = [r[1] for r in con.execute('pragma table_info(obzvon)')]
        for к in колонки:
            if re.search(r'napr|direct|baza|base|segment|brand|source|istoch|funnel', к, re.I):
                кол_напр = к
                break
        q = 'select inn, %s from obzvon' % (кол_напр or "'база'")
        for инн, н in con.execute(q):
            база[str(инн or '').strip()] = str(н or '?')[:30]
        con.close()
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_база=repr(e)[:200])
    # ---------- 7. сверка ----------
    по_кл = collections.defaultdict(collections.Counter)
    итого = collections.Counter()
    for инн, (о, _ист) in окв.items():
        кл = класс(о)
        if кл not in классы:
            continue
        к = по_кл[кл]
        метки = ['всего']
        if инн in база:
            метки += ['в базе обзвона', 'в базе: ' + база[инн]]
        метки += sorted(сд.get(инн, ()))
        if инн not in база and not сд.get(инн):
            метки.append('новые (нет ни в базе, ни в сделках)')
        for м in метки:
            к[м] += 1
            итого[м] += 1
    итог = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'юл_от_30млн': len(доход), 'с_оквэд': len(окв),
            'без_оквэд': len(доход) - len(окв), 'колонки_обзвона': колонки, 'колонка_направления': кол_напр,
            'итого': dict(итого),
            'классы': [dict(по_кл[кл], класс=кл, покупателей_meyer=классы[кл]) for кл in классы]}
    п = os.path.join(ПАПКА, 'ca-meyer-sverka.json')
    with open(п, 'w', encoding='utf-8') as f:
        json.dump(итог, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    if os.path.isdir(D):
        import shutil
        shutil.copyfile(п, os.path.join(D, 'ca-meyer-sverka.json'))
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
