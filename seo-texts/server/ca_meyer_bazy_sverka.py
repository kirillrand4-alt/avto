# -*- coding: utf-8 -*-
r"""Есть ли покупатели-лукэлайки Meyer (зерновые, мукомолы, животноводство, опт зерна и др.) в НАШИХ базах Meyer, а не
только в базе обзвона (10.11, владелец: «там вроде не только база обзвона, но ещё несколько баз есть, где они могут быть»).

Цель — юрлица с доходом от 30 млн (ca\ca-inn-okved-30.jsonl от ca_meyer_sverka.py) в ядровых классах Meyer. По каждому
файлу-базе (текущие версии, без .bak) ищем ИНН (10 цифр) построчно; плюс база обзвона (base_label) и сделки Битрикса.
Выход: ca\ca-meyer-bazy-sverka.json (+ дроп) — счётчики по классам и базам, без персональных данных. Только чтение.
"""
import collections, io, json, os, re, sqlite3, subprocess, sys, time

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:  # сам в фон (файлы на сотни МБ — дольше окна раннера), низкий приоритет
    лог = os.path.join(ПАПКА, 'ca_meyer_bazy_sverka_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(15)
    print('===ИТОГ=== запущен', open(лог, encoding='utf-8', errors='replace').read()[-300:])
    sys.exit(0)
ЗАМОК = os.path.join(ПАПКА, 'ca_meyer_bazy_sverka.lock')
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
КЛАССЫ = {'01.11': 'зерновые', '01.1': 'растениеводство (01.1)', '01.13': 'овощи', '01.41': 'молочное животноводство',
          '01.50': 'смешанное хозяйство', '10.61': 'мукомолы/крупы', '46.21': 'опт зерна и семян', '10.39': 'переработка овощей/орехов',
          '10.83': 'кофе/чай', '10.41': 'масла', '10.89': 'прочая пищевка', '10.82': 'кондитерка', '52.10': 'склады/элеваторы',
          '10.91': 'корма', '01.61': 'услуги растениеводства', '01.64': 'семена'}
БАЗЫ = [os.path.join(DIR, x) for x in ('meyer7-spisok.json', 'meyer-ishodnaya-obzvon-0610.csv', 'meyer-ishodnaya-companies-0610.csv',
                                         'meyer-kompanii-0510.csv', 'meyer-kontakty-0510.csv', 'meyer-nalichie.jsonl',
                                         'fsa-meyer-izg.jsonl', 'fsa-meyer-checko.jsonl', 'fsa-meyer-otsev.jsonl', 'fsa-orehi.jsonl',
                                         'meyer7-pasport.jsonl', 'pilot-kontakty.jsonl', 'fsa120s-kontakty.jsonl', 'fsavkc-kontakty.jsonl')] + \
       [os.path.join(ДРОП, x) for x in ('MEYER-BAZA-KOMPANII.csv', 'meyer-baza-kontakty-0610.csv', 'fsa-meyer-decl-svod.jsonl',
                                        'fsa-klass3-vhod.json', 'meyer7-kontakty-slim.jsonl', 'park_obshchie_inn.jsonl')] + \
       [os.path.join(r'C:\sender', x) for x in ('park_gaz_inn.jsonl', 'park_brendy_inn.jsonl')]
ИНН = re.compile(r'(?<!\d)(\d{10})(?!\d)')


def класс(о):
    ч = str(о or '').split('.')
    кл2 = '.'.join(ч[:2])
    return кл2 if кл2 in КЛАССЫ else ('01.1' if кл2.startswith('01.1') else '')


def main():
    t0 = time.time()
    цель = {}
    for s in io.open(os.path.join(ПАПКА, 'ca-inn-okved-30.jsonl'), encoding='utf-8'):
        y = json.loads(s)
        кл = класс(y.get('оквэд'))
        if кл:
            цель[y['inn']] = кл
    где = collections.defaultdict(set)
    размеры = {}
    for п in БАЗЫ:
        if not os.path.exists(п):
            размеры[os.path.basename(п)] = 'нет файла'
            continue
        имя = os.path.basename(п)
        n = 0
        with io.open(п, encoding='utf-8', errors='replace') as f:
            for s in f:
                for м in ИНН.finditer(s):
                    if м.group(1) in цель:
                        где[м.group(1)].add(имя)
                        n += 1
        размеры[имя] = n
        print(имя, n, int(time.time() - t0), 'с', flush=True)
    try:
        con = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=120)
        for инн, н in con.execute('select inn, base_label from obzvon'):
            if str(инн) in цель:
                где[str(инн)].add('обзвон: ' + str(н))
        con.close()
    except Exception as e:  # noqa: BLE001
        размеры['обзвон'] = repr(e)[:100]
    сд = json.load(io.open(os.path.join(ДРОП, 'sdelki-vse-1410.json'), encoding='utf-8'))
    for инн in цель:
        for d in сд.get(инн) or []:
            где[инн].add('сделка ' + d[0])
    по_кл = collections.defaultdict(collections.Counter)
    for инн, кл in цель.items():
        к = по_кл[кл]
        к['всего'] += 1
        м = где.get(инн, set())
        for x in м:
            к[x] += 1
        базы_meyer = {x for x in м if not x.startswith('сделка') and not x.startswith('обзвон: Компрессор')}
        к['в базах Meyer (любой файл или обзвон Meyer)'] += bool(базы_meyer)
        к['со сделкой (любой)'] += any(x.startswith('сделка') for x in м)
        к['нигде нет'] += not м
    итог = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'порог': 'доход от 30 млн', 'секунд': int(time.time() - t0),
            'совпадений_по_файлам': размеры,
            'классы': {кл: dict(по_кл[кл], название=КЛАССЫ.get(кл, кл)) for кл in sorted(по_кл, key=lambda k: -по_кл[k]['всего'])}}
    п = os.path.join(ПАПКА, 'ca-meyer-bazy-sverka.json')
    with open(п, 'w', encoding='utf-8') as f:
        json.dump(итог, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    import shutil
    shutil.copyfile(п, os.path.join(ДРОП, 'ca-meyer-bazy-sverka.json'))
    print('===ИТОГ=== готово', итог['секунд'], 'с')


if __name__ == '__main__':
    try:
        main()
    finally:
        try:
            os.remove(ЗАМОК)
        except OSError:
            pass
