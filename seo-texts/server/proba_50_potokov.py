# -*- coding: utf-8 -*-
r"""Замер на 100 карточках: луна против хайку, 50 потоков, живой расход.

Владелец 20.08: «а нельзя поставить провайдеру 50 потоков? попробуй на 100
карточках и луну и хайку и как раз увидим реальный расход».

Что здесь меряется по-настоящему, а не оценкой:
  * держит ли шлюз 50 одновременных запросов (или начнёт отказывать);
  * сколько токенов входа и выхода уходит НА САМОМ ДЕЛЕ — до этого была
    прикидка «3 знака на токен», и она могла врать в полтора раза;
  * сколько это стоит по каждой модели;
  * что получается на выходе: уверенность паспорта и заполненность полей,
    потому что дешёвая модель, дающая пустой паспорт, дороже дорогой.

Обе модели гоняются по ОДНИМ И ТЕМ ЖЕ ста компаниям — иначе сравнение
бессмысленно: карточки очень разные по объёму текста.

В site_facts НИЧЕГО НЕ ПИШЕТСЯ. Это замер, а не работа: выбор модели ещё не
сделан, и засорять базу результатом проигравшей модели незачем. Результат
ложится в jsonl на сервере с fsync — по правилу durability из CLAUDE.md,
песочница при рестарте откатывается, сервер нет.

    python proba_50_potokov.py [сколько] [потоков]
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
# gen_provider живёт в C:\sender (а не рядом с серверными скриптами) —
# site_facts находит его тем же способом, добавляя корень в sys.path.
for _p in (r'C:\sender', r'C:\sender\server', DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 100
ПОТОКОВ = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 50
ЖУРНАЛ = r'C:\sender\proba_50_potokov.jsonl'

# Ставки шлюза, доллары за миллион токенов. Луна — самая дешёвая модель,
# хайку дороже примерно в девять раз по входу и в семь по выходу.
СТАВКИ = {
    'gpt-5.6-luna': (0.11, 0.67),
    'claude-haiku-4-5': (1.00, 5.00),
}

_замок = threading.Lock()
_расход = {}


def _учесть(model, msg):
    u = getattr(msg, 'usage', None)
    вх = int(getattr(u, 'input_tokens', 0) or 0)
    вых = int(getattr(u, 'output_tokens', 0) or 0)
    чит = int(getattr(u, 'cache_read_input_tokens', 0) or 0)
    зап = int(getattr(u, 'cache_creation_input_tokens', 0) or 0)
    with _замок:
        д = _расход.setdefault(model, {'вызовов': 0, 'вход': 0, 'выход': 0,
                                       'кэш_чтений': 0, 'кэш_записей': 0})
        д['вызовов'] += 1
        д['вход'] += вх
        д['выход'] += вых
        д['кэш_чтений'] += чит
        д['кэш_записей'] += зап


def обернуть_провайдера():
    """Считать токены КАЖДОГО вызова, не трогая сам gen_provider."""
    import gen_provider as GP
    родной = GP.call

    def счётчик(client, messages, model=None, **kw):
        msg = родной(client, messages, model=model, **kw)
        try:
            _учесть(str(model or '?'), msg)
        except Exception:  # noqa: BLE001 - счётчик не имеет права ронять прогон
            pass
        return msg

    GP.call = счётчик
    return родной


def цели(сколько):
    """Компании со снятыми страницами, у которых паспорта ещё нет."""
    import sqlite3
    KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
    кэш = {n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')}
    c = sqlite3.connect('file:%s?mode=ro' % os.environ.get(
        'ENRICH_DB', r'C:\sender\enrich.db').replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    готовы = {str(r[0]) for r in c.execute('select distinct inn from site_facts')}
    надо = sorted(и for и in кэш if и.isdigit() and и not in готовы)[:сколько]
    из = []
    for кусок in [надо[i:i + 400] for i in range(0, len(надо), 400)]:
        q = ','.join('?' * len(кусок))
        for r in c.execute(
                "select inn, coalesce(name,'') name, coalesce(site,'') site "
                'from companies where inn in (%s)' % q, кусок):
            из.append({'inn': str(r['inn']), 'name': r['name'], 'site': r['site']})
    c.close()
    # компании, которых нет в companies, всё равно берём — страницы у них есть
    известные = {k['inn'] for k in из}
    из += [{'inn': и, 'name': '', 'site': ''} for и in надо if и not in известные]
    return из[:сколько]


def прогон(модель, компании, потоков):
    """Разобрать список одной моделью. В site_facts не пишем — это замер."""
    import site_facts as SF
    # Модель подменяем ПРЯМО В МОДУЛЕ, а не через reload: перезагрузка заново
    # выполнила бы весь модуль и сбросила бы состояние на середине замера.
    SF.MODEL = модель
    SF.MODEL_NOVOSTI = модель        # честное сравнение: одна модель на оба прохода
    import gen_provider as GP
    klient = GP.make_client()

    with _замок:
        _расход.pop(модель, None)
    итог = {'модель': модель, 'взято': len(компании), 'ошибок': 0,
            'уверенность': {}, 'с_продукцией': 0, 'с_новостями': 0,
            'с_оборудованием': 0, 'пустых': 0}
    t0 = time.time()

    def одна(k):
        try:
            return SF._razobrat_odnu(klient, k)
        except Exception as e:  # noqa: BLE001
            return {'inn': k['inn'], 'fakty': None, 'note': str(e)[:140]}

    строки = []
    with ThreadPoolExecutor(max_workers=потоков) as ex:
        for r in ex.map(одна, компании):
            ф = r.get('fakty') or {}
            if not ф:
                итог['ошибок'] += 1
            else:
                у = str(ф.get('уверенность') or '?')[:20]
                итог['уверенность'][у] = итог['уверенность'].get(у, 0) + 1
                итог['с_продукцией'] += bool(ф.get('продукция'))
                итог['с_новостями'] += bool(ф.get('новости'))
                итог['с_оборудованием'] += bool(ф.get('оборудование_линии'))
                if not (ф.get('продукция') or ф.get('оборудование_линии')):
                    итог['пустых'] += 1
            строки.append({'model': модель, 'inn': r.get('inn'),
                           'note': r.get('note'),
                           'polya': {к: len(ф.get(к) or []) for к in
                                     ('продукция', 'оборудование_линии',
                                      'мощности', 'новости')} if ф else None})
    итог['секунд'] = round(time.time() - t0, 1)
    итог['компаний_в_час'] = round(len(компании) * 3600 / max(1.0, итог['секунд']))
    р = dict(_расход.get(модель) or {})
    итог['токены'] = р
    вх_ст, вых_ст = СТАВКИ.get(модель, (0.0, 0.0))
    цена = р.get('вход', 0) / 1e6 * вх_ст + р.get('выход', 0) / 1e6 * вых_ст
    итог['доллара_за_прогон'] = round(цена, 4)
    на_компанию = цена / max(1, len(компании))
    итог['доллара_на_компанию'] = round(на_компанию, 6)
    итог['на_14457_долларов'] = round(на_компанию * 14457, 1)
    итог['токенов_вход_на_компанию'] = round(р.get('вход', 0) / max(1, len(компании)))
    # durable: пишем на сервер с fsync, песочница откатывается, сервер нет
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        for с in строки:
            f.write(json.dumps(с, ensure_ascii=False) + '\n')
        f.write(json.dumps({'ИТОГ': итог}, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return итог


def главное():
    обернуть_провайдера()
    компании = цели(СКОЛЬКО)
    если = {'компаний': len(компании), 'потоков': ПОТОКОВ}
    результаты = []
    for м in ('gpt-5.6-luna', 'claude-haiku-4-5'):
        результаты.append(прогон(м, компании, ПОТОКОВ))
    свод = {'условия': если, 'модели': результаты}
    print(json.dumps(свод, ensure_ascii=False, indent=1)[:5000])
    print(json.dumps({'КОРОТКО': [
        {'модель': r['модель'], 'секунд': r['секунд'],
         'компаний_в_час': r['компаний_в_час'], 'ошибок': r['ошибок'],
         'вход_на_компанию': r['токенов_вход_на_компанию'],
         'кэш_чтений': (r['токены'] or {}).get('кэш_чтений', 0),
         'за_прогон_$': r['доллара_за_прогон'],
         'на_14457_$': r['на_14457_долларов'],
         'пустых': r['пустых'], 'с_продукцией': r['с_продукцией']}
        for r in результаты]}, ensure_ascii=False))


if __name__ == '__main__':
    главное()
