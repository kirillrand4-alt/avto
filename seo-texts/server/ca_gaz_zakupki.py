# -*- coding: utf-8 -*-
r"""Шаг 2 плана PLAN_CA_O2_N2.md: закупки газа и оборудования под газ в ЕИС как сигнал (только ранжирование).

09.11, ночь (владелец: «делай всё, что можешь, параллельно»). RSS расширенного поиска ЕИС по ключам (азот, кислород,
генераторы, станции, жидкий газ, лазерные станки — сигнал для n2_lazer), 44-ФЗ и 223-ФЗ, до CA_EIS_STRANIC страниц
на ключ, запрос раз в 2 с. ИНН заказчика в RSS нет — сопоставляем название заказчика с названиями ЮЛ нашего реестра
(ca-reestr.jsonl, ca-ne-msp-kat.jsonl) после нормализации (ОПФ, кавычки, регистр). Неоднозначные имена не берём.
Выход (fsync): ca\ca-gaz-zakupki.jsonl (все извещения), ca\ca-gaz-zakupki-itog.json (+ дроп). Только чтение ЕИС.
Запуск: python ca_gaz_zakupki.py (сам в фон, низкий приоритет).
"""
import collections, html, io, json, os, re, subprocess, sys, time, urllib.parse

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'

if '--vnutri' not in sys.argv:
    os.makedirs(ПАПКА, exist_ok=True)
    лог = os.path.join(ПАПКА, 'ca_gaz_zakupki_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(30)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-900:])
    sys.exit(0)

ЗАМОК = os.path.join(ПАПКА, 'ca_gaz_zakupki.lock')
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
import enrich_contacts as EC  # noqa: E402

КЛЮЧИ = {
    'азот': ['азот газообразный', 'азот жидкий', 'поставка азота', 'генератор азота', 'азотная станция',
             'азотная установка', 'газообразный азот'],
    'кислород': ['кислород газообразный', 'кислород жидкий', 'кислород технический', 'поставка кислорода',
                 'кислородная станция', 'кислородная установка', 'концентратор кислорода', 'оксигенатор'],
    'лазер': ['станок лазерной резки', 'установка лазерной резки', 'оптоволоконный лазер'],
    'озон': ['озонатор', 'озонаторная установка'],
}
СТРАНИЦ = int(os.environ.get('CA_EIS_STRANIC', '10'))
ОПФ = [('ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ', 'ООО'), ('ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'ПАО'),
       ('НЕПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'АО'), ('ЗАКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'ЗАО'),
       ('ОТКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'ОАО'), ('АКЦИОНЕРНОЕ ОБЩЕСТВО', 'АО'),
       ('СЕЛЬСКОХОЗЯЙСТВЕННЫЙ ПРОИЗВОДСТВЕННЫЙ КООПЕРАТИВ', 'СПК'), ('ПРОИЗВОДСТВЕННЫЙ КООПЕРАТИВ', 'ПК')]


def отметка(**k):
    k['обновлено'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(ПАПКА, 'ca-gaz-zakupki-progress.json'), 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)
    print(json.dumps(k, ensure_ascii=False)[:300], flush=True)


def норм(имя):
    s = html.unescape(str(имя or '')).upper().replace('Ё', 'Е')
    for длин, кор in ОПФ:
        s = s.replace(длин, кор)
    s = re.sub(r'[«»"\'“”„]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def элементы(тело):
    out = []
    for it in re.findall(r'<item>(.*?)</item>', тело, re.S):
        def g(tag):
            м = re.search(r'<%s[^>]*>(.*?)</%s>' % (tag, tag), it, re.S)
            return html.unescape(re.sub(r'<!\[CDATA\[|\]\]>', '', м.group(1))).strip() if м else ''
        опис = re.sub(r'<[^>]+>', ' ', g('description'))
        опис = re.sub(r'\s+', ' ', опис)
        зак = re.search(r'(?:Наименование\s+)?(?:Заказчик|Организаци\w+,\s*осуществляющ\w+ размещение)\w*\s*:\s*(.+?)'
                        r'(?:\s+(?:Начальная|Размещение|Наименование объекта|Этап|Обновлено|Валюта|Цена)\b|$)', опис, re.I)
        out.append({'название': re.sub(r'\s+', ' ', g('title')), 'url': g('link'), 'дата': g('pubDate'),
                    'заказчик': зак.group(1).strip()[:300] if зак else '', 'описание': опис[:600]})
    return out


def main():
    # имена ЮЛ реестра -> ИНН (неоднозначные — вон)
    имя_инн, кат_инн = collections.defaultdict(set), {}
    for имя in ('ca-reestr.jsonl', 'ca-ne-msp-kat.jsonl'):
        п = os.path.join(ПАПКА, имя)
        if not os.path.exists(п):
            continue
        for s in io.open(п, encoding='utf-8', errors='replace'):
            try:
                r = json.loads(s)
            except ValueError:
                continue
            if r.get('тип') == 'ЮЛ' and r.get('название'):
                имя_инн[норм(r['название'])].add(str(r['инн']))
                кат_инн[str(r['инн'])] = [к for к, о in ca_cel.категории(r.get('оквэд'), r.get('оквэд_доп') or []).items()
                                         if о == 'осн']
    отметка(этап='имена', имён=len(имя_инн))
    вых = os.path.join(ПАПКА, 'ca-gaz-zakupki.jsonl')
    видел, найдено, сч = set(), collections.defaultdict(lambda: collections.defaultdict(list)), collections.Counter()
    with io.open(вых, 'w', encoding='utf-8') as f:
        for группа, кк in КЛЮЧИ.items():
            for кл in кк:
                for стр in range(1, СТРАНИЦ + 1):
                    url = ('https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString=%s&morphology=on'
                           '&sortBy=UPDATE_DATE&pageNumber=%d&recordsPerPage=_50&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on'
                           % (urllib.parse.quote(кл), стр))
                    try:
                        эл = элементы(EC._eis_get(url, timeout=40))
                    except Exception as e:  # noqa: BLE001
                        сч['ошибка'] += 1
                        отметка(этап='ключ', ключ=кл, страница=стр, ошибка=repr(e)[:150])
                        time.sleep(10)
                        break
                    if not эл:
                        break
                    for x in эл:
                        if x['url'] in видел:
                            continue
                        видел.add(x['url'])
                        иннs = имя_инн.get(норм(x['заказчик'])) or set()
                        x.update({'группа': группа, 'ключ': кл, 'inn': sorted(иннs)[0] if len(иннs) == 1 else ''})
                        f.write(json.dumps(x, ensure_ascii=False) + '\n')
                        сч['извещений'] += 1
                        if x['inn']:
                            найдено[x['inn']][группа].append({'название': x['название'][:200], 'url': x['url'], 'дата': x['дата']})
                    f.flush()
                    os.fsync(f.fileno())
                    time.sleep(2)
                отметка(этап='ключ', ключ=кл, извещений=сч['извещений'], совпало_инн=len(найдено))
    по_кат = collections.defaultdict(collections.Counter)
    for инн, гр in найдено.items():
        for к in кат_инн.get(инн) or ['вне категорий']:
            for г in гр:
                по_кат[к][г] += 1
    итог = {'дата': time.strftime('%Y-%m-%d %H:%M'), 'счётчики': dict(сч), 'компаний_с_закупкой': len(найдено),
            'по_категориям': {к: dict(v) for к, v in по_кат.items()},
            'компании': {инн: {'кат': кат_инн.get(инн), 'закупки': {г: v[:5] for г, v in гр.items()}} for инн, гр in найдено.items()}}
    п = os.path.join(ПАПКА, 'ca-gaz-zakupki-itog.json')
    with open(п, 'w', encoding='utf-8') as f:
        json.dump(итог, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    import shutil
    shutil.copyfile(п, os.path.join(ДРОП, 'ca-gaz-zakupki-itog.json'))
    отметка(этап='готово', извещений=сч['извещений'], компаний=len(найдено))


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
