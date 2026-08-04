# -*- coding: utf-8 -*-
"""Кому принадлежит домен — спросить у самого домена: ИНН в подвале.

ПОЧЕМУ НЕ СХОДСТВО ИМЕНИ. Весы «название против домена» дали 34 строки из 72,
где не отозвался никто либо отозвались оба: `fankom.ru` у «Свеза Верхняя
Синячиха» — настоящий сайт завода, но на имя не похож, а `sibur.ru` у «КЗСК»
похож на холдинг, которому завод принадлежит, и всё равно не его сайт. Весы
такое не решают, и выдавать их за решение нельзя.

РЕШАЮЩИЙ ПРИЗНАК. Российские сайты печатают реквизиты в подвале и на странице
контактов. Если на домене найден ИМЕННО ЭТОТ ИНН — принадлежность доказана
самим источником, а не нашим сопоставлением. Это то же правило, по которому мы
всю смену отличаем «рядом на странице» от «сказано на странице».

ЧТО ЗАСЧИТЫВАЕТСЯ, ПО УБЫВАНИЮ ВЕСА
    ИНН найден            принадлежит, вопрос закрыт
    ОГРН найден           то же самое (ОГРН уникален не хуже)
    название найдено      сильный намёк, но не доказательство: холдинг тоже
                          называет свои заводы
    молчит / не открылся  ничего не доказано; «не открылся» — это молчание
                          прибора, и оно НЕ равно «не принадлежит»

Ходим обычным HTTP; кто не отдал — уходит в список для браузерного ходока, а не
в приговор. Запись в durable-поток на каждый домен, чтобы рестарт не стёр труд.

Запуск: python sayty_po_innu.py [--vse] [--potok N]
"""
import io, json, os, re, sqlite3, ssl, sys, time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

P25 = r'C:\seostat\data\p25.db'
ПОТОК = r'C:\seostat\drop\sayty_dokazatelstvo_inn.jsonl'
ВСЕ = '--vse' in sys.argv
ПОТОКОВ = 8
for i, а in enumerate(sys.argv):
    if а == '--potok' and i + 1 < len(sys.argv):
        ПОТОКОВ = max(1, min(16, int(sys.argv[i + 1])))

ПУТИ = ('', '/contacts', '/kontakty', '/kontakti', '/about', '/o-kompanii',
        '/company', '/rekvizity')
_КТХ = ssl.create_default_context()
_КТХ.check_hostname = False
_КТХ.verify_mode = ssl.CERT_NONE
_ЗАГ = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9'}


def домен(з):
    д = str(з or '').strip().lower()
    д = re.sub(r'^https?://', '', д)
    д = re.sub(r'^www\.', '', д).split('/')[0].split('?')[0].strip()
    return д if re.match(r'^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$', д) else ''


def взять(url, таймаут=12):
    зпр = urllib.request.Request(url, headers=_ЗАГ)
    with urllib.request.urlopen(зпр, timeout=таймаут, context=_КТХ) as о:
        сыр = о.read(600000)
    for код in ('utf-8', 'cp1251'):
        try:
            return сыр.decode(код)
        except UnicodeDecodeError:
            continue
    return сыр.decode('utf-8', 'replace')


def ядро_имени(имя):
    м = re.search(r'[«"]([^»"]{2,})[»"]', str(имя or ''))
    сырое = м.group(1) if м else re.sub(r'^(?:ООО|ОАО|ЗАО|ПАО|АО|НАО|ФГУП|ГУП|'
                                        r'МУП|НПО|НПП)\s+', '', str(имя or ''))
    сл = [с for с in re.findall(r'[А-Яа-яЁё]{4,}', сырое)]
    return сл[:3]


