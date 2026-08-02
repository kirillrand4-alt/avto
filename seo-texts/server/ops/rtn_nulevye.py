# -*- coding: utf-8 -*-
"""Подпись каждого «нулевого» файла РТН: график с другой раскладкой или обвязка.

424 файла прочитались, но дали ноль строк. Три взятых наугад оказались банком
вопросов тестирования, бланком заявления и образцом формы — то есть обвязкой,
которую разведка тащит вместе с графиками. Но три файла ничего не доказывают
про четыреста: среди них могут быть настоящие графики с другой раскладкой, и
тогда мы теряем главный источник технических руководителей.

Снимаем подпись со ВСЕХ: есть ли маркеры графика, сколько в тексте похожих на
ФИО троек, сколько похожих на должность слов, сколько строк с запятой — и
кусок текста вокруг первой ФИО-тройки. По подписи файл относим к типу:
  * «обвязка» — вопросы тестирования, бланк, образец, перечень, приказ;
  * «график, раскладка другая» — есть и ФИО, и должности, и организации;
  * «непонятно» — ни то, ни другое, нужен глаз.

Ничего не пишет в базу. Выгрузка кладётся на дроп файлом
RTN-nulevye-podpisi.json, чтобы разбирать её можно было и после рестарта.

Запуск: python rtn_nulevye.py [--lim N] [--потоков N] [--бюджет СЕК]
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_contacts as EC   # noqa: E402
import rtn_znaniya as RTN      # noqa: E402


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


ЛИМ = int(арг('--lim', '500'))
ПОТОКОВ = int(арг('--потоков', '10'))
БЮДЖЕТ = float(арг('--бюджет', '900'))
ВЫХОД = r'C:\sender\server\RTN-nulevye-podpisi.json'
ИМЯ_НА_ДРОПЕ = 'RTN-nulevye-podpisi.json'

_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}(?:\s+[А-ЯЁ][а-яё\-]{2,})?')
_ФИО_ИНИЦ = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.')
_ДОЛЖ = re.compile(
    r'главн\w*\s+(?:инженер|энергетик|механик|технолог)|гл\.\s*(?:инженер|энергетик|механик)|'
    r'начальник|мастер|энергетик|механик|инженер|электромонтёр|электромонтер|'
    r'директор|заместитель', re.I)
_ОРГ = re.compile(r'ООО|ОАО|ЗАО|АО\s|ПАО|МУП|ГУП|ФГУП|МБУ|ГБУ|филиал', re.I)
_ОБВЯЗКА = re.compile(
    r'вопросы\s+тестирован|перечень\s+вопрос|бланк|образец|заявление\s+о\s+проверк|'
    r'заявление\s+на\s+проверк|приказ\s+№|методическ|инструкц|положение\s+об|'
    r'форма\s+заявлен|удостоверени\w*\s+образ', re.I)
_ГРАФИК = re.compile(
    r'график\s+провер|график\s+аттестац|список\s+на\s+\d|проверк\w*\s+знани', re.I)

_замок = threading.Lock()


def тип_файла(п):
    if п['обвязка'] and п['фио'] < 8:
        return 'обвязка'
    if п['фио'] >= 8 and п['должн'] >= 5 and п['орг'] >= 3:
        return 'график, раскладка другая'
    if п['фио'] < 5:
        return 'людей в тексте почти нет'
    return 'непонятно, нужен глаз'


def main():
    нулевые = []
    for ln in io.open(RTN.П_СТРОКИ, encoding='utf-8', errors='replace'):
        try:
            d = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if not d.get('пусто') and not (d.get('строки') or []):
            у = d.get('файл') or ''
            if у and у not in нулевые:
                нулевые.append(у)
    нулевые = нулевые[:ЛИМ]
    print(f'нулевых файлов: {len(нулевые)}', flush=True)

    начало = time.time()
    итог = []
    типы = Counter()

    def один(у):
        if time.time() - начало > БЮДЖЕТ:
            return
        try:
            т = EC.doc_text(у) or ''
        except Exception as e:  # noqa: BLE001
            with _замок:
                итог.append({'url': у, 'ошибка': str(e)[:70], 'тип': 'не читается'})
                типы['не читается'] += 1
            return
        т = re.sub(r'[ \t\u00a0]+', ' ', т)
        п = {
            'url': у, 'символов': len(т),
            'фио': len(_ФИО.findall(т)) + len(_ФИО_ИНИЦ.findall(т)),
            'должн': len(_ДОЛЖ.findall(т)),
            'орг': len(_ОРГ.findall(т)),
            'обвязка': bool(_ОБВЯЗКА.search(т[:4000])),
            'маркер_графика': bool(_ГРАФИК.search(т[:4000])),
            'строк_с_запятой': sum(1 for s in т.split('\n') if ',' in s),
        }
        п['тип'] = тип_файла(п)
        м = _ФИО.search(т)
        if м:
            a = max(0, м.start() - 200)
            п['кусок'] = т[a:a + 900]
        with _замок:
            итог.append(п)
            типы[п['тип']] += 1

    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        list(пул.map(один, нулевые))

    with open(ВЫХОД, 'w', encoding='utf-8') as ф:
        json.dump(итог, ф, ensure_ascii=False)
        ф.flush()
        os.fsync(ф.fileno())
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ИМЯ_НА_ДРОПЕ,
            data=open(ВЫХОД, 'rb').read(), method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        положено = ИМЯ_НА_ДРОПЕ
    except Exception as e:  # noqa: BLE001
        положено = 'НЕ легло: ' + str(e)[:80]

    print(json.dumps({'разобрано': len(итог), 'типы': типы.most_common(),
                      'на_дропе': положено,
                      'секунд': round(time.time() - начало)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
