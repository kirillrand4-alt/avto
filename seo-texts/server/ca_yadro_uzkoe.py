# -*- coding: utf-8 -*-
r"""Узкое ядро похожих на покупателей Meyer и КЦ (11.11, владелец: «выдели более узкое ядро — выручка, чистая прибыль,
ОКВЭД + доп. ОКВЭД, — чтобы процент наших покупателей в узком ядре увеличился»).

Вселенная: юрлица с доходом от 15 млн (ФНС revexp, налоговый год 2025) в классах рабочего рынка направления (ядро +
второй круг из ca-rynok-15.json: проникновение класса ≥ 1 %). Признаки компании:
  * класс основного ОКВЭД (XX.XX);
  * полоса выручки: 15–30, 30–100, 100–300, 300 млн–1 млрд, от 1 млрд;
  * рентабельность = (доход − расход) / доход по revexp («прибыль до налога» в приближении ФНС): убыток, 0–3 %, 3–10 %,
    от 10 %;
  * численность (sshr): до 15, 15–50, 50–250, от 250, нет данных;
  * дополнительные ОКВЭД (реестр МСП; для не-МСП — свои базы и добор): «подъёмная сила» (lift) каждого доп. класса =
    доля среди покупателей / доля во вселенной; сильные (lift ≥ 2, не меньше 8 покупателей) дают флаг «есть сильный доп.».
Ячейка = класс × выручка × рентабельность × флаг доп. ОКВЭД. Проникновение ячейки = покупатели / компании. Ячейки
сортируются по проникновению (не меньше 20 компаний), кривая: сколько компаний нужно взять, чтобы накрыть 30/50/70/85 %
покупателей вселенной, и какое у этого набора проникновение. «Узкое ядро» = набор, накрывающий 50 % покупателей.
Плюс разрезы по каждому признаку отдельно (где проникновение растёт).
Выход: ca\ca-yadro-uzkoe.json и CA-YADRO-UZKOE.md (+ дроп). Только чтение. Запуск: сам в фон, низкий приоритет.
"""
import collections, csv, glob, io, json, os, re, sqlite3, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
FNS = r'C:\sender\_ops\ak\fns'
ДРОП = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    лог = os.path.join(ПАПКА, 'ca_yadro_uzkoe_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(15)
    print('===ИТОГ=== запущен', open(лог, encoding='utf-8', errors='replace').read()[-300:])
    sys.exit(0)
ЗАМОК = os.path.join(ПАПКА, 'ca_yadro_uzkoe.lock')
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
    with open(os.path.join(ПАПКА, 'ca-yadro-uzkoe-progress.json'), 'w', encoding='utf-8') as f:
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
    # ---------- покупатели ----------
    купили = collections.defaultdict(set)
    vse = json.load(io.open(os.path.join(ДРОП, 'sdelki-vse-1410.json'), encoding='utf-8'))
    for инн, сс in vse.items():
        for d in сс or []:
            if d[1] == 'Успешна' and d[0] in ('kc', 'meyer'):
                купили['КЦ' if d[0] == 'kc' else 'Meyer'].add(инн)
    п = os.path.join(ДРОП, 'kc-sc-sdelki-0910.csv')
    if os.path.exists(п):
        fh = io.open(п, encoding='utf-8-sig')
        кол = next(csv.reader([fh.readline()], delimiter=';'))
        for r in csv.DictReader(fh, fieldnames=кол, delimiter=';'):
            в = (r.get('ВОРОНКА') or '').strip()
            if в.startswith('СЦ') or 'MEYER' in в.upper():
                continue
            инн = re.sub(r'\D', '', r.get('INN') or '')
            if len(инн) == 10 and r.get('СТАТУС') == 'Успешна':
                купили['КЦ'].add(инн)
    нужные = set().union(*купили.values())
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
    # ---------- по направлениям ----------
    рынок = json.load(io.open(os.path.join(ПАПКА, 'ca-rynok-15.json'), encoding='utf-8'))['направления']
    итог = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'порог_выручки': ПОРОГ, 'направления': {}}
    md = ['# Узкое ядро похожих на покупателей (Meyer, КЦ)', '',
          'Вселенная: юрлица с выручкой от 15 млн в классах рабочего рынка (проникновение класса от 1 %%). '
          'Покупатели: выигранные сделки Битрикса. Рентабельность = (доход − расход) / доход по данным ФНС. %s.' % time.strftime('%d.%m.%Y'), '']
    for н in ('Meyer', 'КЦ'):
        раб = {r['класс'] for r in рынок[н]['классы'] if r['группа'] != '<1%'}
        U = {инн for инн, (д, р) in дох.items() if д >= ПОРОГ and len(инн) == 10 and инн in окв and класс(окв[инн][0]) in раб}
        B = U & купили[н]
        # подъёмная сила доп. классов
        uc, bc = collections.Counter(), collections.Counter()
        for инн in U:
            дк = {класс(x) for x in окв[инн][1]} - {класс(окв[инн][0])}
            uc.update(дк)
            if инн in B:
                bc.update(дк)
        лифт = []
        for c, nb in bc.items():
            if nb >= 8:
                l = (nb / len(B)) / (uc[c] / len(U))
                лифт.append((c, nb, uc[c], round(l, 2), round(100 * nb / uc[c], 2)))
        лифт.sort(key=lambda x: -x[3])
        сильные = {c for c, nb, nu, l, p in лифт if l >= 2}
        # ячейки
        яч = collections.defaultdict(lambda: [0, 0])
        признаки = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
        for инн in U:
            д, р = дох[инн]
            кл = класс(окв[инн][0])
            флаг = 'есть сильный доп.' if ({класс(x) for x in окв[инн][1]} & сильные) else 'нет'
            ключ = (кл, п_выр(д), п_рент(д, р), флаг)
            b = инн in B
            яч[ключ][0] += 1
            яч[ключ][1] += b
            for имя_п, зн in (('выручка', п_выр(д)), ('рентабельность', п_рент(д, р)), ('штат', п_штат(штат.get(инн))),
                              ('доп. ОКВЭД', флаг)):
                признаки[имя_п][зн][0] += 1
                признаки[имя_п][зн][1] += b
        годные = sorted(((k, n, b) for k, (n, b) in яч.items() if n >= 20), key=lambda x: -x[2] / x[1])
        кривая, взято_n, взято_b, ядро = [], 0, 0, []
        цели = [0.3, 0.5, 0.7, 0.85]
        for k, n, b in годные:
            взято_n += n
            взято_b += b
            if взято_b <= 0.5 * len(B) or not ядро:
                ядро.append({'класс': k[0], 'выручка': k[1], 'рентабельность': k[2], 'доп': k[3], 'компаний': n, 'покупателей': b,
                             'проникновение_%': round(100 * b / n, 1)})
            while цели and взято_b >= цели[0] * len(B):
                кривая.append({'покрытие_покупателей_%': int(цели[0] * 100), 'компаний': взято_n, 'покупателей': взято_b,
                               'проникновение_%': round(100 * взято_b / взято_n, 2)})
                цели.pop(0)
        рез = {'вселенная': len(U), 'покупателей_во_вселенной': len(B), 'проникновение_вселенной_%': round(100 * len(B) / max(1, len(U)), 2),
               'кривая': кривая, 'узкое_ядро_ячейки': ядро[:60],
               'разрезы': {п_: {зн: {'компаний': v[0], 'покупателей': v[1], 'проникновение_%': round(100 * v[1] / max(1, v[0]), 2)}
                                for зн, v in д_.items()} for п_, д_ in признаки.items()},
               'доп_оквэд_лифт': [{'класс': c, 'покупателей': nb, 'компаний': nu, 'лифт': l, 'проникновение_%': p} for c, nb, nu, l, p in лифт[:30]]}
        итог['направления'][н] = рез
        with open(os.path.join(ПАПКА, 'ca-yadro-uzkoe.json'), 'w', encoding='utf-8') as f:
            json.dump(итог, f, ensure_ascii=False, indent=1)
        md += ['## %s' % н, '', 'Вселенная (рабочий рынок, от 15 млн): **%d** компаний, покупателей в ней %d, проникновение %.2f %%.' % (
            len(U), len(B), рез['проникновение_вселенной_%']), '', '**Кривая «сколько взять → какой процент наших»:**', '',
               '| накрыть покупателей | компаний | покупателей | проникновение |', '|---|---|---|---|']
        md += ['| %d %% | %d | %d | %.2f %% |' % (x['покрытие_покупателей_%'], x['компаний'], x['покупателей'], x['проникновение_%']) for x in кривая]
        md += ['', '**Разрезы по признакам (проникновение):**', '']
        for п_, д_ in рез['разрезы'].items():
            md.append('- %s: ' % п_ + '; '.join('%s — %s %% (%d комп.)' % (зн, v['проникновение_%'], v['компаний'])
                                                for зн, v in sorted(д_.items(), key=lambda x: -x[1]['проникновение_%'])))
        md += ['', '**Дополнительные ОКВЭД, которые чаще у покупателей (лифт):**', '']
        md += ['- %s: лифт %.1f, покупателей %d из %d компаний (%.1f %%)' % (x['класс'], x['лифт'], x['покупателей'], x['компаний'],
                                                                             x['проникновение_%']) for x in рез['доп_оквэд_лифт'][:15]]
        md += ['', '**Узкое ядро — первые ячейки (класс | выручка | рентабельность | доп. ОКВЭД):**', '']
        md += ['- %s | %s | %s | %s: %d компаний, покупателей %d (%.1f %%)' % (x['класс'], x['выручка'], x['рентабельность'], x['доп'],
                                                                              x['компаний'], x['покупателей'], x['проникновение_%']) for x in ядро[:25]]
        md.append('')
    п = os.path.join(ПАПКА, 'ca-yadro-uzkoe.json')
    with open(п, 'w', encoding='utf-8') as f:
        json.dump(итог, f, ensure_ascii=False, indent=1)
    пм = os.path.join(ПАПКА, 'CA-YADRO-UZKOE.md')
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
