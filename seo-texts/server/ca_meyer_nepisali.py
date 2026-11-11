# -*- coding: utf-8 -*-
r"""Ядро Meyer против отправленных писем (11.11, владелец: «посмотри уже посчитанное ядро с этим файлом
[MEYER-PISALI.csv], много ли тех, кому ещё не писали?»).

Уровни (юрлица с выручкой от 30 млн — ca\ca-inn-okved-30.jsonl; классы — ca-rynok-15.json):
  * рабочий рынок: классы с проникновением от 1 %;
  * ядро классов: проникновение от 3 %;
  * узкое ядро: рабочий рынок И (выручка от 300 млн ИЛИ штат от 50), без 64.91 (лизинг: покупатель по документам —
    лизингодатель).
Для каждого: писали ли Meyer (ИНН в MEYER-PISALI.csv), была ли сделка Meyer (выиграна / провалена / в работе), не тронуто.
Выход: ca\ca-meyer-nepisali.json, список нетронутых узкого ядра — MEYER-YADRO-NE-PISALI.csv (+ дроп). Только чтение.
"""
import collections, csv, io, json, os, re, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
FNS = r'C:\sender\_ops\ak\fns'
ДРОП = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    лог = os.path.join(ПАПКА, 'ca_meyer_nepisali_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(10)
    print('===ИТОГ=== запущен')
    sys.exit(0)


def отметка(**k):
    k['обновлено'] = time.strftime('%H:%M:%S')
    with open(os.path.join(ПАПКА, 'ca-meyer-nepisali-progress.json'), 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)


def документы(fh):
    корень = None
    for ev, el in ET.iterparse(fh, events=('start', 'end')):
        if корень is None:
            корень = el
        if ev == 'end' and el.tag.endswith('Документ'):
            yield el
            корень.clear()


def main():
    окв = {}
    for s in io.open(os.path.join(ПАПКА, 'ca-inn-okved-30.jsonl'), encoding='utf-8'):
        y = json.loads(s)
        окв[y['inn']] = (y['оквэд'], float(y.get('доход') or 0))
    имя = {}
    with zipfile.ZipFile(os.path.join(FNS, 'revexp.zip')) as z:
        for f_ in z.namelist():
            with z.open(f_) as fh:
                for el in документы(fh):
                    for ch in el:
                        if 'СведНП' in ch.tag and (ch.get('ИННЮЛ') or '') in окв:
                            имя[ch.get('ИННЮЛ')] = ch.get('НаимОрг') or ''
    отметка(этап='revexp')
    штат = {}
    with zipfile.ZipFile(os.path.join(FNS, 'sshr.zip')) as z:
        for f_ in z.namelist():
            with z.open(f_) as fh:
                for el in документы(fh):
                    инн, ч = '', None
                    for ch in el.iter():
                        if ch.get('ИННЮЛ'):
                            инн = ch.get('ИННЮЛ')
                        for k, v in ch.attrib.items():
                            if 'Кол' in k and v.isdigit():
                                ч = int(v)
                    if инн in окв and ч is not None:
                        штат[инн] = ч
    отметка(этап='sshr')
    рынок = json.load(io.open(os.path.join(ПАПКА, 'ca-rynok-15.json'), encoding='utf-8'))['направления']['Meyer']['классы']
    раб = {r['класс'] for r in рынок if r['группа'] != '<1%'}
    ядро = {r['класс'] for r in рынок if r['группа'].startswith('ядро')}
    писали = {}
    п = os.path.join(ДРОП, 'MEYER-PISALI.csv')
    with io.open(п, encoding='utf-8-sig', errors='replace') as f:
        r_ = csv.reader(f, delimiter=';')
        шапка = next(r_)
        и_инн = next((i for i, h in enumerate(шапка) if 'ИНН' in h.upper()), 0)
        и_пис = next((i for i, h in enumerate(шапка) if 'писем' in h.lower()), None)
        for row in r_:
            if len(row) > и_инн:
                инн = re.sub(r'\D', '', row[и_инн])
                if инн:
                    писали[инн] = row[и_пис] if и_пис is not None and len(row) > и_пис else '1'
    сд = collections.defaultdict(set)
    for инн, сс in json.load(io.open(os.path.join(ДРОП, 'sdelki-vse-1410.json'), encoding='utf-8')).items():
        for d in сс or []:
            if d[0] == 'meyer':
                сд[инн].add(d[1])
    def кл(о):
        return '.'.join(str(о).split('.')[:2])
    уровни = {
        'рабочий рынок (проникновение класса от 1 %)': {i for i, (о, д) in окв.items() if кл(о) in раб},
        'ядро классов (проникновение от 3 %)': {i for i, (о, д) in окв.items() if кл(о) in ядро},
        'узкое ядро (рабочий рынок и выручка от 300 млн или штат от 50, без лизинга)':
            {i for i, (о, д) in окв.items() if кл(о) in раб and кл(о) != '64.91' and (д >= 3e8 or штат.get(i, 0) >= 50)},
    }
    итог = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'в_файле_писали_ИНН': len(писали), 'уровни': {}}
    for н, мн in уровни.items():
        с = collections.Counter()
        for i in мн:
            с['всего'] += 1
            п_ = i in писали
            с['писали'] += п_
            ст = сд.get(i, set())
            if 'Успешна' in ст:
                с['купили'] += 1
            elif 'Провалена' in ст:
                с['провал'] += 1
            elif ст:
                с['в работе'] += 1
            if not п_ and not ст:
                с['не писали и не было сделок'] += 1
            if not п_ and ст:
                с['не писали, но была сделка'] += 1
        итог['уровни'][н] = dict(с)
    узк = уровни['узкое ядро (рабочий рынок и выручка от 300 млн или штат от 50, без лизинга)']
    строки = sorted(({'ИНН': i, 'Компания': имя.get(i, ''), 'ОКВЭД': окв[i][0], 'Класс в ядре': 'да' if кл(окв[i][0]) in ядро else 'второй круг',
                      'Выручка, млн ₽': round(окв[i][1] / 1e6), 'Штат': штат.get(i, '')}
                     for i in узк if i not in писали and not сд.get(i)), key=lambda r: -r['Выручка, млн ₽'])
    вых = os.path.join(ПАПКА, 'MEYER-YADRO-NE-PISALI.csv')
    with io.open(вых, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['ИНН', 'Компания', 'ОКВЭД', 'Класс в ядре', 'Выручка, млн ₽', 'Штат'], delimiter=';')
        w.writeheader()
        w.writerows(строки)
    итог['не_писали_узкое_ядро_по_классам'] = dict(collections.Counter(r['ОКВЭД'][:5] for r in строки).most_common(15))
    with open(os.path.join(ПАПКА, 'ca-meyer-nepisali.json'), 'w', encoding='utf-8') as f:
        json.dump(итог, f, ensure_ascii=False, indent=1)
    import shutil
    for ф in ('ca-meyer-nepisali.json', 'MEYER-YADRO-NE-PISALI.csv'):
        shutil.copyfile(os.path.join(ПАПКА, ф), os.path.join(ДРОП, ф))
    отметка(этап='готово', **{k[:20]: v for k, v in итог['уровни'].items()})


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:  # noqa: BLE001
        отметка(этап='ошибка', ошибка=repr(e)[:400])
        raise
