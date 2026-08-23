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
СОБРАНО = r'C:\sender\_ops\roli_sobrano.jsonl'
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


def _с_повтором(f, *а, **кв):
    """«database is locked» — не ошибка компании, а очередь к файлу базы.

    Первый прогон 21.08 потерял 8604 компании именно так: в enrich.db в это же
    время пишут мост Зенки, поиск сайтов и цикл фактов, а тридцати секунд
    ожидания хватало не всегда. Ждём и повторяем, а не выбрасываем компанию.
    """
    import sqlite3 as _sq
    for попытка in range(4):
        try:
            return f(*а, **кв)
        except _sq.OperationalError as e:
            if 'locked' not in str(e).lower() or попытка == 3:
                raise
            time.sleep(2.0 * (попытка + 1))


_БУФЕР = []
_СБРОС = 100


def _сбросить_собранное():
    """Сбросить накопленное на диск одним разом, с fsync."""
    if not _БУФЕР:
        return
    os.makedirs(os.path.dirname(СОБРАНО), exist_ok=True)
    with open(СОБРАНО, 'a', encoding='utf-8') as f:
        f.write(''.join(_БУФЕР))
        f.flush()
        os.fsync(f.fileno())
    _БУФЕР.clear()


def _строка_собранного(запись):
    """Собранное со страниц пишем в файл, а не в базу: база занята боевыми.

    fsync на КАЖДУЮ компанию оказался дороже самого разбора: диск занят Зенкой
    и антивирусом, и один сброс стоил секунды — 42 компании за пять минут
    против пятисот за минуту у прежнего варианта. Копим сотню и пишем разом:
    в худшем случае после падения пересмотрим сто компаний, это секунды.
    """
    _БУФЕР.append(json.dumps(запись, ensure_ascii=False) + '\n')
    if len(_БУФЕР) >= _СБРОС:
        _сбросить_собранное()


