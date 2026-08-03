# -*- coding: utf-8 -*-
"""Разобрать провайдером марки, которых не знает справочник семейств.

ОТКУДА ЗАДАЧА. Словарь марок (`slovar_modeley.py`) опознал справочником 424
обозначения из 8 592, встреченных в фактах. Остальные 8 168 — тёмная зона: там
и настоящие семейства, которых у нас нет (их надо добавить в справочник), и
мусор, который вообще не машина. Разница между ними стоит дорого в обе стороны:
пропущенное семейство теряет предприятия, а мусор, принятый за машину,
раздаёт ложные «есть».

ГЛАВНАЯ ЛОВУШКА, из-за которой этот проход вообще нужен. В нефтехимии
позиционные обозначения выглядят как марки: К-101 это КОЛОННА, Н-11 — НАСОС,
Е-205 — ЁМКОСТЬ, Т-102 — ТЕПЛООБМЕННИК, П-1 — ПЕЧЬ. Третья сессия на этом уже
обожглась: `ПК-1/2/3` с 257 упоминаниями раздали вердикт «газ» по всей базе.
Поэтому позиционные обозначения — отдельный ответ, а не «не знаю».

ЧТО ОТДАЁМ НА ВХОД. Только само обозначение и частоту. Ни названия завода, ни
текста заключения: по названию модель начнёт угадывать («раз химия, значит
центробежный»), а нам нужен разбор ОБОЗНАЧЕНИЯ. Проверка тем же приёмом, что и
везде: ответ «центробежный» принимается только с названным признаком.

Ничего не заливает. Выход — CSV на дроп плюс список кандидатов в семейства,
который потом руками (и вторым проходом) превращается в правила справочника.

DURABILITY: ответы пишутся в jsonl с fsync пачками, прогон резюмируемый.

Запуск: python slovar_neopoznannyh.py [--verh 400] [--pachka 25]
"""
import csv
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter

ДРОП = r'C:\seostat\drop\drop-storage'
ВХОД = 'SLOVAR-MODELEY-1s-NEOPOZNANNYE.csv'
ЖУРНАЛ = r'C:\sender\server\slovar_neopoznannyh.jsonl'
ВЫХОД = 'SLOVAR-MODELEY-1s-RAZOBRANO-PROVAYDEROM.csv'
КЛЮЧ = os.environ.get('PROVIDER_API_KEY', '')
БАЗА_API = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
МОДЕЛЬ = 'gemini-3.6-flash'

ОТВЕТЫ = ('центробежный воздушный', 'центробежный газовый или технологический',
          'поршневой', 'винтовой', 'воздуходувка Рутса или вихревая',
          'вентилятор или дымосос', 'позиционное обозначение установки',
          'не компрессор (другое оборудование)', 'не знаю')

ЗАДАНИЕ = (
    'Ты разбираешь обозначения оборудования, выдернутые из российских '
    'промышленных документов (заключения экспертизы промбезопасности, '
    'закупки). Скажи по КАЖДОМУ обозначению, что это.\n\n'
    'Возможные ответы поля "chto":\n'
    + '\n'.join(f'  "{о}"' for о in ОТВЕТЫ) + '\n\n'
    'ВАЖНО ПРО ПОЗИЦИОННЫЕ ОБОЗНАЧЕНИЯ. На НПЗ и в химии аппараты нумеруют по '
    'схеме установки: К-101 колонна, Н-11 насос, Е-205 ёмкость, Т-102 '
    'теплообменник, П-1 печь, С-100 сепаратор, Х-5 холодильник. Такие '
    'обозначения НЕ являются марками машин — отвечай "позиционное обозначение '
    'установки". Голые числа ("100", "220", "1,2") — тоже.\n\n'
    'ЖЁСТКОЕ ПРАВИЛО: «не знаю» лучше догадки. Ответ про компрессор '
    'принимается ТОЛЬКО с признаком: назови в поле "priznak" семейство или '
    'производителя (например "серия ТВ, турбовоздуходувка" или "Aerzen, '
    'воздуходувка"). Нет признака — пиши "не знаю".\n\n'
    'Ответ — СТРОГО JSON: {"otvety":[{"n":1,"chto":"...","priznak":"..."}]}. '
    'Никакого текста вокруг.\n\nОБОЗНАЧЕНИЯ:\n')


def арг(имя, поум):
    try:
        return int(sys.argv[sys.argv.index(имя) + 1])
    except (ValueError, IndexError):
        return поум


def _чат(промпт, максимум=3000):
    тело = json.dumps({'model': МОДЕЛЬ, 'max_tokens': максимум,
                       'messages': [{'role': 'user', 'content': промпт}]},
                      ensure_ascii=False).encode('utf-8')
    зпр = urllib.request.Request(
        БАЗА_API + '/v1/chat/completions', data=тело, method='POST',
        headers={'Authorization': 'Bearer ' + КЛЮЧ,
                 'Content-Type': 'application/json',
                 'User-Agent': 'curl/8.5.0'})
    with urllib.request.urlopen(зпр, timeout=300) as о:
        д = json.loads(о.read().decode('utf-8', 'replace'))
    return д['choices'][0]['message']['content'] or ''


