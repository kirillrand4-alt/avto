# -*- coding: utf-8 -*-
r"""Мейеровские компании без сайта: домен их собственной почты — в начало очереди.

Владелец 29.08: «поставь зенке на разбор в первую очередь мейровские сайты с
доменов их почт которые не разбирали».

ЗАЧЕМ. Платный поиск XMLRiver по мейеровскому списку отработан до конца, и всё
равно у 13 549 компаний направления сайта нет вовсе. При этом у многих есть
почта на СОБСТВЕННОМ домене: `info@zavod.ru` — это и есть адрес сайта, за
который мы платили поиском. Даровая подсказка, которой ни разу не
воспользовались по мейеру.

ЧЕМ ЭТО ОПАСНО И КАК СТРАХУЕМСЯ. Домен из почты — подсказка слабая: у малого
юрлица почта живёт на портале администрации, на сервисе отчётности (тензор,
сбис, диадок) или на домене холдинга. Обойти такой сайт — собрать паспорт
ЧУЖОГО предприятия, ровно та беда, которую гейт атрибуции вычищает на выходе.
Поэтому отсекаем: бесплатные ящики, площадки (ploshchadki), служебные домены,
домены, уже закреплённые за другой компанией, и домены, встречающиеся у
нескольких ИНН сразу. Логика взята из проверенного `_domeny_iz_pocht.py`,
добавлена мейеровская выборка и порог по числу ИНН на домен.

ЧТО ПИШЕМ, КРОМЕ ОЧЕРЕДИ. Ставим `cand_site` в карточку — без него гейт слива
не признает страницы «своими» и находки уйдут в отсев «сайт компании
неизвестен». Каждая правка пишется в журнал на сервере (переживает откат
песочницы), чтобы её можно было разобрать обратно.

В НАЧАЛО, А НЕ В КОНЕЦ. В очереди больше десяти тысяч строк, и дописанное в
хвост Зенка увидит через полсуток. Переписываем файл целиком: наши строки
первыми, дальше прежние. Замена атомарная (os.replace), читатель видит либо
старый файл, либо новый.

    python meyer_sayty_po_pochte.py              посчитать, ничего не трогая
    python meyer_sayty_po_pochte.py --delat      поставить в начало очереди
"""
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender\server')

ZENNO = os.environ.get('ZENNO_OBMEN', r'C:\seostat\drop\zenno')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЖУРНАЛ = r'C:\sender\server\meyer-sayty-po-pochte.jsonl'
ПОРОГ_ИНН_НА_ДОМЕН = 2      # домен у стольких ИНН и более — общий, не берём

FREEMAIL = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru',
            'inbox.ru', 'rambler.ru', 'internet.ru', 'mail.com', 'icloud.com',
            'outlook.com', 'hotmail.com', 'yahoo.com', 'vk.com', 'narod.ru',
            'nm.ru', 'mail.ua', 'ukr.net', 'yandex.com', 'googlemail.com'}
СЛУЖЕБНЫЙ = re.compile(
    r'(^|\.)(gov|gosuslugi|nalog|tensor|sbis|kontur|diadoc|taxcom|astral|'
    r'bashneft|mechel|rzd|rosneft|gazprom|lukoil|sberbank|vtb|beget|reg|nic|'
    r'timeweb|masterhost|jino|hostland|rambler)\.', re.I)


