# -*- coding: utf-8 -*-
# 19.10, владелец: база холодного прозвона — Кемеровская, Томская, Омская обл.; 8 отраслей; доход 2025 от 100 млн; ИНН,
# телефоны (со ссылкой на источник), название + факты из всего собранного. Шаг 1 — «вселенная» компаний:
#   * открытые данные ФНС «доходы и расходы» на 31.12.2025 (C:\sender\_ops\ak\fns\revexp.zip): ИНН с кодом региона 42/70/55
#     и доходом от 100 млн (поле СумДоход — все доходы, подпись «ФНС (доход 2025)»);
#   * база обзвона (obzvon-index.db): регион из трёх и выручка от 100 млн (ИНН мог быть выдан в другом регионе).
# Шаг 2 — карточка checko.ru по каждому ИНН (прокси владельца, 10 потоков): статус, основной ОКВЭД, адрес/регион,
# руководитель, телефоны карточки, счётчики «Госзакупки»/«Проверки», ссылка на карточку.
# Durable: hz\hz-univers.jsonl, hz\hz-checko.jsonl (fsync, резюм). Лог: hz_univers_*.log.
import io, json, os, sqlite3, sys, threading, time, xml.etree.ElementTree as ET, zipfile
DIR = r'C:\sender\server'
HZ = os.path.join(DIR, 'hz')
УН = os.path.join(HZ, 'hz-univers.jsonl')
ЧК = os.path.join(HZ, 'hz-checko.jsonl')
ПОТОКОВ = int(os.environ.get('CHECKO_POTOKOV', '10'))
if __name__ == '__main__' and '--vnutri' not in sys.argv:
    import subprocess
    os.makedirs(HZ, exist_ok=True)
    лог = os.path.join(HZ, 'hz_univers_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'hz_univers.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                             close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    time.sleep(120)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                     ensure_ascii=False))
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import cc_checko_proxy as CP  # noqa: E402
import fsa_meyer_checko as FC  # noqa: E402  (разбор карточки checko)
CP.ВЫХОД = ЧК
РЕГ = ('42', '70', '55')
_лок = threading.Lock()


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


def писать(путь, x):
    with _лок:
        with io.open(путь, 'a', encoding='utf-8') as f:
            f.write(json.dumps(x, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def вселенная():
    if os.path.exists(УН):
        return {y['inn']: y for y in FC.читать(УН)}
    ун = {}
    z = zipfile.ZipFile(r'C:\sender\_ops\ak\fns\revexp.zip')
    for zi in z.infolist():
        with z.open(zi) as fh:
            for ev, el in ET.iterparse(fh, events=('end',)):
                if not el.tag.endswith('Документ'):
                    continue
                i = v = None
                for ch in el:
                    if 'СведНП' in ch.tag:
                        i = ch.get('ИННЮЛ') or ch.get('ИННФЛ')
                    elif 'ДохРасх' in ch.tag:
                        v = ch.get('СумДоход')
                if i and v and i[:2] in РЕГ:
                    try:
                        д = float(v)
                    except ValueError:
                        д = 0
                    if д >= 1e8:
                        ун[i] = {'inn': i, 'доход_фнс_2025': д, 'откуда': 'ФНС (доход 2025)'}
                el.clear()
    п('ФНС: ИНН 42/70/55 с доходом от 100 млн', len(ун))
    c = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True)
    n = 0
    for инн, рег, выр, год in c.execute("select inn, region, revenue_rub, god_otch from obzvon where region like '%Кемеров%' "
                                         "or region like '%Томск%' or region like '%Омск%'"):
        try:
            в = float(выр or 0)
        except ValueError:
            в = 0
        if в >= 1e8 and инн and инн not in ун:
            ун[инн] = {'inn': инн, 'выручка_база': в, 'год_база': год or '', 'откуда': 'база обзвона (регион %s)' % рег}
            n += 1
    п('добавлено из базы обзвона (регион 3 обл., ИНН другого кода или нет в ФНС)', n)
    with io.open(УН, 'w', encoding='utf-8') as f:
        for x in ун.values():
            f.write(json.dumps(x, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return ун


def main():
    t0 = time.time()
    ун = вселенная()
    готово = {y['inn'] for y in FC.читать(ЧК) if y.get('итог') in ('ok', 'не найдена')}
    очередь = sorted(i for i in ун if i not in готово)
    прокси = [CP.Прокси(x) for x in json.load(open(os.path.join(DIR, 'checko-proxies.json')))]
    живые = [x for x in прокси if x.get('https://checko.ru/')[0] == 200]
    п('вселенная', len(ун), '| checko к проходу', len(очередь), '| прокси', len(живые))
    всего = len(очередь)
    n = [0]

    def поток(k):
        while True:
            with _лок:
                if not очередь:
                    return
                инн = очередь.pop(0)
                n[0] += 1
                m = n[0]
            код, html = живые[(k + m) % len(живые)].get('https://checko.ru/search?query=%s' % инн)
            з = {'inn': инн, 'код': код}
            if код == 200 and html:
                try:
                    з.update(FC.разобрать(html))
                except Exception as e:  # noqa: BLE001
                    з['ошибка_разбора'] = repr(e)[:80]
                з['итог'] = 'ok' if FC.re.search(r'/(company|entrepreneur)/', з.get('ссылка') or '') else 'не найдена'
            else:
                з['итог'] = 'ошибка'
            писать(ЧК, з)
            if m % 500 == 0:
                п('checko', m, 'из', всего, '| %.0f в мин' % (m / max(1, (time.time() - t0) / 60)))

    тт = [threading.Thread(target=поток, args=(k,)) for k in range(ПОТОКОВ)]
    for т in тт:
        т.start()
    for т in тт:
        т.join()
    все = {y['inn']: y for y in FC.читать(ЧК)}
    п('===ИТОГ===', json.dumps({'вселенная': len(ун), 'checko ok': sum(1 for y in все.values() if y.get('итог') == 'ok'),
                                'действующих': sum(1 for y in все.values() if 'ействующ' in (y.get('статус') or ''))},
                               ensure_ascii=False), 'за %.1f мин' % ((time.time() - t0) / 60))


if __name__ == '__main__':
    main()