def _джейсон(текст):
    м = re.search(r'\{.*\}', текст or '', re.S)
    if not м:
        return {}
    for попытка in (м.group(0), re.sub(r',\s*([}\]])', r'\1', м.group(0))):
        try:
            return json.loads(попытка)
        except Exception:  # noqa: BLE001
            continue
    return {}


def сделанные():
    из = {}
    if os.path.exists(ЖУРНАЛ):
        for стр in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(стр)
            except Exception:  # noqa: BLE001
                continue
            if з.get('marka'):
                из[з['marka']] = з
    return из


def main():
    if not КЛЮЧ:
        raise SystemExit('нет PROVIDER_API_KEY')
    ВЕРХ, ПАЧКА = арг('--verh', 400), арг('--pachka', 25)
    csv.field_size_limit(10 ** 7)
    путь = os.path.join(ДРОП, ВХОД)
    if not os.path.exists(путь):
        raise SystemExit(f'нет {ВХОД} на дропе — сначала slovar_modeley.py')
    все = []
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            все.append({'marka': (r.get('marka') or '').strip(),
                        'predpriyatiy': int(r.get('predpriyatiy') or 0),
                        'upominaniy': int(r.get('upominaniy') or 0)})
    все.sort(key=lambda с: (-с['predpriyatiy'], -с['upominaniy']))
    верх = все[:ВЕРХ]
    было = сделанные()
    осталось = [с for с in верх if с['marka'] not in было]
    print(f'неопознанных всего: {len(все)}; берём верх по предприятиям: '
          f'{len(верх)}; уже разобрано: {len(верх) - len(осталось)}; '
          f'в этот прогон: {len(осталось)}')
    sys.stdout.flush()

    итог = Counter()
    for н in range(0, len(осталось), ПАЧКА):
        пачка = осталось[н:н + ПАЧКА]
        текст = '\n'.join(
            f'{i + 1}. {с["marka"]}  (встречается у {с["predpriyatiy"]} предприятий)'
            for i, с in enumerate(пачка))
        try:
            ответ = _джейсон(_чат(ЗАДАНИЕ + текст))
        except Exception as e:  # noqa: BLE001
            print(f'  пачка {н // ПАЧКА + 1}: {type(e).__name__} {str(e)[:90]}')
            time.sleep(3)
            continue
        по_номеру = {int(o.get('n') or 0): o for o in (ответ.get('otvety') or [])
                     if str(o.get('n') or '').isdigit()}
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            for i, с in enumerate(пачка):
                o = по_номеру.get(i + 1) or {}
                что = (o.get('chto') or 'ошибка разбора').strip()
                признак = (o.get('priznak') or '').strip()
                # ответ про компрессор без признака не принимаем
                if что not in ОТВЕТЫ or (
                        'центробежн' in что and len(признак) < 4):
                    что = 'не знаю'
                итог[что] += 1
                ж.write(json.dumps({**с, 'chto': что, 'priznak': признак[:120],
                                    'ts': int(time.time())},
                                   ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())
        print(f'  пачка {н // ПАЧКА + 1}: разобрано {len(пачка)}, '
              f'воздушных центробежных всего '
              f'{итог.get("центробежный воздушный", 0)}')
        sys.stdout.flush()

    все_ответы = сделанные()
    итог_всего = Counter(з['chto'] for з in все_ответы.values())
    print(json.dumps({'разобрано_всего': len(все_ответы),
                      'разбивка': итог_всего.most_common()},
                     ensure_ascii=False, indent=1))
    наши = sorted((з for з in все_ответы.values()
                   if з['chto'] == 'центробежный воздушный'),
                  key=lambda з: -з['predpriyatiy'])
    print(f'\nКАНДИДАТЫ В СЕМЕЙСТВА СПРАВОЧНИКА ({len(наши)}):')
    for з in наши[:40]:
        print(f"  {з['marka']:24} {з['predpriyatiy']:4} предпр. — {з['priznak'][:60]}")

    строки = sorted(все_ответы.values(),
                    key=lambda з: (-з['predpriyatiy'], з['marka']))
    import io
    б = io.StringIO()
    в = csv.DictWriter(б, fieldnames=['marka', 'predpriyatiy', 'upominaniy',
                                      'chto', 'priznak', 'ts'],
                       delimiter=';', lineterminator='\n', extrasaction='ignore')
    в.writeheader()
    в.writerows(строки)
    данные = b'\xef\xbb\xbf' + б.getvalue().encode('utf-8')
    п = os.path.join(r'C:\sender\server', ВЫХОД)
    with open(п, 'wb') as ф:
        ф.write(данные)
        ф.flush()
        os.fsync(ф.fileno())
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ВЫХОД, data=данные, method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'\nна дропе: {ВЫХОД} ({len(строки)} строк)')
    except Exception as e:  # noqa: BLE001
        print(f'\nне ушёл на дроп: {str(e)[:90]}')


if __name__ == '__main__':
    main()
