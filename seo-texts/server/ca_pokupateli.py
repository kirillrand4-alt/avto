# -*- coding: utf-8 -*-
r"""Портрет покупателя КЦ / СЦ / Meyer по реальным сделкам и оценка «сколько всего таких компаний в РФ».

09.11, владелец: «можешь прикинуть, сколько всего покупателей КЦ/Meyer? ОКВЭДы покупателей есть где-то на сервере,
но, возможно, не все — сверить с реальными сделками».
1. Покупатели = ИНН с выигранной сделкой («Успешна») по направлению: sdelki-vse-1410.json (все направления, по ИНН)
   + kc-sc-sdelki-0910.csv (КЦ/СЦ). Отдельно — все, кто приходил со сделкой (любой статус) = «интерес».
2. ОКВЭД покупателя: реестр МСП ФНС (rsmp, качает ca_fns_reestr.py — ждём файл), затем свои базы (обзвон, enrich,
   checko). Доход — revexp.
3. По классу ОКВЭД (XX.XX, основной код): покупателей, всего компаний в РФ (МСП по реестру + не-МСП, у кого ОКВЭД
   есть в своих базах), «проникновение» = покупатели / все. Оценка рынка: классы, дающие 80 % и 95 % покупателей,
   с порогом дохода = 10-й процентиль дохода покупателей этого класса.
Только чтение; выход — C:\sender\server\ca\ca-pokupateli.json (+ дроп). Запуск: python ca_pokupateli.py (сам в фон).
"""
import collections, csv, glob, io, json, os, re, sqlite3, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
FNS = r'C:\sender\_ops\ak\fns'
D = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    os.makedirs(ПАПКА, exist_ok=True)
    лог = os.path.join(ПАПКА, 'ca_pokupateli_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(20)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-600:])
    sys.exit(0)

ПРОГ = os.path.join(ПАПКА, 'ca-pokupateli-progress.json')
ЗАМОК = os.path.join(ПАПКА, 'ca_pokupateli.lock')
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


def полоса(v):
    return ('≥1 млрд' if v >= 1e9 else '300 млн–1 млрд' if v >= 3e8 else '100–300 млн' if v >= 1e8 else
            '30–100 млн' if v >= 3e7 else '10–30 млн' if v >= 1e7 else '<10 млн / нет')


ПОЛОСЫ = ('<10 млн / нет', '10–30 млн', '30–100 млн', '100–300 млн', '300 млн–1 млрд', '≥1 млрд')
НИЗ = {'<10 млн / нет': 0, '10–30 млн': 1e7, '30–100 млн': 3e7, '100–300 млн': 1e8, '300 млн–1 млрд': 3e8, '≥1 млрд': 1e9}


def main():
    # ---------- 1. сделки ----------
    напр_инн = collections.defaultdict(lambda: collections.defaultdict(set))  # напр -> статус -> {инн}
    vse = json.load(io.open(os.path.join(D, 'sdelki-vse-1410.json'), encoding='utf-8'))
    for инн, сд in vse.items():
        for d in сд or []:
            н, ст = (list(d) + ['', ''])[:2]
            н = {'kc': 'КЦ', 'sc': 'СЦ', 'meyer': 'Meyer'}.get(н, н)
            напр_инн[н]['все'].add(инн)
            if ст == 'Успешна':
                напр_инн[н]['купили'].add(инн)
    без_инн = collections.Counter()
    fh = io.open(os.path.join(D, 'kc-sc-sdelki-0910.csv'), encoding='utf-8-sig')
    кол = next(csv.reader([fh.readline()], delimiter=';'))
    for r in csv.DictReader(fh, fieldnames=кол, delimiter=';'):
        в = (r.get('ВОРОНКА') or '').strip()
        н = 'СЦ' if в.startswith('СЦ') else 'Meyer' if 'MEYER' in в.upper() else 'КЦ'
        инн = re.sub(r'\D', '', r.get('INN') or '')
        if len(инн) not in (10, 12):
            без_инн[н] += 1
            continue
        напр_инн[н]['все'].add(инн)
        if r.get('СТАТУС') == 'Успешна':
            напр_инн[н]['купили'].add(инн)
    fh.close()
    нужные = set().union(*[s for н in напр_инн.values() for s in н.values()])
    отметка(этап='сделки', **{н: {к: len(v) for к, v in с.items()} for н, с in напр_инн.items()})
    # ---------- 2. ждём реестр МСП (его качает ca_fns_reestr.py) ----------
    for _ in range(240):
        # метку .ok кладёт ca_fns_reestr.py после проверки CRC всего архива (09.11: первый архив был битый)
        фф = [f for f in glob.glob(os.path.join(FNS, 'data-*-structure-*.zip')) if os.path.exists(f + '.ok')]
        if фф:
            break
        отметка(этап='жду rsmp')
        time.sleep(60)
    else:
        raise SystemExit('rsmp не появился за 4 часа')
    rsmp = max(фф, key=os.path.getmtime)
    # ---------- 3. доходы (revexp) ----------
    отметка(этап='revexp')
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
                    if инн.isdigit() and (v >= 1e7 or инн in нужные):
                        доход[int(инн)] = v
    отметка(этап='revexp-готов', с_доходом_от_10млн=len(доход))
    # ---------- 4. МСП: вселенная по классу x полосе дохода + ОКВЭД покупателей ----------
    все = collections.defaultdict(collections.Counter)  # класс -> полоса -> число
    окв, мсп_юл, n = {}, set(), 0
    with zipfile.ZipFile(rsmp) as z:
        for i, имя in enumerate([x for x in z.namelist() if x.lower().endswith('.xml')]):
            with z.open(имя) as fh:
                for el in документы(fh):
                    n += 1
                    инн, юл, осн = '', False, ''
                    for ch in el.iter():
                        т = ch.tag
                        if т.endswith('ОргВклМСП'):
                            инн, юл = ch.get('ИННЮЛ') or '', True
                        elif т.endswith('ИПВклМСП'):
                            инн = ch.get('ИННФЛ') or ''
                        elif т.endswith('СвОКВЭДОсн'):
                            осн = ch.get('КодОКВЭД') or ''
                    if not инн.isdigit():
                        continue
                    if юл:
                        мсп_юл.add(int(инн))
                    все[класс(осн)][полоса(доход.get(int(инн), 0))] += 1
                    if инн in нужные:
                        окв[инн] = (осн, 'МСП')
            if i % 100 == 0:
                отметка(этап='rsmp', файл=i, документов=n)
    # ---------- 5. не-МСП: ОКВЭД из своих баз ----------
    не_мсп = {инн for инн, v in доход.items() if v >= 3e7 and инн not in мсп_юл}
    окв_нм = {}

    def взять(инн, о, ист):
        инн = str(инн or '').strip()
        о = str(о or '').split()[0] if о else ''
        if not о or not инн.isdigit():
            return
        if инн in нужные and инн not in окв:
            окв[инн] = (о, ист)
        if int(инн) in не_мсп and int(инн) not in окв_нм:
            окв_нм[int(инн)] = о
    try:
        con = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True)
        for (т,) in con.execute("select name from sqlite_master where type='table'"):
            if {'inn', 'okved_main'} <= {r[1] for r in con.execute('pragma table_info("%s")' % т)}:
                for инн, о in con.execute('select inn, okved_main from "%s"' % т):
                    взять(инн, о, 'обзвон')
        con.close()
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_обзвон=repr(e)[:200])
    try:
        con = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
        for инн, о in con.execute('select inn, okved_main from requisites'):
            взять(инн, о, 'enrich')
        for инн, о in con.execute('select inn, okved from companies'):
            взять(инн, о, 'enrich')
        con.close()
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_enrich=repr(e)[:200])
    for путь in glob.glob(os.path.join(DIR, '*checko*.jsonl')) + glob.glob(os.path.join(DIR, '*dadata*.jsonl')):
        for s in io.open(путь, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
            except ValueError:
                continue
            if isinstance(y, dict):
                взять(y.get('inn') or y.get('инн'), y.get('оквэд') or y.get('okved'), 'checko/dadata')
    for инн, о in окв_нм.items():
        все[класс(о)][полоса(доход.get(инн, 0))] += 1
    отметка(этап='не-мсп', не_мсп_от_30млн=len(не_мсп), с_оквэд=len(окв_нм))
    # ---------- 6. портрет и оценка ----------
    итог = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'rsmp': os.path.basename(rsmp), 'документов_мсп': n,
            'не_мсп_от_30млн': len(не_мсп), 'не_мсп_от_30млн_с_оквэд': len(окв_нм),
            'сделок_без_инн_в_csv': dict(без_инн), 'направления': {}}
    for н, с in напр_инн.items():
        for вид in ('купили', 'все'):
            мн = с.get(вид, set())
            по_кл = collections.Counter()
            дох_кл = collections.defaultdict(list)
            по_пол = collections.Counter()
            ист = collections.Counter()
            for инн in мн:
                о, и = окв.get(инн, ('', 'нет'))
                ист[и] += 1
                v = доход.get(int(инн), 0) if инн.isdigit() else 0
                по_пол[полоса(v)] += 1
                if о:
                    по_кл[класс(о)] += 1
                    дох_кл[класс(о)].append(v)
            с_окв = sum(по_кл.values())
            строки, накоп = [], 0
            for кл, b in по_кл.most_common():
                накоп += b
                # p10 только по покупателям с известным доходом: ИП и «нет в revexp» дают 0 и обнуляли порог
                дд = sorted(x for x in дох_кл[кл] if x > 0)
                p10 = дд[len(дд) // 10] if дд else 0
                низ = max((НИЗ[п] for п in ПОЛОСЫ if НИЗ[п] <= p10), default=0)
                вселенная = sum(ч for п, ч in все[кл].items() if НИЗ[п] >= низ)
                строки.append({'класс': кл, 'покупателей': b, 'доля_%': round(100 * b / с_окв, 1),
                               'накоп_%': round(100 * накоп / с_окв, 1), 'доход_p10': p10, 'порог_полосы': низ,
                               'компаний_в_рф_от_порога': вселенная, 'всего_в_рф': sum(все[кл].values()),
                               'проникновение_%': round(100 * b / вселенная, 2) if вселенная else None,
                               'рф_по_полосам': {п: все[кл].get(п, 0) for п in ПОЛОСЫ}})
            оценка = {}
            for покр in (50, 80, 95):
                кк = [r for r in строки if r['накоп_%'] - r['доля_%'] < покр]
                оценка['классы_%d%%' % покр] = len(кк)
                оценка['компаний_%d%%' % покр] = sum(r['компаний_в_рф_от_порога'] for r in кк)
                # рынок при фиксированном нижнем доходе (вселенная тех же классов)
                for от in (10e6, 30e6, 100e6):
                    оценка['компаний_%d%%_от_%dмлн' % (покр, от / 1e6)] = sum(
                        ч for r in кк for п, ч in все[r['класс']].items() if НИЗ[п] >= от)
            итог['направления'].setdefault(н, {})[вид] = {
                'компаний': len(мн), 'с_оквэд': с_окв, 'источник_оквэд': dict(ист), 'по_доходу': dict(по_пол),
                'оценка_рынка': оценка, 'классы': строки[:60]}
    # вселенная класс x полоса — чтобы пересчитывать портрет без повторного разбора реестра (20 минут)
    пв = os.path.join(ПАПКА, 'ca-vselennaya.json')
    with open(пв, 'w', encoding='utf-8') as f:
        json.dump({кл: dict(сч) for кл, сч in все.items()}, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    п = os.path.join(ПАПКА, 'ca-pokupateli.json')
    with open(п, 'w', encoding='utf-8') as f:
        json.dump(итог, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    if os.path.isdir(D):
        import shutil
        shutil.copyfile(п, os.path.join(D, 'ca-pokupateli.json'))
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
