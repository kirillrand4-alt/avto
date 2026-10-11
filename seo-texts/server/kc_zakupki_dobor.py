# -*- coding: utf-8 -*-
r"""Контакты закупок ЕИС отдельным шагом (владелец 09.10: «ЕИС-контакты закупок брать от выручки 120 млн, а не от
1 млрд — согласен»). Контактные лица карточек закупок, где компания — заказчик, — это снабжение (ЛПР «да»).

В обходе (kc_kontakty) закупки смотрятся только от KC_ZAKUPKI_OT (1 млрд — ради скорости обхода). Этот шаг добирает
их у компаний от KC_ZAKUPKI_DOBOR_OT (по умолчанию 120 млн), у которых в записи обхода закупок ещё нет: тот же
kc_kontakty.закупки (EC.find_zakupki_contacts: RSS-поиск извещений по ИНН -> карточки -> контактный блок; карточки
из нашей базы). Результат — новая строка в <набор>-kontakty.jsonl: копия последней записи компании с полем «закупки»
и отметкой «закупки_добор» (Excel и проверки берут последнюю запись компании). Резюм: компании с отметкой
пропускаются. Запускать, когда обход этого набора не идёт (один файл).

    KC_NABOR=<набор> python kc_zakupki_dobor.py
"""
import io
import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
ВЫХОД = os.path.join(DIR, НАБОР + '-kontakty.jsonl')
ОТ = float(os.environ.get('KC_ZAKUPKI_DOBOR_OT', '120e6'))
ПОТОКОВ = int(os.environ.get('KC_ZAKUPKI_POTOKOV', '6'))
СДЕЛАНО = os.path.join(DIR, НАБОР + '-zakupki-dobor-sdelano.txt')  # ИНН без карточек ЕИС (не ошибка) — резюм
_лок = threading.Lock()


ЕИС_ИНТЕРВАЛ = float(os.environ.get('KC_EIS_INTERVAL', '1.5'))
_еис_лок, _еис_посл = threading.Lock(), [0.0]


def _еис_с_паузой(исходный):
    """11.10: первый добор meyer7 (4 потока без пауз) — ЕИС закрылся «403 Forbidden» на 4971 из 5202 через минуту.
    Все запросы ЕИС (RSS и карточки) — не чаще одного в ЕИС_ИНТЕРВАЛ с на процесс; 403/434 — пауза 2 мин и повтор."""
    def обёртка(url, *a, **k):
        for попытка in range(3):
            with _еис_лок:
                ждать = _еис_посл[0] + ЕИС_ИНТЕРВАЛ - time.time()
                if ждать > 0:
                    time.sleep(ждать)
                _еис_посл[0] = time.time()
            try:
                return исходный(url, *a, **k)
            except Exception as e:  # noqa: BLE001
                if попытка < 2 and ('403' in str(e) or '434' in str(e)):
                    time.sleep(120)
                    continue
                raise
    return обёртка


KK.EC._eis_get = _еис_с_паузой(KK.EC._eis_get)


def пора_стоп(t0_iso):
    """Файл обхода пишут и шаги оркестратора после агентов — их старт после нашего = остановиться (гонка записей)."""
    try:
        шаги = json.load(io.open(os.path.join(DIR, НАБОР + '-konveyer.json'), encoding='utf-8')).get('шаги', {})
    except Exception:  # noqa: BLE001
        return False
    return any(str((шаги.get(ш) or {}).get('старт') or '') > t0_iso
               for ш in ('pilot_sayty_agentov.py', 'kc_kontakty.py', 'kc_dorazmetka.py'))


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
    последняя = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn'):
            последняя[з['inn']] = з
    сделано = set(io.open(СДЕЛАНО, encoding='utf-8').read().split()) if os.path.exists(СДЕЛАНО) else set()
    задачи = []
    for i, к in сп.items():
        з = последняя.get(i)
        if not з or not i.isdigit() or (к.get('выручка') or 0) < ОТ or i in сделано:
            continue
        if any(x.get('люди') or x.get('url') for x in з.get('закупки') or []):
            continue
        # 11.10: первый добор meyer7 — ЕИС ответил «403 Forbidden» на 4971 из 5202 (блок адреса сервера): такие отметки
        # не считаются сделанными, при следующем запуске — повтор
        if з.get('закупки_добор') and not any(('403' in str(x.get('ошибка') or '') or '434' in str(x.get('ошибка') or ''))
                                              for x in з.get('закупки') or []):
            continue
        задачи.append((к, з))
    задачи.sort(key=lambda x: -(x[0].get('выручка') or 0))
    print('компаний для закупок ЕИС', len(задачи), 'от выручки', ОТ, flush=True)
    t0 = time.time()
    сч = {'карточек': 0, 'людей': 0, 'с людьми': 0, 'ошибок': 0}
    n = [0]

    t0_iso = time.strftime('%Y-%m-%dT%H:%M:%S')
    стоп = [False, 0.0]

    def одна(x):
        if стоп[0] or (time.time() - стоп[1] > 60 and (стоп.__setitem__(1, time.time()) or пора_стоп(t0_iso))):
            стоп[0] = True
            return
        к, з = x
        # 11.10, ревизия (№48/50): у 882 из 1884 компаний обхода ЕИС ответил «HTTP 434» (лимит частоты) — это не «закупок
        # нет»: пауза и повтор (до 3 попыток); после — запись с ошибкой (видно в проверке), отметка добора ставится
        for попытка in range(3):
            try:
                зак = KK.закупки(к)
            except Exception as e:  # noqa: BLE001
                зак = [{'ошибка': repr(e)[:100]}]
            if not any('434' in str(c.get('ошибка') or '') for c in зак):
                break
            time.sleep(60 * (попытка + 1))
        if any(c.get('url') for c in зак):
            записать(dict(з, закупки=зак, закупки_добор=time.strftime('%Y-%m-%d %H:%M')))
        elif not any(('403' in str(c.get('ошибка') or '') or '434' in str(c.get('ошибка') or '')) for c in зак):
            # 11.10: без карточек — не полная копия записи (файл обхода и так 370 МБ), а отметка «сделано» (резюм)
            with _лок:
                with io.open(СДЕЛАНО, 'a', encoding='utf-8') as f:
                    f.write(к['inn'] + '\n')
                    f.flush()
                    os.fsync(f.fileno())
        люди = sum(len(c.get('люди') or []) for c in зак)
        with _лок:
            сч['карточек'] += sum(1 for c in зак if c.get('url'))
            сч['людей'] += люди
            сч['с людьми'] += bool(люди)
            сч['ошибок'] += sum(1 for c in зак if c.get('ошибка'))
            n[0] += 1
            if n[0] % 10 == 0:
                print('готово %d/%d за %d мин' % (n[0], len(задачи), (time.time() - t0) / 60), flush=True)

    with ThreadPoolExecutor(ПОТОКОВ) as ex:
        list(ex.map(одна, задачи))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    сч['минут'] = round((time.time() - t0) / 60, 1)
    сч['компаний'] = len(задачи)
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
