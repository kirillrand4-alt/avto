# -*- coding: utf-8 -*-
"""Перепросить провайдером строки ЭПБ, где принцип машины не назван словом.

ЗАЧЕМ. Гейт центробежности при доливке реестра ЭПБ отсеял 2 267 строк с
причиной «центробежность не названа»: в тексте заключения стоит просто
«компрессор» без указания принципа. Часть из них — наши машины, просто эксперт
не написал слова. Регулярка тут бессильна: она знает семейства К-250, ЦК, ВЦ,
ТВ, но не знает импортных и заводских обозначений вроде `VK32-3EX`,
`4VRZ 151/405/08G`, `GA-425/7`.

ПОЧЕМУ МОДЕЛЬ, А НЕ СПИСОК. Обозначений тысячи, и новые появляются каждый год.
Модель отвечает по строению обозначения и по смыслу описания, а мы проверяем
её ответ тем же арбитром, что и всё остальное: если она сказала «центробежный»,
но не смогла назвать ни признака, ни производителя — не верим.

ЧТО ОТДАЁМ НА ВХОД. Только текст объекта из заключения, без подсказок про
предприятие: иначе модель начнёт угадывать по названию завода («раз химия,
значит центробежный»), а нам нужен разбор ОБОЗНАЧЕНИЯ.

Модель — `gemini-3.6-flash` по таблице владельца от 02.08: разбор свободного
текста, самая дешёвая. Судейство тут не нужно, спорные уходят в «не знаю».

DURABILITY: ответы пишутся в jsonl с fsync пачками, прогон резюмируемый по
номеру пачки. Результат — CSV на дроп; в панель ничего не заливает.

Запуск: python epb_perepros.py [--pachek N] [--razmer N]
"""
import csv
import json
import os
import re
import sys
import time
import urllib.request

КЛЮЧ = os.environ.get('PROVIDER_API_KEY', '')
БАЗА_API = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
МОДЕЛЬ = 'gemini-3.6-flash'
ДРОП = r'C:\seostat\drop\drop-storage'
ФАЙЛ = 'OTSEV-EPB-1-sessiya.csv'
ЖУРНАЛ = r'C:\sender\server\epb_perepros.jsonl'
ВЫХОД = 'EPB-pereprosheno-centrobezhnye.csv'
ПРИЧИНА = 'центробежность не названа'


def арг(имя, поум):
    try:
        return int(sys.argv[sys.argv.index(имя) + 1])
    except (ValueError, IndexError):
        return поум


ПАЧЕК = арг('--pachek', 8)
РАЗМЕР = арг('--razmer', 25)

ЗАДАНИЕ = (
    'Ты разбираешь обозначения промышленных компрессоров из заключений '
    'экспертизы промышленной безопасности. По КАЖДОЙ строке определи ПРИНЦИП '
    'действия машины.\n\n'
    'Возможные ответы поля "tip":\n'
    '  "центробежный" — динамический компрессор, турбокомпрессор, '
    'турбовоздуходувка, нагнетатель центробежного типа (К-250, ЦК, 32ВЦ, ТВ, '
    'Centac, Atlas Copco ZH, Elliott, Siemens STC, Aerzen TB, HIBON, Neuros);\n'
    '  "поршневой" — поршневой или оппозитный (ВМ, ВП, ПК, 4ВМ10, 2ВМ4, ЗИФ);\n'
    '  "винтовой" — винтовой (ВК, GA, ZR, Remeza, Kaeser);\n'
    '  "воздуходувка Рутса или вихревая" — объёмная, не центробежная;\n'
    '  "не компрессор" — насос, вентилятор, турбина, сосуд, трубопровод;\n'
    '  "не знаю" — если по тексту принцип определить нельзя.\n\n'
    'ЖЁСТКОЕ ПРАВИЛО: «не знаю» — нормальный ответ, и он лучше догадки. '
    'Отвечай "центробежный" ТОЛЬКО если можешь назвать признак: узнаваемое '
    'семейство обозначения либо прямое слово в тексте. В поле "pochemu" '
    'напиши этот признак одной короткой фразой.\n\n'
    'Ответ — СТРОГО JSON: {"otvety":[{"n":1,"tip":"...","pochemu":"..."}]}. '
    'Никакого текста вокруг.\n\nСТРОКИ:\n')


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
    return (д['choices'][0]['message']['content'] or '')


def _джейсон(текст):
    м = re.search(r'\{.*\}', текст or '', re.S)
    if not м:
        return {}
    try:
        return json.loads(м.group(0))
    except Exception:  # noqa: BLE001
        try:
            return json.loads(re.sub(r',\s*([}\]])', r'\1', м.group(0)))
        except Exception:  # noqa: BLE001
            return {}


