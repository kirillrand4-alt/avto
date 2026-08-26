# -*- coding: utf-8 -*-
r"""Судья-провайдер по конкурентам, найденным сканом паспортов.

Скан `konkurenty_po_pasportu.py` берёт правило регулярками, а регулярка не умеет
отличить «делаем компрессоры» от «возим чужие» и «ремонтируем свои». Владелец
26.08: «прогнать 74 судьёй-провайдера — давай». Судья читает продукцию из паспорта
и отвечает одним из четырёх вердиктов:

  производитель — сам делает компрессоры/генераторы газов/фотосепараторы/рентген;
  торговец      — продаёт чужое такое же оборудование (тоже соперник по сделке);
  сервис        — только ремонт и обслуживание чужой техники;
  не_конкурент  — оборудование у него в другой роли (строит станции, покупает,
                  делает расходники), продавать ему можно.

ЧТО ПОЧЁМУ. Ответ пишем в durable-хранилище на сервере (`sudya-konkurentov.jsonl`
с fsync плюс отметка в stage_log), а НЕ только в возвращаемый JSON: песочница при
рестарте откатывается к снимку, и разбор пропал бы (урок 25.07). Прогон
резюмируемый — уже разобранные ИНН пропускаются, так что скрипт можно запускать
повторно после любого обрыва.

    python sudya_konkurentov.py            разобрать всех неразобранных
    python sudya_konkurentov.py --predel 5 разобрать пятерых (проба)
    python sudya_konkurentov.py --primenit снять стоп-лист с «не_конкурент»
"""
import json
import os
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import gen_provider as GP  # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
SND = os.environ.get('SENDER_DB', r'C:\sender\sender.db')
ЖУРНАЛ = os.path.join(os.environ.get('TEMP_DIR', r'C:\sender\_tmp'),
                      'sudya-konkurentov.jsonl')
МОДЕЛЬ = os.environ.get('SUDYA_MODEL', 'claude-fable-5')
ВЕРДИКТЫ = ('производитель', 'торговец', 'сервис', 'не_конкурент')

PROMPT = """Ты решаешь, конкурент ли эта компания для ООО «Руспром».

Руспром продаёт: промышленные компрессоры (винтовые, поршневые, воздушные),
компрессорные станции, генераторы азота и кислорода, мобильные компрессорные
станции — это направление «Компрессор Центр»; и фотосепараторы плюс оборудование
рентген-инспекции — это направление «Meyer».

Компания: %(name)s
Сайт: %(site)s
ОКВЭД: %(okved)s
Что она, по её собственному сайту, производит и продаёт:
%(produkciya)s

Выбери РОВНО один вердикт:
- "производитель" — она сама изготавливает такое же оборудование;
- "торговец" — она продаёт такое же оборудование чужого производства;
- "сервис" — она только ремонтирует и обслуживает чужую такую технику,
  своего не делает и не продаёт;
- "не_конкурент" — оборудование у неё в другой роли: она строит или монтирует
  объекты, где оно стоит, покупает его для своего производства, делает к нему
  расходники (масла, фильтры, шланги), либо совпадение случайное.

Важно: строительство и монтаж компрессорных станций — это НЕ производство
компрессоров, такая компания нам покупатель. Ремонт компрессоров — это "сервис".
Если по перечню продукции решить нельзя, ставь "не_конкурент" и низкую уверенность:
цена ошибки в одну сторону — потерянный клиент, в другую — письмо сопернику.

Ответь ТОЛЬКО JSON, без пояснений вокруг:
{"вердикт": "<один из четырёх>", "уверенность": <0.0-1.0>,
 "чем_торгует": "<что именно из нашего списка, 3-6 слов>",
 "почему": "<одно предложение со ссылкой на конкретную позицию из перечня>"}"""


def _razobrannye():
    было = {}
    if os.path.exists(ЖУРНАЛ):
        with open(ЖУРНАЛ, encoding='utf-8') as f:
            for стр in f:
                try:
                    з = json.loads(стр)
                except Exception:  # noqa: BLE001
                    continue
                if з.get('инн') and з.get('вердикт'):
                    было[str(з['инн'])] = з
    return было


def _spisok():
    """Кого судим: помеченные сканом (stage_log.stage='konk_pasport')."""
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    из = []
    for r in c.execute(
            "select k.inn, coalesce(k.name,'') name, coalesce(k.site,'') site, "
            "coalesce(k.okved,'') okved, coalesce(f.facts_json,'') fj "
            'from companies k join stage_log s on s.inn=k.inn '
            'left join site_facts f on f.inn=k.inn '
            "where s.stage='konk_pasport' and coalesce(k.is_competitor,0)=1"):
        try:
            прод = json.loads(r['fj']).get('продукция') if r['fj'] else None
        except Exception:  # noqa: BLE001
            прод = None
        if isinstance(прод, (list, tuple)):
            текст = '\n'.join('- %s' % str(x)[:200] for x in прод[:25])
        else:
            текст = str(прод or '')[:1800]
        if not текст.strip():
            continue
        из.append({'инн': str(r['inn']), 'name': r['name'][:120],
                   'site': r['site'][:80], 'okved': r['okved'][:80],
                   'produkciya': текст})
    c.close()
    return из


