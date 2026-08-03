# -*- coding: utf-8 -*-
"""Закупки Tender.pro по КАЖДОМУ предприятию нашей очереди, а не по ключевым словам.

Зачем это отдельный проход, если обход по словам уже сделан. Обход по словам берёт то, что
попало под десять формулировок, и на этом останавливается. Замер 03.08: по семи крупнейшим
компаниям нашего сбора у нас 2 651 тендер, а на их страницах порядка 152 000 — взята примерно
одна пятидесятая. Причина простая: закупка называется «поставка воздуходувки», «ремонт ТВ-80»,
«запчасти к К-500» и ещё сотней способов, и словарь их не догоняет. Зато если зайти НА СТРАНИЦУ
КОМПАНИИ, видно всё, что она вообще закупала.

Как устроено сужение. Сужает не параметр, а путь:
    /api/company/<company_id>/view?active_tab=purchases&block=tenders&tender_name=<слово>
Замер чистоты: Химпром 51053 плюс «компрессор» дал 415 тендеров, все 415 его, чужих ноль.
Контроль бессмыслицей возвращает ноль, значит фильтр действительно применяется.

Две ловушки, обе тихие, обе стоили времени:
  * без `block=tenders` параметр `page` МОЛЧА игнорируется, и все страницы возвращают одни и те
    же 25 записей. Выглядит как работающая пагинация;
  * `company_id` в строке запроса `/api/tenders/list` площадкой ИГНОРИРУЕТСЯ. Именно на этом
    основывался прежний вывод «сужение не поддерживается», и он был неверен: проверен был один
    параметр на одном адресе.

ИНН превращается в `company_id` через каталог площадки `/api/companies/list?inn=<ИНН>`, и он
знает ЛЮБУЮ компанию, а не только 384 из нашего справочника. Замер по случайной выборке 25
предприятий очереди: 12 нашлись, то есть по всей очереди ожидается около 365.

Чужие строки в выдаче считаются отдельно и печатаются. Если сужение когда-нибудь потечёт, это
должно быть видно числом сразу, а не обнаружиться потом в панели.

Использование:
    python3 tp_po_ocheredi.py                       # вся очередь
    python3 tp_po_ocheredi.py --predel 50           # первые 50 предприятий
    python3 tp_po_ocheredi.py --spisok inn.txt      # свой список ИНН
"""
import csv
import os
import sys
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tenderpro_harvest as T  # noqa: E402

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
OUT = os.path.join(L, 'centro', 'tenderpro')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
VYHOD = os.path.join(OUT, 'tp-spisok-po-kompaniyam.csv')
KARTA = os.path.join(OUT, 'tp-inn-company-id.csv')
COLS = ['inn', 'predpriyatie', 'klyuch', 'tender_id', 'predmet', 'sozdan', 'do',
        'company_id', 'company', 'chya_zakupka']
# По умолчанию — прежние десять слов. `--vsyo` заменяет их на одну пустую строку, то есть
# «страница компании целиком». Разделено флагом, а не переписано насовсем, чтобы можно было
# сравнить два прогона на одних и тех же компаниях и назвать прибавку числом.
SLOVA = T.KLYUCHI
PREDEL_STRANIC = 200