def сделанные():
    из = set()
    if os.path.exists(ЖУРНАЛ):
        for стр in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(стр)
            except Exception:  # noqa: BLE001
                continue
            if з.get('kluch'):
                из.add(з['kluch'])
    return из


def main():
    if not КЛЮЧ:
        raise SystemExit('нет PROVIDER_API_KEY')
    csv.field_size_limit(10 ** 7)
    путь = os.path.join(ДРОП, ФАЙЛ)
    if not os.path.exists(путь):
        raise SystemExit(f'нет {ФАЙЛ} на дропе')
    строки = []
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            if (r.get('prichina_otseva') or '').strip() != ПРИЧИНА:
                continue
            об = (r.get('obekt') or '').strip()
            if len(об) < 10:
                continue
            строки.append({'inn': (r.get('inn') or '').strip(),
                           'predpriyatie': (r.get('predpriyatie') or '').strip(),
                           'obekt': об})
    было = сделанные()
    осталось = [с for с in строки
                if f"{с['inn']}|{с['obekt'][:80]}" not in было]
    print(f'строк с причиной «{ПРИЧИНА}»: {len(строки)}; '
          f'уже разобрано: {len(строки) - len(осталось)}; '
          f'в этот прогон: {min(len(осталось), ПАЧЕК * РАЗМЕР)}')
    sys.stdout.flush()

    итог = {'центробежный': 0, 'поршневой': 0, 'винтовой': 0,
            'воздуходувка Рутса или вихревая': 0, 'не компрессор': 0,
            'не знаю': 0, 'ошибка разбора': 0}
    найдено = []
    for н in range(ПАЧЕК):
        пачка = осталось[н * РАЗМЕР:(н + 1) * РАЗМЕР]
        if not пачка:
            break
        текст = '\n'.join(f'{i + 1}. {с["obekt"][:220]}'
                          for i, с in enumerate(пачка))
        try:
            ответ = _джейсон(_чат(ЗАДАНИЕ + текст))
        except Exception as e:  # noqa: BLE001
            print(f'  пачка {н + 1}: {type(e).__name__} {str(e)[:90]}')
            continue
        по_номеру = {int(o.get('n') or 0): o
                     for o in (ответ.get('otvety') or [])
                     if str(o.get('n') or '').isdigit()}
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            for i, с in enumerate(пачка):
                o = по_номеру.get(i + 1) or {}
                тип = (o.get('tip') or 'ошибка разбора').strip()
                итог[тип] = итог.get(тип, 0) + 1
                зап = {'kluch': f"{с['inn']}|{с['obekt'][:80]}",
                       'inn': с['inn'], 'obekt': с['obekt'][:300],
                       'tip': тип, 'pochemu': (o.get('pochemu') or '')[:160],
                       'ts': int(time.time())}
                ж.write(json.dumps(зап, ensure_ascii=False) + '\n')
                if тип == 'центробежный':
                    найдено.append({**зап, 'predpriyatie': с['predpriyatie']})
            ж.flush()
            os.fsync(ж.fileno())
        print(f'  пачка {н + 1}/{ПАЧЕК}: разобрано {len(пачка)}, '
              f'центробежных всего {итог.get("центробежный", 0)}')
        sys.stdout.flush()

    print(json.dumps({'итог_по_типам': итог,
                      'НАЙДЕНО_ЦЕНТРОБЕЖНЫХ': len(найдено)},
                     ensure_ascii=False, indent=1))
    for с in найдено[:12]:
        print(f'  {с["inn"]} {с["obekt"][:70]} — {с["pochemu"][:50]}')

    if not найдено:
        return
    п = os.path.join(r'C:\sender\server', ВЫХОД)
    новый = not os.path.exists(п)
    with open(п, 'a', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        if новый:
            в.writerow(['inn', 'predpriyatie', 'obekt', 'pochemu'])
        for с in найдено:
            в.writerow([с['inn'], с.get('predpriyatie', ''), с['obekt'],
                        с['pochemu']])
    try:
        урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
        urllib.request.urlopen(urllib.request.Request(
            урл.rstrip('/') + '/' + ВЫХОД, data=open(п, 'rb').read(),
            method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
            timeout=300).read()
        print(f'на дропе: {ВЫХОД}')
    except Exception as e:  # noqa: BLE001
        print(f'файл не ушёл на дроп: {e}')


if __name__ == '__main__':
    main()
