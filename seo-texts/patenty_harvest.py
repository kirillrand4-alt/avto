# -*- coding: utf-8 -*-
"""Патенты предприятий из нашего списка: ФИО изобретателей с привязкой к юрлицу.

Зачем. Патент — один из немногих открытых документов, где **ФИО стоит рядом с названием
предприятия** и обе стороны проверяемы. Ограничение известно заранее: изобретатель мог
уволиться, а патент остаться, поэтому ценность падает с возрастом документа.

Почему заново. Прошлый заход упёрся в HTTP 503 Google Patents, и нули по шести компаниям
были объявлены **недостоверными** — по правилу «ноль почти всегда своя ошибка». Здесь взят
другой вход: `patents.google.com/xhr/query`, он отдаёт JSON и из песочницы работает.

ЗАПРОС БЫЛ СЛОВОМ «КОМПРЕССОР», И ЭТО ОБНУЛЯЛО ВЫДАЧУ. Замер 03.08 на живом эндпоинте:

    «БЕЛЗАН компрессор»               ->   0
    «БЕЛЗАН»                          ->  14
    «Белебеевский завод Автонормаль»  -> 135
    «КАЗАНЬОРГСИНТЕЗ»                 -> 121

Завод патентует своё производство, а не компрессоры, которые покупает. Нам от патента
нужно не оборудование, а ФАМИЛИЯ инженера рядом с названием предприятия — значит искать
надо по имени предприятия и ничего к нему не приписывать. Оператор `assignee:` этот вход
не понимает (отдаёт 0), поэтому выдача полнотекстовая и заявителя приходится сверять
самим — колонка `zayavitel_nash`. Чужие патенты с упоминанием НЕ выбрасываются: это тоже
связь, только слабее.

Выдача постраничная по 10, страница задаётся `&page=N` внутри параметра `url`. Без этого
у предприятия со 135 патентами забиралось десять.

Использование:
    python3 patenty_harvest.py <predpriyatiya.csv> <out.csv> [--limit 40] [--pauza 4]
                               [--stranic 5]

Входной CSV: колонки `inn_zakazchika` и `zakazchik`.
"""
import collections
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def chistoe_imya(s):
    """Из «ПАО "КАЗАНЬОРГСИНТЕЗ"» сделать поисковую строку без формы и кавычек."""
    s = re.sub(r'\((?:ИНН|инн)[^)]*\)', ' ', s)
    s = re.sub(r'[«»"\']', ' ', s)
    s = re.sub(r'\b(ПАО|ОАО|АО|ООО|ЗАО|НАО|ПУБЛИЧНОЕ|АКЦИОНЕРНОЕ|ОБЩЕСТВО|С|ОГРАНИЧЕННОЙ|'
               r'ОТВЕТСТВЕННОСТЬЮ)\b', ' ', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip()


def svoy_zayavitel(imya, zayavitel):
    """Патент этого предприятия или просто упоминание его в чужом тексте.

    Сверяю по СЛОВАМ имени длиннее четырёх букв: «Белебеевский завод Автонормаль» против
    «Открытое акционерное общество "Белебеевский завод "Автонормаль"» совпадает по трём
    словам из трёх, а тот же запрос в патенте Института РАН — ни по одному.
    """
    z = (zayavitel or '').lower()
    slova = [w for w in re.split(r'[^А-Яа-яЁёA-Za-z0-9]+', imya.lower()) if len(w) > 4]
    if not slova:
        return False
    return sum(1 for w in slova if w in z) >= max(1, len(slova) // 2)


def zapros(text, pauza, popytok=3, stranica=0):
    zap = 'q=' + text + (f'&page={stranica}' if stranica else '')
    url = ('https://patents.google.com/xhr/query?url='
           + urllib.parse.quote(zap) + '&exp=')
    req = urllib.request.Request(url, headers={'User-Agent': UA,
                                               'Accept': 'application/json'})
    for p in range(popytok):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception as e:  # noqa: BLE001
            # 503 — то, на чём прошлый заход остановился и записал ложные нули.
            # Здесь он не повод для вывода, а повод подождать подольше.
            print(f'    попытка {p + 1}: {type(e).__name__} {e}', file=sys.stderr)
            time.sleep(pauza * (p + 2))
    return None


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: patenty_harvest.py <predpriyatiya.csv> <out.csv> '
                 '[--limit N] [--pauza SEC]')
    src, out_path = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 40
    pauza = float(sys.argv[sys.argv.index('--pauza') + 1]) if '--pauza' in sys.argv else 4.0

    cnt = collections.Counter()
    imena = {}
    for r in csv.DictReader(open(src, encoding='utf-8-sig'), delimiter=';'):
        i = (r.get('inn_zakazchika') or '').strip()
        if i:
            cnt[i] += 1
            imena[i] = (r.get('zakazchik') or '').strip()
    top = [i for i, _ in cnt.most_common(limit)]
    print(f'предприятий к обходу: {len(top)}, пауза {pauza} с', file=sys.stderr)

    stranic = int(sys.argv[sys.argv.index('--stranic') + 1]) if '--stranic' in sys.argv else 5
    cols = ['inn', 'predpriyatie', 'zapros', 'vsego_naydeno', 'stranica', 'nomer', 'data',
            'nazvanie', 'zayavitel', 'zayavitel_nash', 'izobretateli']
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()

    vsego, sboev, nulevyh = 0, 0, 0
    for k, inn in enumerate(top, 1):
        name = chistoe_imya(imena[inn])
        q = name
        vzyato, total, stranica, sboy = 0, 0, 0, False
        while stranica < stranic:
            d = zapros(q, pauza, stranica=stranica)
            if d is None:
                sboy = True
                break
            res = (d.get('results') or {})
            if stranica == 0:
                total = res.get('total_num_results', 0)
            items = []
            for cl in res.get('cluster', []):
                items.extend(cl.get('result', []))
            if not items:
                break
            for it in items:
                p = it.get('patent', {})
                zay = p.get('assignee') or ''
                # Выдача полнотекстовая: по запросу «КАЗАНЬОРГСИНТЕЗ» приходят и патенты
                # Института РАН, где название просто упомянуто. Заявителя сверяю с именем
                # предприятия и результат ПОМЕЧАЮ, а не отбрасываю: упоминание в чужом
                # патенте — тоже связь, только слабее, и решать по ней должен человек.
                svoy = '1' if svoy_zayavitel(name, zay) else ''
                w.writerow({'inn': inn, 'predpriyatie': imena[inn], 'zapros': q,
                            'vsego_naydeno': total, 'stranica': stranica,
                            'nomer': p.get('publication_number', ''),
                            'data': p.get('publication_date', ''),
                            'nazvanie': (p.get('title') or '')[:200],
                            'zayavitel': zay[:160],
                            'zayavitel_nash': svoy,
                            'izobretateli': (p.get('inventor') or '')[:300]})
                vzyato += 1
            stranica += 1
            # Лишняя страница — это лишний 503. Счётчик выдачи известен с первой страницы,
            # поэтому за него не ходим: у предприятия с 8 патентами вторая страница только
            # жжёт лимит и рождает ложный «сбой».
            if vzyato >= total:
                break
            time.sleep(pauza)
        f.flush()
        if sboy:
            sboev += 1
            print(f'[{k}/{len(top)}] {name[:34]:<34} НЕ ОТВЕТИЛ на стр. {stranica} — '
                  f'это не ноль, а сбой (взято до сбоя {vzyato})', file=sys.stderr)
        else:
            if not vzyato:
                nulevyh += 1
            print(f'[{k}/{len(top)}] {name[:34]:<34} счётчик {total:>5}, взято {vzyato:>3}, '
                  f'всего {vsego + vzyato}', file=sys.stderr)
        vsego += vzyato
        time.sleep(pauza)
    f.close()
    # Ноль и сбой печатаются РАЗДЕЛЬНО. Прошлый заход слил их в одно и записал в отчёт
    # шесть ложных нулей от HTTP 503.
    print(f'итого {vsego} строк | предприятий без единого патента {nulevyh} | '
          f'СБОЕВ (ноль недостоверен) {sboev} → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
