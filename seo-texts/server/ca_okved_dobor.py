# -*- coding: utf-8 -*-
r"""Шаг 1б плана PLAN_CA_O2_N2.md: ОКВЭД для крупных не-МСП без кода (ca\ca-net-okved.json от ca_fns_reestr.py,
~36 тыс. юрлиц с доходом от 30 млн) и их категории ca_cel.

09.11, владелец: «правки категорий применяй, добирай ОКВЭД дальше»; решение 6: «бесплатно, но наиболее полно,
если что через Checko добиваем». Порядок:
  1. бесплатно и мгновенно — все *.jsonl сервера с ОКВЭД (kc-okved-fns, poisk-okved, *checko*, *dadata*, свой выход);
  2. DaData findById — сверху списка (самые крупные), не больше ЛИМИТ_DADATA за запуск (бесплатно 10k/день, часть
     оставляем news-scan'у); 403/429 — поток DaData останавливается;
  3. checko.ru через прокси владельца (checko-proxies.json) — снизу списка, навстречу DaData.
ГИР БО (bo.nalog.ru) проверен 09.11: поиск по ИНН отдаёт страницу сайта, не данные — не используем.
Выход (fsync, резюм по ИНН): ca\ca-okved-dobor.jsonl; итог по категориям — ca\ca-dobor-itog.json и
ca\ca-ne-msp-kat.jsonl (не-МСП с категориями), раз в 10 минут и в конце; копии на дроп.
Запуск: python ca_okved_dobor.py (сам уходит в фон, низкий приоритет, замок от второго экземпляра).
"""
import collections, glob, io, json, os, re, subprocess, sys, threading, time, urllib.error, urllib.request

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
D = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    os.makedirs(ПАПКА, exist_ok=True)
    лог = os.path.join(ПАПКА, 'ca_okved_dobor_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(40)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-900:])
    sys.exit(0)

ПРОГ = os.path.join(ПАПКА, 'ca-okved-dobor-progress.json')
ЗАМОК = os.path.join(ПАПКА, 'ca_okved_dobor.lock')
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

sys.path.insert(0, DIR)
os.chdir(DIR)
import ca_cel  # noqa: E402
import cc_checko_proxy as CP  # noqa: E402
import enrich_contacts as EC  # noqa: E402

ВЫХОД = os.path.join(ПАПКА, 'ca-okved-dobor.jsonl')
ЛИМИТ_DADATA = 8000
ПОТОКОВ_DADATA = 10  # DaData с сервера отвечает 10–20 с (замер 07.10)
_лок = threading.Lock()


def отметка(**k):
    k['обновлено'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(ПРОГ, 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)
    print(json.dumps(k, ensure_ascii=False)[:400], flush=True)


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def коды(s):
    if not s:
        return []
    if isinstance(s, list):
        return [str(x.get('code') if isinstance(x, dict) else x).split()[0] for x in s if x]
    return re.findall(r'\d{2}(?:\.\d{1,2}){0,2}', str(s))


def осн_код(s):
    м = re.match(r'\s*(\d{2}(?:\.\d{1,2}){0,2})', str(s or ''))
    return м.group(1) if м else ''


def main():
    спис = json.load(io.open(os.path.join(ПАПКА, 'ca-net-okved.json'), encoding='utf-8'))  # [[инн, название, доход]]
    доход = {str(x[0]): float(x[2] or 0) for x in спис}
    назв = {str(x[0]): x[1] for x in спис}
    окв = {}  # инн -> (осн, [доп], источник, статус)

    # ---------- 1. бесплатно: всё, что уже собрано на сервере ----------
    файлы = sorted(set(glob.glob(os.path.join(DIR, '*okved*.jsonl')) + glob.glob(os.path.join(DIR, '*checko*.jsonl')) +
                       glob.glob(os.path.join(DIR, '*dadata*.jsonl')))) + [ВЫХОД]
    по_ист = collections.Counter()
    for путь in файлы:
        if not os.path.exists(путь):
            continue
        for s in io.open(путь, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
            except ValueError:
                continue
            if not isinstance(y, dict):
                continue
            инн = str(y.get('inn') or y.get('инн') or '')
            if инн not in доход or инн in окв:
                continue
            о = осн_код(y.get('оквэд') or y.get('okved') or y.get('okved_main'))
            if о:
                окв[инн] = (о, коды(y.get('оквэд_все') or y.get('okveds') or y.get('okved_all')),
                            os.path.basename(путь), y.get('статус') or '')
                по_ист[os.path.basename(путь)] += 1
    # «не найден» в своём выходе — второй раз не спрашиваем
    закрыто = set(окв)
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                y = json.loads(s)
            except ValueError:
                continue
            if y.get('итог') in ('не найден', 'нет оквэд'):
                закрыто.add(str(y.get('inn')))
    очередь = sorted((i for i in доход if i not in закрыто), key=lambda i: -доход[i])
    отметка(этап='свои-файлы', всего=len(доход), найдено_в_файлах=len(окв), источники=dict(по_ист), осталось=len(очередь))

    # ---------- 2-3. DaData сверху, Checko снизу ----------
    гр = {'верх': 0, 'низ': len(очередь)}
    гл = threading.Lock()

    def взять(сверху):
        with гл:
            if гр['верх'] >= гр['низ']:
                return None
            if сверху:
                гр['верх'] += 1
                return очередь[гр['верх'] - 1]
            гр['низ'] -= 1
            return очередь[гр['низ']]

    def принять(з):
        записать(з)
        if з.get('итог') == 'ok' and з.get('оквэд'):
            with гл:
                окв[з['inn']] = (осн_код(з['оквэд']), коды(з.get('оквэд_все')), з['источник'], з.get('статус') or '')

    tok = EC._read_secret('DADATA_TOKEN')
    прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    сч = {'dadata': 0, 'checko': 0, 'ошибки_checko': 0}

    def поток_dadata():
        while tok and сч['dadata'] < ЛИМИТ_DADATA and 'стоп_dadata' not in сч:
            i = взять(True)
            if i is None:
                return
            з = {'inn': i, 'доход': доход[i], 'источник': 'dadata'}
            try:
                req = urllib.request.Request('https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                                             data=json.dumps({'query': i}).encode(), method='POST', headers={
                                                 'Content-Type': 'application/json', 'Accept': 'application/json',
                                                 'Authorization': 'Token ' + tok})
                с = json.loads(прямой.open(req, timeout=40).read()).get('suggestions') or []
                with гл:
                    сч['dadata'] += 1
                if с:
                    d = с[0]['data']
                    з.update({'итог': 'ok', 'оквэд': d.get('okved') or '',
                              'оквэд_все': [x.get('code') for x in d.get('okveds') or [] if isinstance(x, dict)],
                              'название': (d.get('name') or {}).get('short_with_opf') or с[0].get('value'),
                              'статус': (d.get('state') or {}).get('status') or ''})
                else:
                    з['итог'] = 'не найден'
            except urllib.error.HTTPError as e:
                з.update({'итог': 'ошибка', 'ошибка': 'HTTP %s' % e.code})
                записать(з)  # ИНН с ошибкой подберёт повторный запуск (резюм)
                if e.code in (403, 429):
                    сч['стоп_dadata'] = 'HTTP %s после %d запросов' % (e.code, сч['dadata'])
                    return
                continue
            except Exception as e:  # noqa: BLE001
                з.update({'итог': 'ошибка', 'ошибка': repr(e)[:80]})
            принять(з)
            time.sleep(0.2)

    def поток_checko(п):
        подряд = 0
        while подряд < 20:
            i = взять(False)
            if i is None:
                return
            з = {'inn': i, 'доход': доход[i], 'источник': 'checko'}
            код, html = п.get('https://checko.ru/search?query=%s' % i)
            if код != 200:
                з.update({'итог': 'ошибка', 'ошибка': str(код)})
                with гл:
                    сч['ошибки_checko'] += 1
                подряд += 1
                записать(з)
                continue
            подряд = 0
            т = CP.текст(html)
            if 'ничего не найдено' in т[:3000]:
                з['итог'] = 'не найден'
                записать(з)
                continue
            ок = CP.окведы(т)
            сайт = re.search(r'Сайт\s+((?:https?://)?(?:www\.)?[a-zа-я0-9\-]+(?:\.[a-zа-я0-9\-]+)+)', т, re.I)
            з.update({'итог': 'ok' if ок else 'нет оквэд', 'оквэд': ок[0] if ок else '', 'оквэд_все': ок[:40],
                      'статус': 'ликвидирована' if re.search(r'ликвидирован|прекратил[ао]? деятельность', т[:6000], re.I) else '',
                      'сайт': сайт.group(1) if сайт else ''})
            with гл:
                сч['checko'] += 1
            принять(з)

    def итог(финал=False):
        сч_к = collections.defaultdict(collections.Counter)
        п = os.path.join(ПАПКА, 'ca-ne-msp-kat.jsonl')
        with гл:
            снимок = dict(окв)
        with io.open(п + '.tmp', 'w', encoding='utf-8') as f:
            for инн, (о, доп, ист, ст) in снимок.items():
                кат = ca_cel.категории(о, доп)
                if not кат:
                    continue
                v = доход[инн]
                f.write(json.dumps({'инн': инн, 'тип': 'ЮЛ', 'мсп': 'не МСП', 'название': назв.get(инн, ''),
                                    'оквэд': о, 'оквэд_доп': доп, 'кат': кат, 'доход': v, 'статус': ст,
                                    'оквэд_откуда': ист,
                                    'ниже_порога': sorted(к for к in кат if v < ca_cel.порог(к))}, ensure_ascii=False) + '\n')
                for к, откуда in кат.items():
                    с = сч_к[к]
                    с['всего'] += 1
                    с['по_осн'] += откуда == 'осн'
                    if v >= ca_cel.порог(к):
                        с['выше_порога'] += 1
                        с['выше_порога_осн'] += откуда == 'осн'
            f.flush()
            os.fsync(f.fileno())
        os.replace(п + '.tmp', п)
        без = [i for i in доход if i not in снимок]
        пол = collections.Counter('≥1 млрд' if доход[i] >= 1e9 else '300 млн–1 млрд' if доход[i] >= 3e8 else
                                  '100–300 млн' if доход[i] >= 1e8 else '30–100 млн' for i in без)
        и = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'финал': финал, 'не_мсп_всего': len(доход), 'с_оквэд': len(снимок),
             'без_оквэд': len(без), 'без_оквэд_по_доходу': dict(пол), 'запросы': dict(сч),
             'категории_не_мсп': {к: dict(сч_к[к], статус=ca_cel.КАТ[к][1], название=ca_cel.КАТ[к][2]) for к in ca_cel.КАТ}}
        пи = os.path.join(ПАПКА, 'ca-dobor-itog.json')
        with open(пи, 'w', encoding='utf-8') as f:
            json.dump(и, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        if os.path.isdir(D):
            import shutil
            for имя in ('ca-dobor-itog.json', 'ca-ne-msp-kat.jsonl'):
                try:
                    shutil.copyfile(os.path.join(ПАПКА, имя), os.path.join(D, имя))
                except OSError:
                    pass

    итог()
    прокси = []
    try:
        прокси = [CP.Прокси(п) for п in json.load(open(os.path.join(DIR, 'checko-proxies.json')))]
        прокси = [п for п in прокси if п.get('https://checko.ru/')[0] == 200]
    except Exception as e:  # noqa: BLE001
        отметка(этап='прокси', ошибка=repr(e)[:200])
    нити = [threading.Thread(target=поток_dadata, daemon=True) for _ in range(ПОТОКОВ_DADATA)] + \
           [threading.Thread(target=поток_checko, args=(п,), daemon=True) for п in прокси]
    for н in нити:
        н.start()
    t0 = time.time()
    посл = time.time()
    while any(н.is_alive() for н in нити):
        time.sleep(30)
        отметка(этап='добор', мин=int((time.time() - t0) / 60), прокси=len(прокси), с_оквэд=len(окв),
                осталось=max(0, гр['низ'] - гр['верх']), **сч)
        if time.time() - посл > 600:
            итог()
            посл = time.time()
    итог(финал=True)
    отметка(этап='готово', с_оквэд=len(окв), осталось=max(0, гр['низ'] - гр['верх']), **сч)


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