def _журнал(запись):
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        f.write(json.dumps(запись, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _домен(строка):
    d = re.sub(r'^https?://', '', str(строка or '').strip().lower()).split('/')[0]
    return d[4:] if d.startswith('www.') else d


def кандидаты():
    try:
        import ploshchadki as PL
        площадка = PL.из_списка
    except Exception:  # noqa: BLE001
        def площадка(u):
            return ''
    отдано = set()
    try:
        with open(os.path.join(ZENNO, 'otdano.txt'), encoding='utf-8',
                  errors='replace') as f:
            отдано = {s.strip() for s in f if s.strip()}
    except OSError:
        pass
    try:
        обойдено = {n.split('.')[0] for n in os.listdir(KESH)
                    if n.endswith('.json.gz')}
    except OSError:
        обойдено = set()

    e = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True,
                        timeout=60)
    занятые = set()
    for (u,) in e.execute("select coalesce(site,'') from companies "
                          "where coalesce(site,'')<>'' union "
                          "select coalesce(cand_site,'') from companies "
                          "where coalesce(cand_site,'')<>''"):
        d = _домен(u)
        if d:
            занятые.add(d)
    # сколько РАЗНЫХ ИНН держат почту на домене: два и больше — это провайдер,
    # холдинг или общий ящик группы, и «сайтом» такой домен назвать нельзя
    домен_инн = {}
    for inn, дом in e.execute(
            "select inn, lower(substr(email, instr(email,'@')+1)) from emails "
            "where coalesce(email,'')<>''"):
        домен_инн.setdefault(дом.strip(), set()).add(str(inn))

    итог = {'мейер_без_сайта': 0, 'кандидатов': 0, 'уже_обойдены': 0,
            'уже_отдавали': 0, 'только_freemail': 0, 'площадки': 0,
            'служебные': 0, 'домен_уже_чей_то': 0, 'домен_у_многих_инн': 0}
    строки = []
    for inn, дома in e.execute(
            "select e.inn, group_concat(distinct lower(substr(e.email,"
            "instr(e.email,'@')+1))) from emails e join companies k on k.inn=e.inn "
            "where coalesce(k.division,'') like '%meyer%' "
            "and coalesce(k.site,'')='' and coalesce(k.cand_site,'')='' "
            "and coalesce(e.email,'')<>'' group by e.inn"):
        inn = str(inn)
        итог['мейер_без_сайта'] += 1
        if inn in обойдено:
            итог['уже_обойдены'] += 1
            continue
        if inn in отдано:
            итог['уже_отдавали'] += 1
            continue
        выбор = ''
        for d in (дома or '').split(','):
            d = d.strip()
            if not d or '.' not in d or d in FREEMAIL:
                continue
            if площадка(d):
                итог['площадки'] += 1
                continue
            if СЛУЖЕБНЫЙ.search(d):
                итог['служебные'] += 1
                continue
            if d in занятые:
                итог['домен_уже_чей_то'] += 1
                continue
            if len(домен_инн.get(d, ())) >= ПОРОГ_ИНН_НА_ДОМЕН:
                итог['домен_у_многих_инн'] += 1
                continue
            выбор = d
            break
        if not выбор:
            итог['только_freemail'] += 1
            continue
        итог['кандидатов'] += 1
        строки.append((inn, выбор))
    e.close()
    итог['примеры'] = строки[:8]
    return строки, итог


def поставить(строки):
    """Наши строки — первыми в очереди, прежние следом. Замена атомарная."""
    путь = os.path.join(ZENNO, 'ochered.txt')
    было = []
    наши_инн = {inn for inn, _ in строки}
    try:
        with open(путь, encoding='utf-8', errors='replace') as f:
            for s in f:
                s = s.strip()
                if s and s.split(';')[0].strip() not in наши_инн:
                    было.append(s)
    except OSError:
        pass
    новые = ['%s;%s;oba' % (inn, дом) for inn, дом in строки]
    врем = путь + '.new'
    with open(врем, 'w', encoding='utf-8') as f:
        f.write('\n'.join(новые + было) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(врем, путь)
    with open(os.path.join(ZENNO, 'otdano.txt'), 'a', encoding='utf-8') as f:
        f.write('\n'.join(наши_инн) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return {'поставлено_первыми': len(новые), 'прежних_строк': len(было)}


def проставить_cand_site(строки):
    """cand_site в карточку — иначе гейт слива не признает страницы своими."""
    c = sqlite3.connect(ENRICH, timeout=60)
    c.execute('PRAGMA busy_timeout=180000')
    легло = занято = 0
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
    for i, (inn, дом) in enumerate(строки):
        try:
            c.execute("update companies set cand_site=?, updated_at=? "
                      "where inn=? and coalesce(site,'')='' "
                      "and coalesce(cand_site,'')=''", (дом, сейчас, inn))
            легло += c.total_changes and 1 or 0
        except sqlite3.OperationalError:
            занято += 1
        if i % 200 == 0:
            c.commit()
            time.sleep(0.5)
    c.commit()
    всего = c.execute(
        "select count(*) from companies where coalesce(division,'') like '%meyer%' "
        "and coalesce(cand_site,'')<>''").fetchone()[0]
    c.close()
    return {'обновлено_карточек': легло, 'не_легло_база_занята': занято,
            'мейер_с_cand_site_теперь': всего}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    строки, итог = кандидаты()
    if '--delat' in sys.argv[1:] and строки:
        итог['карточки'] = проставить_cand_site(строки)
        итог['очередь'] = поставить(строки)
        _журнал({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'ИТОГ': итог,
                 'пары': [{'inn': i, 'domen': d} for i, d in строки]})
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