def опросить(з):
    """Один домен: что он сам про себя говорит."""
    д, инн, огрн, имя = з['domen'], з['inn'], з['ogrn'], з['predpriyatie']
    ядра = ядро_имени(имя)
    итог = {'domen': д, 'inn': инн, 'stranic': 0, 'inn_nayden': 0,
            'ogrn_nayden': 0, 'imya_naydeno': 0, 'oshibka': ''}
    текст = ''
    for сх in ('https://', 'http://'):
        for путь in ПУТИ:
            try:
                стр = взять(f'{сх}{д}{путь}')
            except Exception as e:
                if not путь and сх == 'http://':
                    итог['oshibka'] = type(e).__name__
                continue
            итог['stranic'] += 1
            текст += ' ' + стр
            if len(текст) > 1500000:
                break
        if итог['stranic']:
            break
    if not итог['stranic']:
        итог['oshibka'] = итог['oshibka'] or 'не открылся'
        return итог
    цифры = re.sub(r'[^0-9]', ' ', re.sub(r'<[^>]+>', ' ', текст))
    цифры = ' ' + re.sub(r'\s+', ' ', цифры) + ' '
    итог['inn_nayden'] = 1 if инн and f' {инн} ' in цифры else 0
    итог['ogrn_nayden'] = 1 if огрн and f' {огрн} ' in цифры else 0
    низ = текст.lower()
    итог['imya_naydeno'] = 1 if ядра and all(я.lower() in низ for я in ядра[:1]) else 0
    return итог


def main():
    db = EDB.EnrichDB()
    чеко, огрны = {}, {}
    поля_e = {r[1] for r in db.cx.execute('PRAGMA table_info(companies)')}
    for и, с in db.cx.execute("SELECT inn, COALESCE(site_checko,'') FROM companies"):
        д = домен(с)
        if д:
            чеко[str(и)] = д
    if 'ogrn' in поля_e:
        for и, о in db.cx.execute("SELECT inn, COALESCE(ogrn,'') FROM companies"):
            if str(о).strip():
                огрны[str(и)] = re.sub(r'\D', '', str(о))

    цб = sqlite3.connect(f'file:{P25}?mode=ro', uri=True)
    поля = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
    есть_огрн = 'ogrn' in поля
    задачи = []
    for р in цб.execute("SELECT inn, COALESCE(sayt,''), COALESCE(predpriyatie,'')" +
                        (', COALESCE(ogrn,\'\')' if есть_огрн else ", ''") +
                        ' FROM company'):
        и, наш, имя, огрн = str(р[0]), домен(р[1]), str(р[2]), re.sub(r'\D', '', str(р[3]))
        ч = чеко.get(и, '')
        огрн = огрн or огрны.get(и, '')
        спор = наш and ч and наш != ч
        if not (спор or (ВСЕ and (наш or ч))):
            continue
        for д in {x for x in (наш, ч) if x}:
            задачи.append({'domen': д, 'inn': и, 'ogrn': огрн,
                           'predpriyatie': имя, 'nash': int(д == наш),
                           'cheko': int(д == ч)})
    цб.close()

    сделано = set()
    if os.path.exists(ПОТОК):
        for стр in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(стр)
            except Exception:
                continue
            сделано.add((str(з.get('inn')), str(з.get('domen'))))
    очередь = [з for з in задачи if (з['inn'], з['domen']) not in сделано]
    print(f'доменов к опросу {len(очередь)} (уже опрошено {len(сделано)})')

    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    стат = Counter()
    готово = 0
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        for исх, з in zip(пул.map(опросить, очередь), очередь):
            готово += 1
            зп = {**исх, 'nash': з['nash'], 'cheko': з['cheko'],
                  'predpriyatie': з['predpriyatie'][:60],
                  'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}
            ф.write(json.dumps(зп, ensure_ascii=False) + '\n')
            ф.flush()
            os.fsync(ф.fileno())
            чей = 'наш' if з['nash'] else 'чеко'
            if исх['inn_nayden']:
                стат[f'{чей}: ИНН НАЙДЕН — принадлежность доказана'] += 1
            elif исх['ogrn_nayden']:
                стат[f'{чей}: ОГРН найден — принадлежность доказана'] += 1
            elif исх['imya_naydeno']:
                стат[f'{чей}: только название — намёк, не доказательство'] += 1
            elif исх['stranic']:
                стат[f'{чей}: открылся, но реквизитов нет'] += 1
            else:
                стат[f'{чей}: не открылся ({исх["oshibka"]})'] += 1
    ф.close()

    print()
    for к, v in sorted(стат.items()):
        print(f'   {к:56} {v:4}')
    print()
    print(f'опрошено доменов {готово}')


if __name__ == '__main__':
    main()