def _zapisat(з):
    """Durable: строка в jsonl с fsync + отметка в stage_log сервера."""
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    # Строка в jsonl уже легла с fsync — она и есть durable-запись. Отметка в
    # stage_log нужна для отчётов, поэтому ждём замок недолго: enrich.db держит
    # zenno_most, и настойчивое ожидание тут растягивало разбор одной компании
    # на полторы минуты сверх самого вызова.
    for _ in range(6):
        try:
            e = sqlite3.connect(BD, timeout=20)
            e.execute('PRAGMA busy_timeout=20000')
            e.execute('BEGIN IMMEDIATE')
            e.execute('INSERT INTO stage_log(inn, stage, detail, ts) '
                      'VALUES(?,?,?,?) ON CONFLICT(inn, stage) DO UPDATE SET '
                      'detail=excluded.detail, ts=excluded.ts',
                      (з['инн'], 'sudya_konk',
                       ('%s %.2f' % (з['вердикт'], з.get('уверенность') or 0))[:80],
                       time.strftime('%Y-%m-%dT%H:%M:%S')))
            e.commit()
            e.close()
            return True
        except sqlite3.OperationalError:
            time.sleep(2)
    return False


def sudit(predel=None):
    было = _razobrannye()
    очередь = [x for x in _spisok() if x['инн'] not in было]
    if predel:
        очередь = очередь[:predel]
    d = {'всего_помечено': len(было) + len(очередь), 'уже_разобрано': len(было),
         'в_работе': len(очередь), 'сбоев': 0, 'по_вердиктам': {}}
    клиент = GP.make_client()
    for i, x in enumerate(очередь, 1):
        сооб = [{'role': 'user', 'content': PROMPT % x}]
        try:
            # effort='low': задача — выбрать один из четырёх ярлыков по готовому
            # перечню продукции, длинные размышления тут только жгут время. Проба
            # на трёх компаниях с полным thinking шла дольше двух минут на каждую.
            ответ = GP.call(клиент, сооб, model=МОДЕЛЬ, attempts=4, effort='low')
            данные = GP.parse_json(ответ)
        except Exception as ex:  # noqa: BLE001
            d['сбоев'] += 1
            d.setdefault('последний_сбой', str(ex)[:160])
            continue
        в = str((данные or {}).get('вердикт', '')).strip().lower()
        if в not in ВЕРДИКТЫ:
            d['сбоев'] += 1
            d.setdefault('последний_сбой', 'вердикт вне списка: %r' % в)
            continue
        з = {'инн': x['инн'], 'имя': x['name'], 'сайт': x['site'],
             'вердикт': в, 'уверенность': (данные or {}).get('уверенность'),
             'чем_торгует': str((данные or {}).get('чем_торгует', ''))[:120],
             'почему': str((данные or {}).get('почему', ''))[:300],
             'модель': МОДЕЛЬ, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}
        _zapisat(з)
        d['по_вердиктам'][в] = d['по_вердиктам'].get(в, 0) + 1
        if i % 10 == 0:
            print('разобрано %d/%d' % (i, len(очередь)), file=sys.stderr)
    return d


def primenit():
    """Снять стоп-лист и флаг с тех, кого судья назвал не_конкурентом.

    Сервис не трогаем: ремонтник чужих компрессоров конкурирует с нашей сервисной
    выручкой, и это решение владельца, а не судьи.
    """
    было = _razobrannye()
    вернуть = [з for з in было.values() if з['вердикт'] == 'не_конкурент']
    d = {'разобрано': len(было), 'вернуть': len(вернуть)}
    if not вернуть:
        return d
    инны = [з['инн'] for з in вернуть]
    s = sqlite3.connect(SND, timeout=90)
    s.execute('PRAGMA busy_timeout=90000')
    # Знак процента в LIKE и %-подстановка списка ИНН в одной строке не уживаются:
    # питон принимает «%' AND» за спецификатор формата и падает. Поэтому образец
    # причины уходит параметром, а форматируется только плейсхолдерный хвост.
    s.execute('DELETE FROM suppression WHERE scope=? AND reason LIKE ? '
              'AND value IN (%s)' % ','.join('?' * len(инны)),
              ('inn', 'конкурент по паспорту%') + tuple(инны))
    s.commit()
    d['снято_из_стоп-листа'] = s.total_changes
    s.close()
    e = sqlite3.connect(BD, timeout=90)
    e.execute('PRAGMA busy_timeout=90000')
    снято = 0
    for i in range(0, len(инны), 5):
        кусок = инны[i:i + 5]
        for _ in range(40):
            try:
                e.execute('BEGIN IMMEDIATE')
                for и in кусок:
                    e.execute('UPDATE companies SET is_competitor=0 WHERE inn=?', (и,))
                e.commit()
                снято += len(кусок)
                break
            except sqlite3.OperationalError:
                try:
                    e.rollback()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(3)
    d['снят_флаг'] = снято
    d['осталось_is_competitor'] = e.execute(
        'select count(*) from companies where is_competitor=1').fetchone()[0]
    e.close()
    return d


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    предел = None
    if '--predel' in sys.argv:
        предел = int(sys.argv[sys.argv.index('--predel') + 1])
    d = {}
    if '--primenit' not in sys.argv:
        d['разбор'] = sudit(предел)
    if '--primenit' in sys.argv:
        d['применение'] = primenit()
    было = _razobrannye()
    d['итог_по_вердиктам'] = {}
    for з in было.values():
        d['итог_по_вердиктам'][з['вердикт']] = \
            d['итог_по_вердиктам'].get(з['вердикт'], 0) + 1
    d['журнал'] = ЖУРНАЛ
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
