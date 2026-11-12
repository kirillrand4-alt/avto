# -*- coding: utf-8 -*-
r"""Выжимка ФНС для анализа покупателей крупных компрессоров КЦ (12.11, владелец: «ядро/узкое ядро покупателей
крупных компрессоров, по категориям»). Сделки владельца на сервер не кладутся — склейка в сессии; здесь только реестры.

Все ЮЛ из revexp (любая выручка): ИНН, доход, расход, штат (sshr), основной и дополнительные ОКВЭД (реестр МСП; для не-МСП —
свои базы: obzvon okved_main/okved_all_codes, enrich requisites, ca-inn-okved-30).
Выход: ca\kc-an-fns.jsonl.gz (+ дроп): строки [инн, доход, расход, штат, осн, "доп1,доп2,…", источник_оквэд].
Только чтение. Запуск: сам в фон, прогресс — ca\kc-an-fns-progress.json.
"""
import glob, gzip, io, json, os, re, sqlite3, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
FNS = r'C:\sender\_ops\ak\fns'
ДРОП = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    лог = os.path.join(ПАПКА, 'kc_fns_vyzhimka_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(10)
    print('===ИТОГ=== запущен')
    sys.exit(0)


def отметка(**k):
    k['обновлено'] = time.strftime('%H:%M:%S')
    with open(os.path.join(ПАПКА, 'kc-an-fns-progress.json'), 'w', encoding='utf-8') as f:
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
                    if инн.isdigit():
                        дох[инн] = (д, р)
    отметка(этап='revexp', юл=len(дох))
    штат = {}
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
    отметка(этап='sshr', со_штатом=len(штат))
    окв = {}
    фф = [f for f in glob.glob(os.path.join(FNS, 'data-*-structure-*.zip')) if os.path.exists(f + '.ok')]
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
                            if ch.get('КодОКВЭД'):
                                доп.append(ch.get('КодОКВЭД'))
                    if инн in дох and осн:
                        окв[инн] = (осн, доп, 'мсп')
            if i % 500 == 0:
                отметка(этап='rsmp', файл=i, с_оквэд=len(окв))

    def взять(инн, о, все=''):
        инн = str(инн or '').strip()
        м = re.match(r'\s*(\d{2}(?:\.\d{1,2}){0,2})', str(о or ''))
        if м and инн in дох and инн not in окв:
            окв[инн] = (м.group(1), re.findall(r'\d{2}(?:\.\d{1,2}){0,2}', str(все or ''))[:40], 'базы')
    for бд, q in ((r'C:/sender/obzvon-index.db', 'select inn, okved_main, okved_all_codes from obzvon'),
                  (r'C:/sender/enrich.db', "select inn, okved_main, '' from requisites")):
        try:
            con = sqlite3.connect('file:%s?mode=ro' % бд, uri=True, timeout=120)
            for инн, о, все in con.execute(q):
                взять(инн, о, все)
            con.close()
        except Exception as e:  # noqa: BLE001
            отметка(ошибка=repr(e)[:200])
    п = os.path.join(ПАПКА, 'ca-inn-okved-30.jsonl')
    if os.path.exists(п):
        for s in io.open(п, encoding='utf-8'):
            try:
                y = json.loads(s)
                взять(y['inn'], y.get('оквэд'))
            except (ValueError, KeyError):
                pass
    вых = os.path.join(ПАПКА, 'kc-an-fns.jsonl.gz')
    with gzip.open(вых, 'wt', encoding='utf-8') as f:
        for инн, (д, р) in дох.items():
            о = окв.get(инн, ('', [], ''))
            f.write(json.dumps([инн, round(д), round(р), штат.get(инн), о[0], ','.join(о[1]), о[2]], ensure_ascii=False) + '\n')
    import shutil
    shutil.copyfile(вых, os.path.join(ДРОП, 'kc-an-fns.jsonl.gz'))
    отметка(этап='готово', юл=len(дох), с_оквэд=len(окв), со_штатом=len(штат))


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:  # noqa: BLE001
        отметка(этап='ошибка', ошибка=repr(e)[:400])
        raise
