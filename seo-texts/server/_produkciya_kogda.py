# -*- coding: utf-8 -*-
r"""Когда заполняется «продукция» и держится ли она после нового обхода.

Вопрос владельца 20.08 — про надёжность признака, по которому мы считаем
паспорт полным. Проверяем три вещи по фактам, а не по устройству кода:

  1. доля паспортов с пустой «продукцией» — и что у них при этом заполнено
     (пустое поле промпт разрешает: «пустое лучше правдоподобного»);
  2. сколько паспортов УСТАРЕЛО — страницы в кэше свежее самого паспорта,
     то есть Зенка привезла новые разделы после разбора;
  3. переразбирает ли их цикл на самом деле — гоняем отбор компаний так же,
     как это делает fakty_cikl, и смотрим, попадают ли туда устаревшие.
"""
import gzip
import json
import os
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
KESH = r'C:\seostat\drop\pagecache'
BD = r'C:\sender\enrich.db'
ПОЛЯ = ('оборудование_линии', 'сырьё', 'мощности', 'энергохозяйство', 'газы',
        'упаковка_фасовка', 'контроль_качества', 'экспорт', 'клиенты',
        'расширение', 'новости', 'масштаб', 'география_поставок')
итог = {}

c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True, timeout=60)
c.row_factory = sqlite3.Row
ст = {'паспортов': 0, 'продукция_есть': 0, 'продукция_пуста': 0,
      'пуста_но_есть_другое': 0, 'пуст_весь_паспорт': 0}
времена, пустые_примеры, пустые_инн = {}, [], []
для_счёта_строк = []
for r in c.execute("select inn, facts_json f, coalesce(ts,'') ts from site_facts "
                   "where coalesce(facts_json,'')<>'' and coalesce(format,0)>=2"):
    ст['паспортов'] += 1
    времена[str(r['inn'])] = r['ts']
    try:
        д = json.loads(r['f'])
    except Exception:  # noqa: BLE001
        continue
    прод = д.get('продукция') or []
    if прод:
        ст['продукция_есть'] += 1
        для_счёта_строк.append(len(прод))
        continue
    ст['продукция_пуста'] += 1
    пустые_инн.append(str(r['inn']))
    другое = [п for п in ПОЛЯ if д.get(п)]
    if другое:
        ст['пуста_но_есть_другое'] += 1
        if len(пустые_примеры) < 5:
            пустые_примеры.append({'инн': str(r['inn']), 'заполнено': другое[:5],
                                   'уверенность': д.get('уверенность')})
    else:
        ст['пуст_весь_паспорт'] += 1
c.close()
ст['строк_продукции_в_среднем'] = (
    round(sum(для_счёта_строк) / max(1, len(для_счёта_строк)), 1))
итог['паспорта'] = ст
итог['примеры_пустой_продукции'] = пустые_примеры


def _мтайм(inn):
    try:
        return os.path.getmtime(os.path.join(KESH, inn + '.json.gz'))
    except OSError:
        return None


def _вр(ts):
    import time
    try:
        return time.mktime(time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S'))
    except Exception:  # noqa: BLE001
        return None


# 2. Устаревшие: страницы свежее паспорта.
устарело = устарело_пустых = 0
пустых_множество = set(пустые_инн)
for inn, ts in времена.items():
    м, п = _мтайм(inn), _вр(ts)
    if м is None or п is None:
        continue
    if м > п + 60:
        устарело += 1
        if inn in пустых_множество:
            устарело_пустых += 1
итог['устарело'] = {'паспортов_старше_страниц': устарело,
                    'из_них_с_пустой_продукцией': устарело_пустых}

# 3. Отбор компаний ровно как в цикле фактов — попадают ли туда устаревшие.
try:
    import site_facts as SF
    c2 = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True, timeout=60)
    import time as _t
    готовые = {str(x[0]) for x in c2.execute(
        "select inn from site_facts where coalesce(popytok,0) >= 3 "
        "or coalesce(otlozheno_do,0) > ? "
        "or (coalesce(facts_json,'')<>'' and coalesce(format,0) >= ?)",
        (_t.time(), SF.FORMAT))}
    свежесть = {str(x[0]): SF._vremya_pasporta(x[1]) for x in c2.execute(
        "select inn, coalesce(ts,'') from site_facts where coalesce(facts_json,'')<>''")}
    c2.close()
    сырьё = SF._iz_kesha(200, готовые, свежесть)
    после = [k for k in сырьё if k['inn'] not in готовые]
    итог['отбор_цикла'] = {
        'вернул__iz_kesha': len(сырьё),
        'из_них_с_готовым_паспортом': sum(1 for k in сырьё if k['inn'] in готовые),
        'осталось_после_фильтра_вызывающего': len(после),
    }
except Exception as e:  # noqa: BLE001
    итог['отбор_цикла'] = {'ошибка': str(e)[:200]}


# 4. Сколько страниц было в кэше у пустых — бедный обход или нечего сказать.
def страниц(inn):
    п = os.path.join(KESH, inn + '.json.gz')
    try:
        with gzip.open(п, 'rt', encoding='utf-8', errors='replace') as f:
            д = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(д, dict):
        д = д.get('stranicy') or д.get('pages') or list(д.values())
    return len(д) if isinstance(д, list) else None


проба = пустые_инн[:150]
цифры = [n for n in (страниц(i) for i in проба) if n is not None]
итог['страниц_у_пустых'] = {
    'проверено': len(цифры),
    'в_среднем': round(sum(цифры) / max(1, len(цифры)), 1),
    'одна_страница_или_меньше': sum(1 for n in цифры if n <= 1),
}
print(json.dumps(итог, ensure_ascii=False, indent=1))
