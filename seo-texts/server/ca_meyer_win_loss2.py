# -*- coding: utf-8 -*-
r"""Meyer, выигранные и проваленные: компании без выручки и динамика по годам (11.11, владелец: «а есть ООО без выручки
по этим ОКВЭД? какие там коэффициенты, и по годам интересно — сейчас лучше идут пищевики»).

ИНН-уровень (как в ca_meyer_win_loss.py): купили / провал / в работе. Выручка — ФНС revexp (любая), ОКВЭД — реестр МСП
(ЮЛ и ИП), для остальных — свои базы. Группы по выручке: ИП; ЮЛ без данных ФНС о доходе; до 15 млн; 15–100; 100 млн–1 млрд;
от 1 млрд. Сегменты по основному ОКВЭД: сырьё (01.*, 03.*, 52.10), переработка (10.*, 11.*), опт (46.*), прочее.
Годы — на уровне СДЕЛОК (год создания): выиграно / провалено / доля побед, по сегментам.
Выход: ca\CA-MEYER-WIN-LOSS-2.md (+ дроп). Только чтение. Запуск: сам в фон.
"""
import collections, glob, io, json, os, re, sqlite3, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
FNS = r'C:\sender\_ops\ak\fns'
ДРОП = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    with open(os.path.join(ПАПКА, 'ca_meyer_win_loss2_%s.log' % time.strftime('%d%m-%H%M')), 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(8)
    print('===ИТОГ=== запущен')
    sys.exit(0)


def отметка(**k):
    k['обновлено'] = time.strftime('%H:%M:%S')
    with open(os.path.join(ПАПКА, 'ca-meyer-win-loss2-progress.json'), 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)


def документы(fh):
    корень = None
    for ev, el in ET.iterparse(fh, events=('start', 'end')):
        if корень is None:
            корень = el
        if ev == 'end' and el.tag.endswith('Документ'):
            yield el
            корень.clear()


def сегмент(о):
    о = str(о or '')
    if о.startswith(('01.', '03.')) or о.startswith('52.10'):
        return 'сырьё (хозяйства, элеваторы)'
    if о.startswith(('10.', '11.')):
        return 'переработка (пищевые производства)'
    if о.startswith('46.'):
        return 'опт'
    return 'прочее' if о else 'ОКВЭД неизвестен'


def main():
    сделки = {инн: [d for d in сс or [] if d[0] == 'meyer'] for инн, сс in
              json.load(io.open(os.path.join(ДРОП, 'sdelki-vse-1410.json'), encoding='utf-8')).items()}
    сделки = {к: v for к, v in сделки.items() if v}
    гр = {}
    for инн, м in сделки.items():
        ст = {d[1] for d in м}
        гр[инн] = 'купили' if 'Успешна' in ст else 'провал' if 'Провалена' in ст else 'в работе'
    дох = {}
    with zipfile.ZipFile(os.path.join(FNS, 'revexp.zip')) as z:
        for f_ in z.namelist():
            with z.open(f_) as fh:
                for el in документы(fh):
                    инн, д = '', 0.0
                    for ch in el:
                        if 'СведНП' in ch.tag:
                            инн = ch.get('ИННЮЛ') or ''
                        elif 'ДохРасх' in ch.tag:
                            try:
                                д = float(ch.get('СумДоход') or 0)
                            except ValueError:
                                pass
                    if инн in гр:
                        дох[инн] = д
    отметка(этап='revexp', найдено=len(дох))
    окв = {}
    фф = [f for f in glob.glob(os.path.join(FNS, 'data-*-structure-*.zip')) if os.path.exists(f + '.ok')]
    with zipfile.ZipFile(max(фф, key=os.path.getmtime)) as z:
        for i, f_ in enumerate([x for x in z.namelist() if x.lower().endswith('.xml')]):
            with z.open(f_) as fh:
                for el in документы(fh):
                    инн, осн = '', ''
                    for ch in el.iter():
                        т = ch.tag
                        if т.endswith('ОргВклМСП'):
                            инн = ch.get('ИННЮЛ') or ''
                        elif т.endswith('ИПВклМСП'):
                            инн = ch.get('ИННФЛ') or ''
                        elif т.endswith('СвОКВЭДОсн'):
                            осн = ch.get('КодОКВЭД') or ''
                    if инн in гр and осн:
                        окв[инн] = осн
            if i % 1000 == 0:
                отметка(этап='rsmp', файл=i, с_оквэд=len(окв))
    try:
        con = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=120)
        for инн, о in con.execute('select inn, okved_main from obzvon'):
            инн = str(инн or '')
            if инн in гр and инн not in окв and о:
                окв[инн] = str(о).split()[0]
        con.close()
        con = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=120)
        for инн, о in con.execute('select inn, okved_main from requisites'):
            инн = str(инн or '')
            if инн in гр and инн not in окв and о:
                окв[инн] = str(о).split()[0]
        con.close()
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_баз=repr(e)[:150])
    for путь in glob.glob(os.path.join(DIR, '*okved*.jsonl')) + [os.path.join(ПАПКА, 'ca-okved-dobor.jsonl')]:
        if os.path.exists(путь):
            for s in io.open(путь, encoding='utf-8', errors='replace'):
                try:
                    y = json.loads(s)
                except ValueError:
                    continue
                инн = str(y.get('inn') or '')
                if инн in гр and инн not in окв and y.get('оквэд'):
                    окв[инн] = str(y['оквэд']).split()[0]

    def п_выр(инн):
        if len(инн) == 12:
            return 'ИП'
        if инн not in дох:
            return 'ЮЛ без данных ФНС о доходе'
        д = дох[инн]
        return 'до 15 млн' if д < 15e6 else '15–100 млн' if д < 1e8 else '100 млн–1 млрд' if д < 1e9 else 'от 1 млрд'
    ПОРЯДОК = ['ИП', 'ЮЛ без данных ФНС о доходе', 'до 15 млн', '15–100 млн', '100 млн–1 млрд', 'от 1 млрд']
    т1 = collections.defaultdict(collections.Counter)
    т1с = collections.defaultdict(collections.Counter)
    for инн, г in гр.items():
        в = п_выр(инн)
        т1[в][г] += 1
        т1с[(сегмент(окв.get(инн)), в)][г] += 1
    # годы — уровень сделок
    т2 = collections.defaultdict(collections.Counter)
    for инн, м in сделки.items():
        сег = сегмент(окв.get(инн))
        for d in м:
            год = (d[2] or '')[:4]
            if not год.isdigit():
                continue
            т2[(год, сег)][d[1]] += 1
            т2[(год, 'все')][d[1]] += 1

    def доля(c):
        k, f = c['купили'] or c['Успешна'], c['провал'] or c['Провалена']
        return '%.1f %%' % (100 * k / (k + f)) if k + f else '—'
    md = ['# Meyer: компании без выручки и динамика по годам', '',
          'Битрикс (выгрузка 14.10), направление Meyer. Доля побед = выиграно / (выиграно + провалено). %s.' % time.strftime('%d.%m.%Y'), '',
          '## 1. По размеру, включая ИП и ЮЛ без данных ФНС (уровень компаний)', '',
          '| группа | купили | провал | в работе | доля побед |', '|---|---|---|---|---|']
    for в in ПОРЯДОК:
        c = т1[в]
        md.append('| %s | %d | %d | %d | %s |' % (в, c['купили'], c['провал'], c['в работе'], доля(c)))
    md += ['', '### То же по сегментам', '', '| сегмент | группа | купили | провал | доля побед |', '|---|---|---|---|---|']
    for сег in ('переработка (пищевые производства)', 'сырьё (хозяйства, элеваторы)', 'опт', 'прочее', 'ОКВЭД неизвестен'):
        for в in ПОРЯДОК:
            c = т1с[(сег, в)]
            if c['купили'] + c['провал'] >= 5:
                md.append('| %s | %s | %d | %d | %s |' % (сег, в, c['купили'], c['провал'], доля(c)))
    md += ['', '## 2. По годам создания сделки (уровень сделок)', '',
           '| год | сегмент | выиграно | провалено | в работе | доля побед |', '|---|---|---|---|---|---|']
    годы = sorted({г for г, _ in т2})
    for год in годы:
        for сег in ('все', 'переработка (пищевые производства)', 'сырьё (хозяйства, элеваторы)', 'опт'):
            c = т2[(год, сег)]
            if sum(c.values()) >= 5:
                md.append('| %s | %s | %d | %d | %d | %s |' % (год, сег, c['Успешна'], c['Провалена'], c['В работе'], доля(c)))
    п = os.path.join(ПАПКА, 'CA-MEYER-WIN-LOSS-2.md')
    io.open(п, 'w', encoding='utf-8').write('\n'.join(md))
    import shutil
    shutil.copyfile(п, os.path.join(ДРОП, 'CA-MEYER-WIN-LOSS-2.md'))
    отметка(этап='готово', компаний=len(гр), с_оквэд=len(окв), с_доходом=len(дох))


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:  # noqa: BLE001
        отметка(этап='ошибка', ошибка=repr(e)[:400])
        raise
