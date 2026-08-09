# -*- coding: utf-8 -*-
"""Марка и тип из текста заключения ЭПБ — провайдером, там где регулярка не справилась.

ЗАЧЕМ. Мой разбор вынул марку у 16 809 строк из 20 830. Оставшиеся 4 021 — это тексты, где
обозначение либо стоит не за словом типа («Компрессор поршневой марки 4КГ, технологический
индекс КГ-4»), либо машины в строке нет вовсе («Трубопровод нагнетания воздуха ОТ
компрессоров поз. 1/1-1»). Разделить эти два случая шаблоном я не смог: оба выглядят
одинаково — слово «компрессор» есть, обозначения рядом нет.

Модель отвечает СТРОГО из текста и обязана вернуть пустое, если в тексте обозначения нет.
Выдумывать марку нельзя: марка — это то, что мы напишем клиенту про его машину.
"""
import csv, json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
VHOD = os.path.join(L, 'PARK-FAKTY-2S-EPB.csv')
VYHOD = os.path.join(L, 'PARK-MARKA-PROVAJDER-2S.jsonl')
PACHKA = int(os.environ.get('PACHKA', '25'))
NITEY = int(os.environ.get('NITEY', '4'))
PREDEL = int(os.environ.get('PREDEL', '2000'))

PROMPT = """Ты разбираешь строки реестра заключений промышленной безопасности.
Для КАЖДОЙ строки верни JSON-объект с полями:
  n            — номер строки, как дан
  est_mashina  — true, если объект экспертизы САМ является машиной (компрессор, воздуходувка,
                 генератор азота/кислорода, ВРУ, МКС); false, если это трубопровод, ёмкость,
                 арматура, здание или узел ПРИ машине
  marka        — обозначение машины ИЗ ТЕКСТА (например «4ВМ10-100/8», «ТВ-80-1,6», «GA160»).
                 Пустая строка, если обозначения в тексте НЕТ. НЕ ВЫДУМЫВАЙ и не подставляй
                 технологический индекс, инвентарный или регистрационный номер вместо марки
  zavodskoy    — заводской номер из текста, иначе пустая строка. «б/н» = пустая строка
  tip          — один из: компрессор | воздуходувка | компрессорная станция | ВРУ |
                 генератор азота | генератор кислорода | МКС | осушитель | ресивер | не машина

Отвечай ТОЛЬКО массивом JSON, без пояснений. Строки:
"""


def main():
    rows = [x for x in csv.DictReader(open(VHOD, encoding='utf-8-sig'), delimiter=';')
            if not x['marka_model'].strip()]
    gotovo = set()
    if os.path.exists(VYHOD):
        for ln in open(VYHOD, encoding='utf-8'):
            try:
                gotovo.add(json.loads(ln)['klyuch'])
            except (json.JSONDecodeError, KeyError):
                pass
    celi = [x for x in rows if (x['inn'] + '|' + x['citata'][:60]) not in gotovo][:PREDEL]
    print(f'без марки всего {len(rows)}, к разбору {len(celi)}', file=sys.stderr, flush=True)
    if not celi:
        return
    client = G.make_client()
    f = open(VYHOD, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = {'пачек': 0, 'строк': 0, 'машина': 0, 'марка найдена': 0, 'сбоев': 0}

    def pachka(i):
        kus = celi[i:i + PACHKA]
        tekst = '\n'.join(f"{n}. {x['citata']}" for n, x in enumerate(kus))
        try:
            msg = G.call(client, [{'role': 'user', 'content': PROMPT + tekst}],
                         model='claude-fable-5', attempts=4)
            # `call` возвращает объект сообщения, а не строку: текст лежит в блоках content.
            otvet = ''.join(b.text for b in msg.content if b.type == 'text') \
                if hasattr(msg, 'content') else str(msg)
        except Exception as e:  # noqa: BLE001
            with lock:
                sch['сбоев'] += 1
            print(f'  сбой пачки {i}: {str(e)[:90]}', file=sys.stderr, flush=True)
            return
        m = re.search(r'\[.*\]', otvet or '', re.S)
        try:
            dannye = json.loads(m.group(0)) if m else []
        except json.JSONDecodeError:
            dannye = []
        with lock:
            sch['пачек'] += 1
            for d in dannye:
                try:
                    x = kus[int(d.get('n', -1))]
                except (ValueError, IndexError):
                    continue
                sch['строк'] += 1
                if d.get('est_mashina'):
                    sch['машина'] += 1
                if (d.get('marka') or '').strip():
                    sch['марка найдена'] += 1
                f.write(json.dumps({'klyuch': x['inn'] + '|' + x['citata'][:60],
                                    'inn': x['inn'], 'tip_model': d.get('tip', ''),
                                    'est_mashina': bool(d.get('est_mashina')),
                                    'marka': (d.get('marka') or '').strip(),
                                    'zavodskoy': (d.get('zavodskoy') or '').strip(),
                                    'ssylka': x['ssylka'], 'citata': x['citata']},
                                   ensure_ascii=False) + '\n')
            f.flush()
            if sch['пачек'] % 5 == 0:
                print(f'  {sch}', file=sys.stderr, flush=True)

    with ThreadPoolExecutor(max_workers=NITEY) as p:
        list(p.map(pachka, range(0, len(celi), PACHKA)))
    print(f'готово: {sch}', file=sys.stderr)


main()