def obshchee_slovo(a, b):
    """Есть ли у двух названий общее различительное слово. Нужно ровно для одного: отличить
    ФИЛИАЛ того же предприятия от совсем чужой компании.

    Замер 03.08, из-за которого это появилось: страница компании показывает закупки её филиалов.
    У «ИСО (Москва)» пришли «Филиал ИСО в г. Каменск-Уральский», «Филиал ИСО в г. Краснотурьинск»,
    у «Комбината Магнезит» — «Филиал Группа Магнезит в пгт. Раздолинске». Счётчик чужих строк
    показал 856 из 2 804, и это выглядело как утечка сужения. Утечки нет: это тот же холдинг.
    Но записывать закупку филиала головному ИНН молча нельзя — у филиала свой ИНН и свои люди,
    поэтому строка помечается «филиал того же предприятия», и продавец видит разницу.
    """
    stop = {'филиал', 'группа', 'компания', 'завод', 'комбинат', 'ооо', 'оао', 'пао', 'ао',
            'зао', 'гуп', 'муп', 'фгуп', 'им', 'на', 'в', 'г', 'пгт', 'промплощадке',
            'для', 'нужд', 'име', 'общество', 'акционерное', 'ограниченной',
            'ответственностью', 'муниципальное', 'унитарное', 'предприятие'}
    def slova(x):
        # порог 3, а не 4: различительное слово «ИСО» ровно трёхбуквенное, и при пороге 4
        # 837 закупок филиалов ИСО помечались чужими. Такие сокращения в промышленности часты
        # (ИСО, МЭЗ, ЦОФ, НТМК), поэтому короткие слова терять нельзя.
        return {w for w in re.split(r'[^\wа-яА-ЯёЁ]+', (x or '').lower())
                if len(w) >= 3 and w not in stop}
    return bool(slova(a) & slova(b))


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def main():
    global SLOVA, PREDEL_STRANIC
    predel = int(sys.argv[sys.argv.index('--predel') + 1]) if '--predel' in sys.argv else 10 ** 9
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 3
    # --vsyo снимает словарь: берём ВСЁ, что компания закупала, а не то, что попало под десять
    # слов. Замер, из-за которого это появилось: у РУСАЛ Менеджмента по словам 1 833 закупки,
    # а на странице около 173 775. Приём «страница компании» мы взяли, а старое узкое место
    # внутри него оставили. Отсеивать должен `tip_mashiny.py`, а не словарь на входе.
    global VYHOD, KARTA
    if '--vsyo' in sys.argv:
        SLOVA = ['']
        PREDEL_STRANIC = int(sys.argv[sys.argv.index('--stranic') + 1]) \
            if '--stranic' in sys.argv else 400
        # ОТДЕЛЬНЫЕ файлы, а не дозапись в прежние. Иначе докачка сочтёт компанию пройденной
        # (её ИНН уже есть в выходе от словарного прогона) и не спросит ни одной. Заодно два
        # файла рядом позволяют назвать прибавку числом, а не на глаз.
        VYHOD = os.path.join(OUT, 'tp-spisok-po-kompaniyam-vsyo.csv')
        KARTA = os.path.join(OUT, 'tp-inn-company-id-vsyo.csv')
    if '--spisok' in sys.argv:
        put = sys.argv[sys.argv.index('--spisok') + 1]
        celi = [{'inn': x.strip(), 'predpriyatie': ''}
                for x in open(put, encoding='utf-8') if x.strip()]
    else:
        celi = [{'inn': r['inn'], 'predpriyatie': r.get('predpriyatie') or ''}
                for r in chitat(OCHERED)]

    # Докачка: уже пройденные ИНН пропускаем. Карта ИНН → company_id ведётся отдельно, чтобы
    # не спрашивать каталог второй раз и чтобы было видно, кого на площадке нет вовсе.
    karta = {r['inn']: r for r in chitat(KARTA)}
    proydeno = {r['inn'] for r in chitat(VYHOD)}
    celi = [c for c in celi if c['inn'] not in proydeno and c['inn'] not in karta][:predel]
    print(f'предприятий к обходу: {len(celi)} (уже пройдено {len(proydeno | set(karta))})',
          file=sys.stderr)
    if not celi:
        return

    novyy_v = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    novyy_k = not os.path.exists(KARTA) or os.path.getsize(KARTA) == 0
    fv = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    fk = open(KARTA, 'a', encoding='utf-8-sig', newline='')
    wk = csv.DictWriter(fk, fieldnames=['inn', 'predpriyatie', 'company_id', 'company_na_ploshchadke',
                                        'tenderov', 'pochemu'], delimiter=';',
                        extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    lock = threading.Lock()
    sch = {'нашлось на площадке': 0, 'нет на площадке': 0, 'тендеров': 0, 'филиалов': 0,
           'чужих строк': 0, 'сбоев': 0}

    def odna(c):
        try:
            nashli = T.company_id_po_inn(c['inn'])
        except Exception as e:  # noqa: BLE001
            return c, None, [], 0, f'сбой каталога: {type(e).__name__}'
        if not nashli:
            return c, None, [], 0, 'в каталоге площадки нет'
        cid, nazv = nashli[0]
        try:
            rows, stranic, _ = T.spisok_kompanii(cid, SLOVA, predel=PREDEL_STRANIC, pauza=1.2)
            chuzhih = 0
            for r in rows:
                if r['company_id'] == str(cid):
                    r['chya_zakupka'] = 'её собственная'
                elif obshchee_slovo(r['company'], nazv) or obshchee_slovo(r['company'],
                                                                          c['predpriyatie']):
                    r['chya_zakupka'] = 'филиал того же предприятия, ИНН у него свой'
                else:
                    r['chya_zakupka'] = 'ЧУЖАЯ КОМПАНИЯ, не приписывать'
                    chuzhih += 1
        except Exception as e:  # noqa: BLE001
            return c, (cid, nazv), [], 0, f'сбой обхода: {type(e).__name__}'
        # Обрезка по потолку страниц ДОЛЖНА быть видна в журнале. Без этого «взято 3 000»
        # читается как «у компании 3 000 закупок», хотя их может быть 170 000, и второй проход
        # никто не назначит, потому что повода не увидит.
        return c, (cid, nazv), rows, chuzhih, ('выдача обрезана потолком страниц'
                                               if stranic >= PREDEL_STRANIC else '')

    # ЗАПИСЬ ПО МЕРЕ ГОТОВНОСТИ, а не по порядку. `pool.map` отдаёт результаты В ПОРЯДКЕ ВХОДА:
    # пока не досчитана первая компания, не пишется ничего. На словарном обходе это было
    # незаметно (компания считалась за секунды), а без словаря первая же крупная берёт до 400
    # страниц — полчаса прогона дали НОЛЬ строк в файле, и выглядело это как зависание.
    # Третья сессия писала ровно об этом: любой прогон длиннее десяти минут должен писать потоком.
    with ThreadPoolExecutor(max_workers=threads) as pool:
        zadachi = {pool.submit(odna, c): c for c in celi}
        for i, gotovo in enumerate(as_completed(zadachi), 1):
            c, comp, rows, chuzhih, err = gotovo.result()
            with lock:
                if comp is None:
                    sch['сбоев' if 'сбой' in err else 'нет на площадке'] += 1
                    wk.writerow({'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                                 'company_id': '', 'company_na_ploshchadke': '',
                                 'tenderov': 0, 'pochemu': err})
                else:
                    cid, nazv = comp
                    sch['нашлось на площадке'] += 1
                    sch['тендеров'] += len(rows)
                    sch['чужих строк'] += chuzhih
                    sch['филиалов'] += sum(1 for r in rows
                                           if r.get('chya_zakupka', '').startswith('филиал'))
                    wk.writerow({'inn': c['inn'], 'predpriyatie': c['predpriyatie'],
                                 'company_id': cid, 'company_na_ploshchadke': nazv[:80],
                                 'tenderov': len(rows), 'pochemu': err or 'обойдено'})
                    for r in rows:
                        wv.writerow({**r, 'inn': c['inn'],
                                     'predpriyatie': c['predpriyatie']})
                fv.flush()
                fk.flush()
                if i % 5 == 0:
                    print(f'  {i}/{len(celi)}: {sch}', file=sys.stderr, flush=True)
            time.sleep(0.3)

    fv.close()
    fk.close()
    print(f'готово: {sch}', file=sys.stderr)
    if sch['чужих строк']:
        print('ВНИМАНИЕ: в выдаче встретились чужие компании — сужение потекло, проверить адрес',
              file=sys.stderr)
    print(f'→ {VYHOD}\n→ {KARTA}', file=sys.stderr)


if __name__ == '__main__':
    main()
