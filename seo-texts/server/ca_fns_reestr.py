# -*- coding: utf-8 -*-
r"""Шаг 0+1 плана PLAN_CA_O2_N2.md: реестр «от налоговой» и замер по категориям ca_cel. Только чтение баз; без моделей.

09.11, владелец: «идём от налоговой: всех, кто подходит под категории, потом сайт и глубокие контакты»; подписку ЕГРЮЛ
не берём — «пытаемся бесплатно, но наиболее полно (если что, через checko добиваем)».
1. Реестр МСП ФНС (rsmp, открытые данные, все ОКВЭД МСП, ЮЛ и ИП) — качаем свежий месяц в C:\sender\_ops\ak\fns\.
2. revexp (доходы всех организаций, сдавших отчётность) — универсум ИНН. Не-МСП = revexp минус МСП-ЮЛ: крупные и
   ЛЮБЫЕ дочки с долей холдинга > 49 % (фабрики золотых холдингов, рыбхозы групп, фармзаводы). Их ОКВЭД — из своих
   баз (база обзвона, enrich.db companies/requisites, файлы checko/DaData); у кого нет — список ca-net-okved.json
   (по убыванию дохода) для добора checko/ГИР БО на следующем шаге.
3. sshr — среднесписочная численность.
Выход (C:\sender\server\ca\): ca-reestr.jsonl — все попавшие в категории (ИНН, тип, категория МСП, название, регион,
ОКВЭД, категории ca_cel с «осн/доп», доход, ССЧ, «ниже порога»); ca-zamer.json — счётчики; ca-net-okved.json.
Копии ca-zamer.json и ca-net-okved.json — на дроп. ФИО ИП не сохраняем.
Запуск: python ca_fns_reestr.py — сам уходит в фон (низкий приоритет), прогресс — ca\ca-zamer-progress.json.
"""
import collections, glob, io, json, os, re, shutil, sqlite3, ssl, subprocess, sys, time, urllib.request, zipfile
import xml.etree.ElementTree as ET

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
FNS = r'C:\sender\_ops\ak\fns'
ДРОП = r'C:\seostat\drop\drop-storage'
ПОРОГ_НЕМСП = float(os.environ.get('CA_NEMSP_OT', '30e6'))  # ниже — не-МСП не рассматриваем (мелочь без ОКВЭД)

if '--vnutri' not in sys.argv:
    os.makedirs(ПАПКА, exist_ok=True)
    лог = os.path.join(ПАПКА, 'ca_fns_reestr_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)  # 0x4000 — BELOW_NORMAL: нагрузка сервера ≤ 90 %
    time.sleep(40)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-900:])
    sys.exit(0)

sys.path.insert(0, DIR)
import ca_cel  # noqa: E402

# 09.11: раннер перезапускал запуск по своему таймауту — четыре копии писали в один .part; второй экземпляр выходит
ЗАМОК = os.path.join(ПАПКА, 'ca_fns_reestr.lock')
try:
    _fd = os.open(ЗАМОК, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(_fd, str(os.getpid()).encode())
    os.close(_fd)
except FileExistsError:
    _pid = open(ЗАМОК).read().strip()
    if _pid and str(_pid) in subprocess.run(['tasklist', '/FI', 'PID eq %s' % _pid], capture_output=True, text=True).stdout:
        print('уже запущен, pid', _pid)
        sys.exit(0)
    open(ЗАМОК, 'w').write(str(os.getpid()))

ПРОГ = os.path.join(ПАПКА, 'ca-zamer-progress.json')
сост = {'старт': time.strftime('%Y-%m-%d %H:%M:%S'), 'этап': 'rsmp-ссылка'}


def отметка(**k):
    сост.update(k, обновлено=time.strftime('%H:%M:%S'))
    with open(ПРОГ, 'w', encoding='utf-8') as f:
        json.dump(сост, f, ensure_ascii=False)
    print(json.dumps(k, ensure_ascii=False)[:300], flush=True)


def ssl_ctx():
    ctx = ssl.create_default_context()
    for n in glob.glob(r'C:\sender\_tmp\tender_ca\*.crt'):  # корневые сертификаты Минцифры (сайты ФНС)
        try:
            ctx.load_verify_locations(n)
        except Exception:  # noqa: BLE001
            pass
    return ctx


UA = 'Mozilla/5.0 (compatible; ruspromdata/1.0)'


def get(url, ctx, tmo=120):
    з = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; ruspromdata/1.0)'})
    return urllib.request.urlopen(з, timeout=tmo, context=ctx)


