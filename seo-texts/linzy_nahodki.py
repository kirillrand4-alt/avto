# -*- coding: utf-8 -*-
"""Проверка находок на опровержение: провайдер судит, а файлы для него открывает код.

Зачем именно так, а не агентами. Задача «прогнать N находок через один и тот же вопрос» —
это скрипт, а не агент: думать по-разному тут не нужно, нужен один и тот же скептический
разбор N раз. Агент оправдан там, где надо самому решать, куда идти дальше: разведать
неизвестный источник, отладить парсер, понять, почему прогон падает.

Единственная причина, по которой раньше проверку отдавали агенту, — провайдер не умеет
открывать файлы. Она снимается разделением труда: **пути и числа код читает сам** (находка
обязана их назвать), а провайдер получает уже готовые выдержки и судит по ним.

Вход — JSON со списком находок вида:
    {"napravlenie": "eis", "nahodki": [{"zagolovok": ..., "chto": ..., "dokazatelstvo": ...,
      "obekt_zamera": ..., "znamenatel": ..., "fajly": ["путь", ...]}]}

Использование:
    python3 linzy_nahodki.py nahodki.json verdikty.json [--threads 8]
"""
import csv
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import gen_provider as G

MODEL = 'claude-fable-5'
BAZA = os.path.dirname(os.path.abspath(__file__))
KOREN = os.path.dirname(BAZA)


def _env():
    key = os.environ.get('PROVIDER_API_KEY')
    if not key:
        sys.exit('нет PROVIDER_API_KEY в окружении')
    return {'PROVIDER_API_KEY': key,
            'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')}


G.env = _env

PUT = re.compile(r'[\w./\-]+\.(?:csv|md|json|py|txt|html|sqlite|log)')


def vydержka(put, predel=6000):
    """Выдержка из файла для судьи. Для CSV — шапка, три строки и **число строк**, потому что
    самый частый брак в находках — цифра из счётчика прогона вместо цифры из файла."""
    p = put if os.path.isabs(put) else os.path.join(KOREN, put)
    if not os.path.exists(p):
        p2 = os.path.join(BAZA, put)
        if os.path.exists(p2):
            p = p2
        else:
            return f'ФАЙЛА НЕТ: {put}'
    try:
        if p.endswith('.csv'):
            with open(p, encoding='utf-8-sig', errors='replace') as f:
                stroki = f.read().split('\n')
            n = len([s for s in stroki if s.strip()])
            golova = '\n'.join(stroki[:4])
            return (f'{put}: строк с данными {max(0, n - 1)} (без шапки), байт '
                    f'{os.path.getsize(p)}\nпервые строки:\n{golova[:predel]}')
        t = open(p, encoding='utf-8', errors='replace').read()
        return f'{put}: байт {os.path.getsize(p)}\n{t[:predel]}'
    except Exception as e:  # noqa: BLE001
        return f'{put}: не прочитан ({type(e).__name__}: {e})'


