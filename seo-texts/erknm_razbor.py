# -*- coding: utf-8 -*-
"""Разбор надзорных записей ЕРКНМ через провайдера: машина, заключение, суть.

Зачем. В остром срезе 1 262 записи по промышленной безопасности, и в тексте некоторых
лежит именно то, ради чего всё собиралось: **марка машины, инвентарный номер и ссылка на
заключение ЭПБ**. Так была найдена связка на НЛМК — предостережение от 05.06.2026 прямо
цитирует заключение от 26.05.2026 по турбокомпрессору К-3000-61-1.

Регуляркой это не берётся: формулировки у каждого управления свои, номер заключения
пишется десятком способов, а «турбокомпрессор К-3000-61-1 CTN №4, инв. №77981» надо
разложить на марку, позицию и номер.

Модель обязана отвечать пустым полем, когда данных нет: выдуманный номер заключения хуже
пропуска, потому что по нему пойдут искать.

Использование:
    python3 erknm_razbor.py <erknm-ostryy-srez.csv> <out.csv> [--batch 12] [--threads 15]
"""
import csv
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import gen_provider as G

MODEL = 'claude-fable-5'


def _env():
    key = os.environ.get('PROVIDER_API_KEY')
    if not key:
        sys.exit('нет PROVIDER_API_KEY в окружении')
    return {'PROVIDER_API_KEY': key,
            'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}


G.env = _env

SISTEMA = """Тебе дают тексты записей из Единого реестра контрольных (надзорных)
мероприятий: предостережения, решения о проверке, профилактические визиты в отношении
российских промышленных предприятий.

Нас интересует одно: упоминается ли в записи **конкретное техническое устройство** и
**заключение экспертизы промышленной безопасности**.

По каждой записи верни:
- oborudovanie: что за машина названа в тексте — дословно, вместе с маркой и номерами
  («турбокомпрессор К-3000-61-1 CTN №4, инв. №77981»). Пусто, если машина не названа.
- marka: только обозначение модели, если оно есть («К-3000-61-1»). Иначе пусто.
- nomer_zaklyucheniya: регистрационный номер заключения ЭПБ, если он в тексте
  («48-ТУ-845161-2026»). Иначе пусто.
- sut: одной строкой, в чём суть претензии надзора. Пусто, если претензии нет.
- kompressor: «да», если названная машина — компрессор, нагнетатель, воздуходувка или
  турбокомпрессор; «нет» в остальных случаях; пусто, если машина не названа.

Правила, нарушать нельзя:
1. **Пустое поле лучше догадки.** Выдуманный номер заключения хуже пропуска: по нему
   пойдут искать и потратят время. Не достраивай номера и марки по образцу.
2. Не пересказывай текст в поле `oborudovanie` — переноси дословно тот фрагмент, где
   названо устройство.
3. Большинство записей не про оборудование вовсе (пожарный надзор, экология, лицензии).
   Для них все поля пустые, и это нормальный ответ.
4. Никаких пояснений вне JSON.

Ответ — строго JSON-массив объектов с полями n, oborudovanie, marka, nomer_zaklyucheniya,
sut, kompressor, где n — номер записи из входа."""


def razbor(client, chunk):
    lines = []
    for i, t in chunk:
        lines.append(f'--- запись {i}\n{t}')
    out = G.call(client, [{'role': 'user', 'content': SISTEMA + '\n\nЗаписи:\n'
                           + '\n'.join(lines)}], model=MODEL)
    txt = ''.join(b.text for b in out.content if b.type == 'text').strip()
    i, j = txt.find('['), txt.rfind(']')
    if i < 0 or j < 0:
        raise ValueError('нет JSON-массива: ' + txt[:150])
    return json.loads(txt[i:j + 1])


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: erknm_razbor.py <in.csv> <out.csv> [--batch N] [--threads N]')
    src, out_path = sys.argv[1], sys.argv[2]
    batch = int(sys.argv[sys.argv.index('--batch') + 1]) if '--batch' in sys.argv else 12
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 15

    src_rows = list(csv.DictReader(open(src, encoding='utf-8-sig'), delimiter=';'))
    zapisi = [(i, (r.get('tekst') or '')[:1200]) for i, r in enumerate(src_rows)
              if (r.get('tekst') or '').strip()]
    print(f'записей к разбору: {len(zapisi)}, потоков {threads}', file=sys.stderr)

    client = G.make_client()
    cols = ['inn', 'zakazchik', 'data_nachala', 'vid_nadzora', 'oborudovanie', 'marka',
            'nomer_zaklyucheniya', 'kompressor', 'sut', 'erpid']
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
    w.writeheader()

    chunks = [zapisi[k:k + batch] for k in range(0, len(zapisi), batch)]

    def rabota(nc):
        nomer, chunk = nc
        try:
            return nomer, chunk, razbor(client, chunk)
        except Exception as e:  # noqa: BLE001
            print(f'  партия {nomer}: ОШИБКА {e}', file=sys.stderr)
            return nomer, chunk, []

    done, nashli, lock = 0, 0, threading.Lock()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for nomer, chunk, res in pool.map(rabota, enumerate(chunks, 1)):
            by = {}
            for r in res:
                if isinstance(r, dict):
                    try:
                        by[int(r.get('n'))] = r
                    except (TypeError, ValueError):
                        pass
            with lock:
                for i, _ in chunk:
                    r = by.get(i) or {}
                    src_r = src_rows[i]
                    if not (r.get('oborudovanie') or r.get('nomer_zaklyucheniya')):
                        continue          # пустые записи не пишем — их большинство
                    w.writerow({'inn': src_r.get('inn', ''),
                                'zakazchik': src_r.get('zakazchik', ''),
                                'data_nachala': src_r.get('data_nachala', ''),
                                'vid_nadzora': src_r.get('vid_nadzora', ''),
                                'oborudovanie': r.get('oborudovanie', ''),
                                'marka': r.get('marka', ''),
                                'nomer_zaklyucheniya': r.get('nomer_zaklyucheniya', ''),
                                'kompressor': r.get('kompressor', ''),
                                'sut': r.get('sut', ''),
                                'erpid': src_r.get('erpid', '')})
                    nashli += 1
                done += len(chunk)
                f.flush()
            print(f'  партия {nomer}/{len(chunks)}: разобрано {done}, с оборудованием '
                  f'{nashli}', file=sys.stderr)
    f.close()
    print(f'итого записей с оборудованием: {nashli} из {done} → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
