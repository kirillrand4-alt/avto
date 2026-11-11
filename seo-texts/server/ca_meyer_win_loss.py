# -*- coding: utf-8 -*-
r"""Meyer: выигранные и проваленные сделки — есть ли различие в ЦА (11.11, владелец: «сделай расчёт, как делал, но если
учесть в том числе проваленные сделки — есть ли различие у ЦА Meyer между успешными и проваленными, посмотрим»).

Группы по ИНН (выгрузка Битрикса sdelki-vse-1410.json, направление meyer): «купили» — есть «Успешна»; «провал» — есть
«Провалена» и нет «Успешна»; «в работе» — только активные. Только юрлица (10 цифр) с данными ФНС.
По каждому признаку (класс ОКВЭД, выручка, рентабельность, штат, сильный доп. ОКВЭД): купили, провал, в работе, доля
побед = купили / (купили + провал), интерес = (купили + провал + в работе) / компаний во вселенной сегмента (выручка
от 15 млн), проникновение покупок = купили / компаний. Отдельно — классы, где мы чаще всего проигрываем.
Выход: ca\ca-meyer-win-loss.json и CA-MEYER-WIN-LOSS.md (+ дроп). Только чтение. Запуск: сам в фон.
"""
import collections, csv, glob, io, json, os, re, sqlite3, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
FNS = r'C:\sender\_ops\ak\fns'
ДРОП = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    лог = os.path.join(ПАПКА, 'ca_meyer_win_loss_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(15)
    print('===ИТОГ=== запущен', open(лог, encoding='utf-8', errors='replace').read()[-300:])
    sys.exit(0)
ЗАМОК = os.path.join(ПАПКА, 'ca_meyer_win_loss.lock')
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

ПОРОГ = 15e6


def отметка(**k):
    k['обновлено'] = time.strftime('%H:%M:%S')
    with open(os.path.join(ПАПКА, 'ca-meyer-win-loss-progress.json'), 'w', encoding='utf-8') as f:
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


def класс(к):
    return '.'.join(str(к or '').split('.')[:2])


def п_выр(v):
    return '15–30 млн' if v < 3e7 else '30–100 млн' if v < 1e8 else '100–300 млн' if v < 3e8 else '300 млн–1 млрд' if v < 1e9 else 'от 1 млрд'


def п_рент(д, р):
    if not д:
        return 'нет данных'
    м = (д - р) / д
    return 'убыток' if м < 0 else '0–3 %' if м < 0.03 else '3–10 %' if м < 0.10 else 'от 10 %'


def п_штат(ч):
    if ч is None:
        return 'нет данных'
    return 'до 15' if ч < 15 else '15–50' if ч < 50 else '50–250' if ч < 250 else 'от 250'


def main():
    # ---------- группы Meyer ----------
    гр = {}
    vse = json.load(io.open(os.path.join(ДРОП, 'sdelki-vse-1410.json'), encoding='utf-8'))
    for инн, сс in vse.items():
        м = [d for d in сс or [] if d[0] == 'meyer']
        if not м or len(инн) != 10:
            continue
        ст = {d[1] for d in м}
        гр[инн] = 'купили' if 'Успешна' in ст else 'провал' if 'Провалена' in ст else 'в работе'
    нужные = set(гр)
    # ---------- доход/расход ----------
    дох = {}
    with zipfile.ZipFile(os.path.join(FNS, 'revexp.zip')) as z:
        for имя in z.namelist():
            with z.open(имя) as fh:
                for el in документы(fh):
                    инн, д, р = '', 0.0, 0.0
                    for ch in el:
                        if 'СведНП' in ch.tag:
                            инн = ch.get('ИННЮЛ') or ''
                        elif 'ДохРасх' in ch.tag:
                            try:
                                д, р = float(ch.get('СумДоход') or 0), float(ch.get('СумРасход') or 0)
                            except ValueError:
                                pass
                    if инн.isdigit() and (д >= ПОРОГ or инн in нужные):
                        дох[инн] = (д, р)
    отметка(этап='revexp', компаний=len(дох))
    # ---------- численность ----------
    штат = {}
    try:
        with zipfile.ZipFile(os.path.join(FNS, 'sshr.zip')) as z:
            for имя in z.namelist():
                with z.open(имя) as fh:
                    for el in документы(fh):
                        инн, ч = '', None
                        for ch in el.iter():
                            if ch.get('ИННЮЛ'):
                                инн = ch.get('ИННЮЛ')
                            for k, v in ch.attrib.items():
                                if 'Кол' in k and v.isdigit():
                                    ч = int(v)
                        if инн in дох and ч is not None:
                            штат[инн] = ч
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_sshr=repr(e)[:150])
    отметка(этап='sshr', со_штатом=len(штат))
    # ---------- ОКВЭД: МСП (осн + доп) ----------
    фф = [f for f in glob.glob(os.path.join(FNS, 'data-*-structure-*.zip')) if os.path.exists(f + '.ok')]
    окв = {}
    with zipfile.ZipFile(max(фф, key=os.path.getmtime)) as z:
        for i, имя in enumerate([x for x in z.namelist() if x.lower().endswith('.xml')]):
            with z.open(имя) as fh:
                for el in документы(fh):
                    инн, осн, доп = '', '', []
                    for ch in el.iter():
                        т = ch.tag
                        if т.endswith('ОргВклМСП'):
                            инн = ch.get('ИННЮЛ') or ''
                        elif т.endswith('СвОКВЭДОсн'):
                            осн = ch.get('КодОКВЭД') or ''
                        elif т.endswith('СвОКВЭДДоп'):
                            доп.append(ch.get('КодОКВЭД') or '')
                    if инн in дох and осн:
                        окв[инн] = (осн, доп)
            if i % 500 == 0:
                отметка(этап='rsmp', файл=i, с_оквэд=len(окв))
    # ---------- не-МСП: свои базы и добор ----------
    def коды(s):
        if isinstance(s, list):
            return [str(x).split()[0] for x in s if x]
        return re.findall(r'\d{2}(?:\.\d{1,2}){0,2}', str(s or ''))

    def взять(инн, о, все):
        инн = str(инн or '').strip()
        к = коды(о)
        if инн in дох and инн not in окв and к:
            окв[инн] = (к[0], [x for x in коды(все) if x != к[0]])
    try:
        con = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=120)
        for инн, о, в in con.execute('select inn, okved_main, okved_all_codes from obzvon'):
            взять(инн, о, в)
        con.close()
        con = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=120)
        for инн, о, в in con.execute('select inn, okved_main, okved_all from requisites'):
            взять(инн, о, в)
        con.close()
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_базы=repr(e)[:150])
    for путь in sorted(set(glob.glob(os.path.join(DIR, '*okved*.jsonl')) + glob.glob(os.path.join(DIR, '*checko*.jsonl')) +
                           glob.glob(os.path.join(DIR, '*dadata*.jsonl')) + [os.path.join(ПАПКА, 'ca-okved-dobor.jsonl')])):
        if os.path.exists(путь):
            for s in io.open(путь, encoding='utf-8', errors='replace'):
                try:
                    y = json.loads(s)
                except ValueError:
                    continue
                if isinstance(y, dict):
                    взять(y.get('inn') or y.get('инн'), y.get('оквэд') or y.get('okved'), y.get('оквэд_все') or y.get('okveds') or '')
    отметка(этап='оквэд', с_оквэд=len(окв))
    # ---------- анализ ----------
    рынок = json.load(io.open(os.path.join(ПАПКА, 'ca-rynok-15.json'), encoding='utf-8'))['направления']['Meyer']
    раб = {r['класс'] for r in рынок['классы'] if r['группа'] != '<1%'}
    U = {инн for инн, (д, р) in дох.items() if д >= ПОРОГ and len(инн) == 10 and инн in окв}
    с_данными = {инн for инн in гр if инн in дох and инн in окв}
    # сильные доп. ОКВЭД — по покупателям относительно вселенной рабочего рынка (как в узком ядре)
    UW = {инн for инн in U if класс(окв[инн][0]) in раб}
    B = {инн for инн in UW if гр.get(инн) == 'купили'}
    uc, bc = collections.Counter(), collections.Counter()
    for инн in UW:
        дк = {класс(x) for x in окв[инн][1]} - {класс(окв[инн][0])}
        uc.update(дк)
        if инн in B:
            bc.update(дк)
    сильные = {c for c, nb in bc.items() if nb >= 8 and (nb / max(1, len(B))) / (uc[c] / len(UW)) >= 2}
    def признаки(инн):
        д, р = дох[инн]
        return {'класс ОКВЭД': класс(окв[инн][0]), 'выручка': п_выр(д) if д >= ПОРОГ else 'до 15 млн',
                'рентабельность': п_рент(д, р), 'штат': п_штат(штат.get(инн)),
                'сильный доп. ОКВЭД': 'есть' if ({класс(x) for x in окв[инн][1]} & сильные) else 'нет',
                'рабочий рынок': 'да' if класс(окв[инн][0]) in раб else 'нет'}
    табл = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for инн in с_данными:
        for п_, зн in признаки(инн).items():
            табл[п_][зн][гр[инн]] += 1
    for инн in U:
        for п_, зн in признаки(инн).items():
            табл[п_][зн]['компаний'] += 1
    итог = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'групп': dict(collections.Counter(гр.values())),
            'с_данными_ФНС': dict(collections.Counter(гр[i] for i in с_данными)), 'признаки': {}}
    md = ['# Meyer: выигранные и проваленные сделки', '',
          'Группы по ИНН (Битрикс, выгрузка 14.10): купили — есть выигранная сделка; провал — есть проваленная и нет выигранной; '
          'в работе — только активные. Доля побед = купили / (купили + провал). Интерес = все со сделкой / компаний сегмента '
          '(выручка от 15 млн). %s.' % time.strftime('%d.%m.%Y'), '',
          'Всего ИНН со сделками Meyer: %s; с данными ФНС и ОКВЭД: %s.' % (dict(collections.Counter(гр.values())),
                                                                   dict(collections.Counter(гр[i] for i in с_данными))), '']
    for п_ in ('рабочий рынок', 'выручка', 'рентабельность', 'штат', 'сильный доп. ОКВЭД', 'класс ОКВЭД'):
        строки = []
        for зн, c in табл[п_].items():
            k, f, w, n = c['купили'], c['провал'], c['в работе'], c['компаний']
            if п_ == 'класс ОКВЭД' and k + f < 15:
                continue
            строки.append({'значение': зн, 'купили': k, 'провал': f, 'в работе': w, 'компаний': n,
                           'доля_побед_%': round(100 * k / (k + f), 1) if k + f else None,
                           'интерес_%': round(100 * (k + f + w) / n, 2) if n else None,
                           'проникновение_%': round(100 * k / n, 2) if n else None})
        строки.sort(key=lambda r: -(r['купили'] + r['провал']))
        итог['признаки'][п_] = строки
        md += ['## %s' % п_, '', '| значение | купили | провал | в работе | доля побед | интерес | проникновение покупок | компаний (от 15 млн) |',
               '|---|---|---|---|---|---|---|---|']
        for r in строки[:25]:
            md.append('| %s | %d | %d | %d | %s | %s | %s | %d |' % (r['значение'], r['купили'], r['провал'], r['в работе'],
                      '%.1f %%' % r['доля_побед_%'] if r['доля_побед_%'] is not None else '—',
                      '%.2f %%' % r['интерес_%'] if r['интерес_%'] is not None else '—',
                      '%.2f %%' % r['проникновение_%'] if r['проникновение_%'] is not None else '—', r['компаний']))
        md.append('')
        with open(os.path.join(ПАПКА, 'ca-meyer-win-loss.json'), 'w', encoding='utf-8') as f:
            json.dump(итог, f, ensure_ascii=False, indent=1)
    п = os.path.join(ПАПКА, 'ca-meyer-win-loss.json')
    пм = os.path.join(ПАПКА, 'CA-MEYER-WIN-LOSS.md')
    io.open(пм, 'w', encoding='utf-8').write('\n'.join(md))
    import shutil
    for ф in (п, пм):
        shutil.copyfile(ф, os.path.join(ДРОП, os.path.basename(ф)))
    отметка(этап='готово')


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:  # noqa: BLE001
        отметка(этап='ошибка', ошибка=repr(e)[:400])
        raise
    finally:
        try:
            os.remove(ЗАМОК)
        except OSError:
            pass