def скачать_rsmp(ctx):
    ссылки = set()
    for стр in ('https://www.nalog.gov.ru/opendata/7707329152-rsmp/', 'https://www.nalog.gov.ru/opendata/7707329152-rsmp/meta.csv'):
        try:
            ссылки |= set(re.findall(r'https?://file\.nalog\.ru/opendata/7707329152-rsmp/data-\d{8}-structure-\d{8}\.zip',
                                     get(стр, ctx).read().decode('utf-8', 'replace')))
        except Exception as e:  # noqa: BLE001
            отметка(ошибка_ссылки=repr(e)[:200])
    if not ссылки:
        raise SystemExit('нет ссылки на rsmp')
    url = max(ссылки, key=lambda u: (lambda d: d[4:] + d[2:4] + d[:2])(re.search(r'data-(\d{8})', u).group(1)))
    путь = os.path.join(FNS, os.path.basename(url))
    if os.path.exists(путь + '.ok'):
        отметка(этап='rsmp-есть', url=url)
        return путь
    # 09.11: докачка «с конца файла» дала архив, битый с места первого обрыва (3321 из 7440 файлов) — теперь качаем
    # кусками по 64 МБ с явным Range a-b, сверяем длину и Content-Range, пишем по смещению; в конце — CRC всех файлов
    # архива; только после этого рядом кладётся метка .ok (её ждёт ca_pokupateli.py)
    if os.path.exists(путь) and целый(путь):
        open(путь + '.ok', 'w').close()
        return путь
    for f in (путь, путь + '.part'):
        if os.path.exists(f):
            os.remove(f)
    if shutil.disk_usage(FNS).free < 15e9:
        raise SystemExit('мало места под rsmp')
    з = urllib.request.Request(url, headers={'User-Agent': UA, 'Range': 'bytes=0-0'})
    with urllib.request.urlopen(з, timeout=120, context=ctx) as r:
        всего = int(r.headers['Content-Range'].split('/')[-1])
    КУС = 64 << 20
    куски = [(a, min(a + КУС, всего) - 1) for a in range(0, всего, КУС)]
    отметка(этап='rsmp-качаю', url=url, всего_мб=всего >> 20, кусков=len(куски))
    with open(путь + '.part', 'wb') as f:
        f.truncate(всего)
    with open(путь + '.part', 'r+b') as f:
        for k, (a, b) in enumerate(куски):
            for попытка in range(15):
                try:
                    з = urllib.request.Request(url, headers={'User-Agent': UA, 'Range': 'bytes=%d-%d' % (a, b)})
                    with urllib.request.urlopen(з, timeout=300, context=ctx) as r:
                        cr = r.headers.get('Content-Range') or ''
                        if r.status != 206 or not cr.startswith('bytes %d-%d/' % (a, b)):
                            raise IOError('не тот кусок: %s %s' % (r.status, cr))
                        данные = r.read()
                    if len(данные) != b - a + 1:
                        raise IOError('кусок %d: %d из %d байт' % (k, len(данные), b - a + 1))
                    f.seek(a)
                    f.write(данные)
                    break
                except Exception as e:  # noqa: BLE001
                    отметка(ошибка_скачивания=repr(e)[:200], кусок=k, попытка=попытка)
                    time.sleep(10 * min(попытка + 1, 6))
            else:
                raise SystemExit('кусок %d не скачался' % k)
            if k % 4 == 0:
                отметка(этап='rsmp-качаю', кусок=k, кусков=len(куски))
        f.flush()
        os.fsync(f.fileno())
    if not целый(путь + '.part'):
        os.replace(путь + '.part', путь + '.bad')
        raise SystemExit('rsmp битый после скачивания')
    os.replace(путь + '.part', путь)
    open(путь + '.ok', 'w').close()
    return путь