def _уже_собрано():
    """ИНН, которые уже прочитаны со страниц: файл — и есть отметка о проходе."""
    было = set()
    if not os.path.exists(СОБРАНО):
        return было
    with open(СОБРАНО, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                было.add(str(json.loads(s).get('inn')))
            except Exception:  # noqa: BLE001
                pass
    return было


def sliyanie(porciya=400, pauza=0.4):
    """Перенести собранное в базу ПАКЕТАМИ, своим соединением.

    Первая версия звала EnrichDB.add_phone на каждый номер, а он делает три
    чтения и свой commit — сорок тысяч отдельных запросов на блокировку. При
    живых мосте, цикле фактов и поиске сайтов это выродилось в сплошное
    «database is locked», хотя короткая запись со стороны проходит мгновенно:
    мешал не чужой замок, а собственная манера долбить его по одному разу на
    строку. Теперь одна транзакция на четыреста строк.

    Правила записи повторяют add_phone, потому что они не косметические:
      * номер приводится к десяти цифрам, иначе не номер;
      * реквизиты компании (её ИНН и ОГРН) телефоном не считаются;
      * роль канонизируется той же таблицей;
      * номер, уже записанный за ДРУГИМ предприятием, роли не получает —
        это коммутатор, а не прямой телефон;
      * непустая роль не понижается до общей, непустое ФИО не затирается.
    """
    import re as _re
    import sqlite3 as _sq
    if not os.path.exists(СОБРАНО):
        return {'нечего сливать': True}
    записи = []
    with open(СОБРАНО, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                записи.append(json.loads(s))
            except Exception:  # noqa: BLE001
                pass

    c = _sq.connect(os.environ.get('ENRICH_DB', r'C:\sender\enrich.db'),
                    timeout=60)
    c.execute('PRAGMA busy_timeout=60000')
    сделано = {str(r[0]) for r in c.execute(
        'select inn from stage_log where stage=?', (СТАДИЯ,))}
    реквизиты = {}
    for инн, огрн in c.execute("select inn, coalesce(ogrn,'') from companies"):
        реквизиты[str(инн)] = str(огрн or '')
    чей_номер = {}
    for инн, тел in c.execute("select inn, phone from phone_contacts"):
        d = _re.sub(r'\D', '', str(тел or ''))
        if len(d) == 11 and d[0] in '78':
            d = d[1:]
        if len(d) == 10:
            чей_номер.setdefault(d, set()).add(str(инн))

    СТРОКА = ('INSERT INTO phone_contacts(inn,phone,person,role,source,'
              'source_url,updated_at) VALUES(?,?,?,?,?,?,?) '
              'ON CONFLICT(inn,phone,source_url) DO UPDATE SET '
              "role=CASE WHEN excluded.role NOT IN ('','общий') THEN excluded.role "
              'ELSE phone_contacts.role END, '
              'updated_at=excluded.updated_at')
    теперь = time.strftime('%Y-%m-%dT%H:%M:%S')
    ст = {'компаний': 0, 'строк': 0, 'с_ролью': 0, 'реквизитов_отсеяно': 0,
          'общих_номеров': 0, 'пакетов': 0, 'сбоев_пакета': 0}
    пакет, инны = [], []
    for з in записи:
        инн = str(з.get('inn') or '')
        if not инн or инн in сделано:
            continue
        сделано.add(инн)
        ст['компаний'] += 1
        for т in з.get('tel') or []:
            d = _re.sub(r'\D', '', str(т.get('nomer') or ''))
            if len(d) == 11 and d[0] in '78':
                d = d[1:]
            if len(d) != 10:
                continue
            огрн = реквизиты.get(инн, '')
            if d and (d in инн or (огрн and d in огрн)):
                ст['реквизитов_отсеяно'] += 1
                continue
            роль = EnrichDB._canon_role(т.get('rol') or '') if т.get('rol') else ''
            if роль == 'общий':
                роль = ''
            чужие = чей_номер.get(d, set()) - {инн}
            if роль and чужие:
                ст['общих_номеров'] += 1
                роль = ''
            чей_номер.setdefault(d, set()).add(инн)
            if роль:
                ст['с_ролью'] += 1
            пакет.append((инн, str(т.get('nomer') or '')[:60], '', роль,
                          ИСТОЧНИК, т.get('url') or '', теперь))
        инны.append(инн)
        if len(пакет) >= porciya:
            ст['строк'] += _пакетом(c, СТРОКА, пакет, инны, ст, теперь)
            пакет, инны = [], []
            time.sleep(pauza)
    if пакет or инны:
        ст['строк'] += _пакетом(c, СТРОКА, пакет, инны, ст, теперь)
    c.close()
    _журнал({'слияние_итог': ст})
    return ст


def _пакетом(c, СТРОКА, пакет, инны, ст, теперь):
    """Одна транзакция: строки телефонов и отметки о пройденных компаниях."""
    from datetime import datetime, timezone
    метка = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for попытка in range(5):
        try:
            c.execute('BEGIN IMMEDIATE')
            if пакет:
                c.executemany(СТРОКА, пакет)
            if инны:
                c.executemany(
                    'INSERT INTO stage_log(inn, stage, detail, ts) VALUES(?,?,?,?) '
                    'ON CONFLICT(inn, stage) DO UPDATE SET ts=excluded.ts',
                    [(и, СТАДИЯ, 'подписи', метка) for и in инны])
            c.commit()
            ст['пакетов'] += 1
            return len(пакет)
        except Exception as e:  # noqa: BLE001
            try:
                c.rollback()
            except Exception:  # noqa: BLE001
                pass
            if попытка == 4:
                ст['сбоев_пакета'] += 1
                _журнал({'пакет': str(e)[:120], 'строк': len(пакет)})
                return 0
            time.sleep(2.0 * (попытка + 1))
    return 0


def progon(predel=None, primenit=False):
    db = EnrichDB()
    свои = {str(r[0]) for r in db.cx.execute('select inn from companies')}
    сделано = {str(r[0]) for r in db.cx.execute(
        'select inn from stage_log where stage=?', (СТАДИЯ,))}
    db.cx.close()
    сделано |= _уже_собрано()
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
                    _строка_собранного({'inn': инн, 'tel': []})
                continue
            ст['со_страницами'] += 1
            найдено = (LS._kontakty_so_stranic(страницы) or {}).get('tel') or {}
            собрано = []
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
                собрано.append({'nomer': узел.get('kak') or ключ,
                                'rol': канон, 'url': url})
            if primenit:
                # строку пишем ВСЕГДА, даже когда телефонов не нашлось: файл
                # служит отметкой «эту компанию уже смотрели», и без неё
                # компания без номеров просматривалась бы каждый круг заново
                _строка_собранного({'inn': инн, 'tel': собрано})
                ст['записано'] += len(собрано)
        except Exception as e:  # noqa: BLE001 - одна компания не рушит прогон
            ст['ошибок'] += 1
            _журнал({'инн': инн, 'ошибка': str(e)[:160]})
        if i % 500 == 0:
            _сбросить_собранное()
            скорость = i / max(1e-6, time.time() - начало)
            _журнал({'сделано': i, 'из': len(очередь), 'ст': dict(ст),
                     'в_час': int(скорость * 3600)})
            print(time.strftime('%H:%M:%S'), i, 'из', len(очередь),
                  json.dumps(ст, ensure_ascii=False), flush=True)
    _сбросить_собранное()
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
    if '--sliyanie' in а:
        итог = sliyanie()
    else:
        итог = progon(предел, '--primenit' in а)
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
