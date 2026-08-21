# -*- coding: utf-8 -*-
r"""Разложить телефоны со страниц по строкам и проставить роли из подписей.

Что чиним (замер 21.08):
  * у 7 047 компаний «Партии 935» номера лежат БЕЗЛИКИМ СПИСКОМ в
    companies.phones, а в phone_contacts, где есть поле роли, строк нет —
    так извлечение работало до 29.07, когда телефоны отдавались голыми
    строками и роль у номера не спрашивали;
  * осмысленной роли нет у 14 084 компаний, чьи страницы лежат в кэше, хотя
    на самих страницах роль часто написана: «Комм. отдел: +7 (8639) 26 26 98».

Что делаем: читаем страницы из кэша обхода, берём подпись слева от номера
(признак — двоеточие), прогоняем её через ТУ ЖЕ каноническую таблицу ролей,
которой пользуется провайдерский путь, и пишем через EnrichDB.add_phone —
единственную точку записи телефона, где уже стоят отсев реквизитов, канон
роли и правило «непустая роль не понижается до общей».

Провайдер не нужен: роль на странице уже написана человеком, мы её только
переносим. Где подписи нет — роль не выдумываем, кладём номер без роли.

Прогон резюмируемый: пройденные ИНН отмечаются в stage_log стадией
«phone_podpis», при перезапуске они пропускаются. Результат durable: строки
в enrich.db плюс jsonl с fsync — песочница переживёт рестарт.

    python roli_telefonov.py                 сухой прогон по всей базе
    python roli_telefonov.py --predel 500    сухой прогон по 500 компаниям
    python roli_telefonov.py --primenit      запись
"""
import json
import os
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, r'C:\sender', r'C:\sender\sender', r'C:\sender\server'):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lid_ssylka as LS  # noqa: E402
from enrich_db import EnrichDB  # noqa: E402

КЕШ = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ЖУРНАЛ = r'C:\sender\_ops\roli_telefonov.jsonl'
СТАДИЯ = 'phone_podpis'
ИСТОЧНИК = 'подпись со страницы'


def _журнал(запись):
    """Durable-след: строка с fsync. Песочница откатывается, сервер — нет."""
    try:
        os.makedirs(os.path.dirname(ЖУРНАЛ), exist_ok=True)
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            f.write(json.dumps(запись, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    except Exception:  # noqa: BLE001 - журнал не должен ронять прогон
        pass


def progon(predel=None, primenit=False):
    db = EnrichDB()
    свои = {str(r[0]) for r in db.cx.execute('select inn from companies')}
    сделано = {str(r[0]) for r in db.cx.execute(
        'select inn from stage_log where stage=?', (СТАДИЯ,))}
    файлы = [n for n in os.listdir(КЕШ) if n.endswith('.json.gz')]
    очередь = [n for n in файлы
               if n.split('.')[0] in свои and n.split('.')[0] not in сделано]
    if predel:
        очередь = очередь[:int(predel)]

    ст = {'компаний': 0, 'со_страницами': 0, 'номеров': 0, 'записано': 0,
          'с_ролью': 0, 'роль_не_общая': 0, 'уже_было': 0, 'ошибок': 0}
    роли = {}
    начало = time.time()
    for i, имя in enumerate(очередь, 1):
        инн = имя.split('.')[0]
        ст['компаний'] += 1
        try:
            страницы = LS._stranicy_kesha(инн)
            if not страницы:
                if primenit:
                    db.mark_stage(инн, СТАДИЯ, 'страниц нет')
                continue
            ст['со_страницами'] += 1
            найдено = (LS._kontakty_so_stranic(страницы) or {}).get('tel') or {}
            for ключ, узел in найдено.items():
                ст['номеров'] += 1
                подпись = (узел.get('podpisi') or [''])[0]
                канон = EnrichDB._canon_role(подпись) if подпись else ''
                if канон == 'общий':
                    канон = ''      # «Единый телефон» роли не несёт
                if канон:
                    ст['с_ролью'] += 1
                    роли[канон] = роли.get(канон, 0) + 1
                url = (LS._luchshie_stranicy(узел.get('stranicy')) or [''])[0]
                if not primenit:
                    continue
                ок = db.add_phone(инн, узел.get('kak') or ключ, role=канон,
                                  source=ИСТОЧНИК, source_url=url)
                if ок:
                    ст['записано'] += 1
                else:
                    ст['уже_было'] += 1
            if primenit:
                db.mark_stage(инн, СТАДИЯ,
                              'номеров %d' % len(найдено))
        except Exception as e:  # noqa: BLE001 - одна компания не рушит прогон
            ст['ошибок'] += 1
            _журнал({'инн': инн, 'ошибка': str(e)[:160]})
        if i % 500 == 0:
            скорость = i / max(1e-6, time.time() - начало)
            _журнал({'сделано': i, 'из': len(очередь), 'ст': dict(ст),
                     'в_час': int(скорость * 3600)})
            print(time.strftime('%H:%M:%S'), i, 'из', len(очередь),
                  json.dumps(ст, ensure_ascii=False), flush=True)
    db.cx.close()
    ст['роли'] = dict(sorted(роли.items(), key=lambda x: -x[1])[:14])
    ст['очередь'] = len(очередь)
    ст['секунд'] = round(time.time() - начало)
    ст['режим'] = 'ЗАПИСЬ' if primenit else 'сухой'
    _журнал({'итог': ст})
    return ст


def main():
    а = sys.argv[1:]
    предел = None
    if '--predel' in а:
        предел = int(а[а.index('--predel') + 1])
    итог = progon(предел, '--primenit' in а)
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