def целый(путь):
    """CRC всех файлов архива (zipfile проверяет при полном чтении)."""
    отметка(этап='rsmp-проверка CRC')
    try:
        with zipfile.ZipFile(путь) as z:
            for i in z.infolist():
                with z.open(i) as fh:
                    while fh.read(1 << 22):
                        pass
        return True
    except Exception as e:  # noqa: BLE001
        отметка(rsmp_битый=repr(e)[:200])
        return False



def документы(fh):
    """Элементы <Документ> по одному; корень чистим, иначе миллионы пустых узлов копятся в памяти."""
    корень = None
    for ev, el in ET.iterparse(fh, events=('start', 'end')):
        if корень is None:
            корень = el
        if ev == 'end' and el.tag.endswith('Документ'):
            yield el
            корень.clear()


def атр(el, *имена):
    for и in имена:
        v = el.get(и)
        if v:
            return v
    return ''


def main():
    os.makedirs(ПАПКА, exist_ok=True)
    ctx = ssl_ctx()
    rsmp = скачать_rsmp(ctx)
    # ---------- 1. МСП ----------
    отметка(этап='rsmp-разбор')
    мсп_юл = set()  # int(ИНН) всех МСП-ЮЛ: их ОКВЭД известен из реестра
    записи = {}  # ИНН -> запись (только попавшие в категории)
    наим_кода = {}
    n = 0
    with zipfile.ZipFile(rsmp) as z:
        файлы = [x for x in z.namelist() if x.lower().endswith('.xml')]
        for i, имя in enumerate(файлы):
            with z.open(имя) as fh:
                for el in документы(fh):
                    n += 1
                    инн, тип, назв, рег, осн, доп = '', '', '', '', '', []
                    for ch in el.iter():
                        т = ch.tag
                        if т.endswith('ОргВклМСП'):
                            инн, тип, назв = атр(ch, 'ИННЮЛ'), 'ЮЛ', атр(ch, 'НаимОргСокр', 'НаимОрг')
                        elif т.endswith('ИПВклМСП'):
                            инн, тип = атр(ch, 'ИННФЛ'), 'ИП'
                        elif т.endswith('СведМН'):
                            рег = атр(ch, 'КодРегион')
                        elif т.endswith('СвОКВЭДОсн'):
                            осн = атр(ch, 'КодОКВЭД')
                            наим_кода.setdefault(осн, атр(ch, 'НаимОКВЭД'))
                        elif т.endswith('СвОКВЭДДоп'):
                            к = атр(ch, 'КодОКВЭД')
                            доп.append(к)
                            наим_кода.setdefault(к, атр(ch, 'НаимОКВЭД'))
                    if тип == 'ЮЛ' and инн.isdigit():
                        мсп_юл.add(int(инн))
                    кат = ca_cel.категории(осн, доп)
                    if кат and инн:
                        записи[инн] = {'инн': инн, 'тип': тип, 'мсп': атр(el, 'КатСубМСП'), 'название': назв if тип == 'ЮЛ' else '',
                                       'регион': рег, 'оквэд': осн, 'оквэд_доп': доп, 'кат': кат, 'ссч': атр(el, 'ССЧР'),
                                       'оквэд_откуда': 'МСП'}
            if i % 50 == 0:
                отметка(этап='rsmp-разбор', файл=i, файлов=len(файлы), документов=n, в_категориях=len(записи))
    отметка(этап='rsmp-готов', документов=n, мсп_юл=len(мсп_юл), в_категориях=len(записи))
    # ---------- 2. revexp: доход; не-МСП выше порога ----------
    доход, не_мсп = {}, {}
    with zipfile.ZipFile(os.path.join(FNS, 'revexp.zip')) as z:
        for имя in z.namelist():
            with z.open(имя) as fh:
                for el in документы(fh):
                    инн = назв = ''
                    v = 0.0
                    for ch in el:
                        if 'СведНП' in ch.tag:
                            инн, назв = атр(ch, 'ИННЮЛ'), атр(ch, 'НаимОрг')
                        elif 'ДохРасх' in ch.tag:
                            try:
                                v = float(ch.get('СумДоход') or 0)
                            except ValueError:
                                pass
                    if инн in записи:
                        доход[инн] = v
                    elif инн.isdigit() and int(инн) not in мсп_юл and v >= ПОРОГ_НЕМСП:
                        не_мсп[инн] = (назв, v)
    всего_revexp = len(доход) + len(не_мсп)
    отметка(этап='revexp-готов', не_мсп_выше_порога=len(не_мсп))
    # ---------- 3. ОКВЭД не-МСП из своих баз ----------
    окв = {}  # ИНН -> (осн, [доп], источник)

    def взять(инн, осн, доп, ист):
        осн = str(осн or '').split()[0] if осн else ''
        if инн in не_мсп and инн not in окв and (осн or доп):
            окв[инн] = (осн, [str(x).split()[0] for x in доп or [] if x], ист)

    def коды(s):
        if not s:
            return []
        if isinstance(s, list):
            return s
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [x.get('code') if isinstance(x, dict) else x for x in v]
        except (ValueError, TypeError):
            pass
        return re.findall(r'\d{2}(?:\.\d{1,2}){0,2}', str(s))
    try:
        con = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True)
        for (т,) in con.execute("select name from sqlite_master where type='table'"):
            кол = [r[1] for r in con.execute('pragma table_info("%s")' % т)]
            if 'inn' in кол and 'okved_main' in кол:
                доп_к = 'okved_all_codes' if 'okved_all_codes' in кол else 'okved_main'
                for инн, о, д in con.execute('select inn, okved_main, %s from "%s"' % (доп_к, т)):
                    взять(str(инн or '').strip(), о, коды(д), 'обзвон')
        con.close()
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_обзвон=repr(e)[:200])
    try:
        con = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
        for инн, о, д in con.execute('select inn, okved_main, okved_all from requisites'):
            взять(str(инн or '').strip(), о, коды(д), 'enrich-реквизиты')
        for инн, о in con.execute('select inn, okved from companies'):
            взять(str(инн or '').strip(), о, [], 'enrich')
        con.close()
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_enrich=repr(e)[:200])
    # 09.11: *okved*.jsonl (kc-okved-fns, poisk-okved) и добор ca_okved_dobor.py раньше не читались
    for путь in sorted(set(glob.glob(os.path.join(DIR, '*checko*.jsonl')) + glob.glob(os.path.join(DIR, '*dadata*.jsonl')) +
                           glob.glob(os.path.join(DIR, '*okved*.jsonl')) + glob.glob(os.path.join(ПАПКА, 'ca-okved-dobor.jsonl')))):
        for s in io.open(путь, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
            except ValueError:
                continue
            if not isinstance(y, dict):
                continue
            инн = str(y.get('inn') or y.get('инн') or '')
            if инн in не_мсп:
                взять(инн, y.get('оквэд') or y.get('okved'), коды(y.get('оквэд_все') or y.get('okveds')),
                      os.path.basename(путь))
    отметка(этап='оквэд-не-мсп', с_оквэд=len(окв))
    нет_окв = []
    for инн, (назв, v) in не_мсп.items():
        if инн not in окв:
            нет_окв.append((v, инн, назв))
            continue
        осн, доп, ист = окв[инн]
        кат = ca_cel.категории(осн, доп)
        if кат:
            записи[инн] = {'инн': инн, 'тип': 'ЮЛ', 'мсп': 'не МСП', 'название': назв, 'регион': инн[:2], 'оквэд': осн,
                           'оквэд_доп': доп, 'кат': кат, 'ссч': '', 'оквэд_откуда': ист}
            доход[инн] = v
    нет_окв.sort(reverse=True)
    # ---------- 4. численность ----------
    try:
        with zipfile.ZipFile(os.path.join(FNS, 'sshr.zip')) as z:
            for имя in z.namelist():
                with z.open(имя) as fh:
                    for el in документы(fh):
                        инн = кол = ''
                        for ch in el.iter():
                            инн = инн or атр(ch, 'ИННЮЛ')
                            кол = кол or атр(ch, 'КолРаб')
                        if инн in записи and кол and not записи[инн]['ссч']:
                            записи[инн]['ссч'] = кол
    except Exception as e:  # noqa: BLE001
        отметка(ошибка_sshr=repr(e)[:200])
    # ---------- 5. запись и счётчики ----------
    сч = collections.defaultdict(collections.Counter)
    with open(os.path.join(ПАПКА, 'ca-reestr.jsonl'), 'w', encoding='utf-8') as f:
        for инн, r in записи.items():
            r['доход'] = доход.get(инн)
            r['ниже_порога'] = sorted(к for к in r['кат'] if (r['доход'] or 0) < ca_cel.порог(к))
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            for к, откуда in r['кат'].items():
                с = сч[к]
                с['всего'] += 1
                с['по_осн' if откуда == 'осн' else 'только_доп'] += 1
                с['ИП' if r['тип'] == 'ИП' else 'не_МСП' if r['мсп'] == 'не МСП' else 'МСП_ЮЛ'] += 1
                if к not in r['ниже_порога']:
                    с['выше_порога'] += 1
                    if откуда == 'осн':
                        с['выше_порога_осн'] += 1
        f.flush()
        os.fsync(f.fileno())
    итог = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'rsmp': os.path.basename(rsmp), 'документов_мсп': n,
            'мсп_юл': len(мсп_юл), 'revexp_организаций_в_учёте': всего_revexp, 'порог_не_мсп': ПОРОГ_НЕМСП,
            'не_мсп_выше_порога': len(не_мсп), 'не_мсп_с_оквэд_из_своих_баз': len(окв),
            'не_мсп_без_оквэд': len(нет_окв),
            'не_мсп_без_оквэд_по_доходу': dict(collections.Counter(
                '≥1 млрд' if v >= 1e9 else '300 млн–1 млрд' if v >= 3e8 else '100–300 млн' if v >= 1e8 else '30–100 млн'
                for v, _, _ in нет_окв)),
            'источники_оквэд_не_мсп': dict(collections.Counter(x[2] for x in окв.values())),
            'категории': {к: dict(сч[к], газ=ca_cel.КАТ[к][0], статус=ca_cel.КАТ[к][1], название=ca_cel.КАТ[к][2],
                                  порог=ca_cel.КАТ[к][4]) for к in ca_cel.КАТ},
            'названия_кодов': {к: наим_кода.get(к, '') for к in sorted({к for r in записи.values()
                                                                       for к in [r['оквэд']] + r['оквэд_доп']
                                                                       if ca_cel.категории(к)})}}
    for имя, данные in (('ca-zamer.json', итог), ('ca-net-okved.json', [[и, н, v] for v, и, н in нет_окв])):
        п = os.path.join(ПАПКА, имя)
        with open(п, 'w', encoding='utf-8') as f:
            json.dump(данные, f, ensure_ascii=False, indent=1 if имя == 'ca-zamer.json' else None)
            f.flush()
            os.fsync(f.fileno())
        if os.path.isdir(ДРОП):
            shutil.copyfile(п, os.path.join(ДРОП, имя))
    отметка(этап='готово', в_категориях=len(записи), не_мсп_без_оквэд=len(нет_окв))


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