VOPROS = """Ты независимый скептик. Твоя задача — ОПРОВЕРГНУТЬ находку, а не подтвердить её.
По умолчанию ставь `ustoyalo: false`: ложное подтверждение дороже пропуска, потому что по
подтверждённой находке потратят день работы и позвонят живому человеку.

КОНТЕКСТ. ООО «Руспром» продаёт промышленные воздушные центробежные компрессоры и
воздуходувки. Нужен человек в технической роли на предприятии-цели: главный инженер, главный
механик, главный энергетик, начальник компрессорной. Телефон важнее почты.

НАХОДКА:
- заголовок: {zagolovok}
- что утверждается: {chto}
- доказательство автора: {dokazatelstvo}
- что именно измерено: {obekt_zamera}
- знаменатель: {znamenatel}

ВЫДЕРЖКИ ИЗ ФАЙЛОВ, на которые ссылается находка (открыты кодом, не автором):
{vydержki}

ПРОВЕРЬ ПО ПОРЯДКУ:
1. **Совпадают ли числа находки с числами из выдержек.** Это главный вид брака: цифра берётся
   из счётчика прогона, а счётчик не знает про дедуп. У соседней сессии «231 сматчено»
   оказалось 209 в базе. Если файла нет вовсе — находка недостоверна.
2. **Не шире ли вывод, чем замер.** Мерил поле карточки — а написал «площадка не даёт»?
   Мерил одну страницу — а написал «реестр закрыт»? Этот класс за сутки дал четыре отмены
   наших выводов, он самый дорогой.
3. **Если утверждается ноль или «не работает»** — правило проекта: **ноль по умолчанию
   считается неисправностью инструмента, пока не доказано обратное**. За двое суток «пусто»
   больше десяти раз оказывалось своей ошибкой и ни разу не оказалось пустым источником.
   Требуй доказательства, что инструмент был жив: искомое слово есть в ответе, контрольная
   бессмыслица даёт ноль, осмысленный запрос даёт не ноль.
4. **Если это телефон или ФИО** — проверь, что номер взят из входного текста, что это не ИНН,
   не десять цифр из координат векторной графики PDF (в прошлом прогоне так набралось 3 815
   ложных номеров) и не телефон агентства, ведущего закупки за предприятие.
5. **Двойной счёт**: не посчитаны ли строки там, где надо считать людей или компании.

ОТВЕТ — строго JSON без пояснений:
{{"ustoyalo": true|false, "pochemu": "коротко и по делу",
  "chto_ne_sxoditsya": "число находки против числа из файла, если расходятся",
  "vyvod_shire_zamera": true|false,
  "kak_dopravit": "как переформулировать вывод, чтобы он был равен замеру"}}
"""


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: linzy_nahodki.py <nahodki.json> <verdikty.json> [--threads 8]')
    src, out = sys.argv[1], sys.argv[2]
    threads = int(sys.argv[sys.argv.index('--threads') + 1]) if '--threads' in sys.argv else 8
    dannye = json.load(open(src, encoding='utf-8'))
    if isinstance(dannye, dict):
        dannye = [dannye]

    zadaniya = []
    for blok in dannye:
        napr = blok.get('napravlenie') or blok.get('key') or ''
        obshie = blok.get('fajly') or []
        for f in blok.get('nahodki') or []:
            puti = list(dict.fromkeys((f.get('fajly') or [])
                                      + PUT.findall(f.get('dokazatelstvo') or '')
                                      + PUT.findall(f.get('chto') or '')
                                      + obshie))[:5]
            zadaniya.append((napr, f, puti))
    print(f'находок к проверке: {len(zadaniya)}', file=sys.stderr)

    client = G.make_client()
    lock = threading.Lock()
    itog = []

    def odna(z):
        napr, f, puti = z
        vyd = '\n\n'.join(vydержka(p) for p in puti) or 'файлы в находке не названы — это дефект'
        telo = VOPROS.format(zagolovok=f.get('zagolovok', ''), chto=f.get('chto', ''),
                             dokazatelstvo=f.get('dokazatelstvo', ''),
                             obekt_zamera=f.get('obekt_zamera', ''),
                             znamenatel=f.get('znamenatel') or 'НЕ УКАЗАН, это само по себе дефект',
                             vydержki=vyd[:60000])
        try:
            o = G.call(client, [{'role': 'user', 'content': telo}], model=MODEL, attempts=5)
            txt = ''.join(b.text for b in o.content if b.type == 'text').strip()
            m = re.search(r'\{.*\}', txt, re.S)
            v = json.loads(m.group(0)) if m else {'ustoyalo': False,
                                                  'pochemu': 'судья не отдал JSON'}
        except Exception as e:  # noqa: BLE001
            v = {'ustoyalo': False, 'pochemu': f'сбой судьи: {type(e).__name__}: {str(e)[:80]}'}
        return {'napravlenie': napr, 'nahodka': f, 'puti': puti, 'verdikt': v}

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, r in enumerate(pool.map(odna, zadaniya), 1):
            with lock:
                itog.append(r)
                if i % 10 == 0:
                    print(f'  {i}/{len(zadaniya)}', file=sys.stderr, flush=True)

    json.dump(itog, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ust = sum(1 for r in itog if (r['verdikt'] or {}).get('ustoyalo'))
    shire = sum(1 for r in itog if (r['verdikt'] or {}).get('vyvod_shire_zamera'))
    print(f'готово: устояло {ust} из {len(itog)}, вывод шире замера у {shire} → {out}',
          file=sys.stderr)


if __name__ == '__main__':
    main()
