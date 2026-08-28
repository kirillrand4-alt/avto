# -*- coding: utf-8 -*-
r"""Вторая фаза добора: записать в базу адреса, вынутые из кэша, вместе с ролями.

Первая фаза (`pochty_iz_kesha_zamer.py`) прошла 25 546 паспортов, у которых
своей почты с сайта не было, и собрала 37 352 адреса у 15 498 компаний, из них
34 449 базе неизвестны. Здесь мы их пишем.

ПОЧЕМУ ОТДЕЛЬНОЙ ФАЗОЙ. Старый добор ходил по кэшу и писал по одному адресу за
раз, каждый со своими повторами по «database is locked». На живой базе это
давало 0,4 компании в минуту — сутки на партию. Разделение убирает главную
причину: чтение диска больше не соперничает с записью, а запись идёт пачками.

ЧТО СОХРАНЯЕМ ОТ СТАРОГО ПУТИ. Пишем через `EnrichDB.add_email`, а не своим
INSERT: там живут чинилка битых адресов (сайты прячут почту, и «ba%6d_%74%70@»
без неё уедет в базу как есть), отсев реквизитов, правило «роль общего ящика —
это заход, а не владелец» и защита от понижения уже известной роли. Роль берём
по имени ящика тем же `rol_iz_imeni_yashchika`, что и обходчик: info, sales,
zakupki, buh. Не опознали — пусто, и это нормально.

Пачками коммитим сами: `add_email` делает commit на каждый адрес, поэтому на
время пачки подменяем commit заглушкой и фиксируем один раз на 200 адресов, с
повтором при занятой базе. Журнал записанных ИНН — durable, прогон резюмируемый.

    python pochty_iz_kesha_zapis.py            прикидка, без записи
    python pochty_iz_kesha_zapis.py --pisat    записать
"""
import json
import os
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault('NO_BROWSER', '1')

ВХОД = r'C:\sender\_tmp\pochty-v-keshe.jsonl'
ЖУРНАЛ = r'C:\sender\_tmp\pochty-zapisany.jsonl'


def _sdelano():
    было = set()
    if os.path.exists(ЖУРНАЛ):
        with open(ЖУРНАЛ, encoding='utf-8', errors='replace') as f:
            for s in f:
                try:
                    з = json.loads(s)
                except Exception:  # noqa: BLE001
                    continue
                # сбой записи — НЕ «сделано»: компанию должен подобрать
                # следующий заход, иначе замок помечает её готовой навсегда
                if not з.get('сбой'):
                    было.add(з['инн'])
    return было


def _ochered():
    из = []
    with open(ВХОД, encoding='utf-8', errors='replace') as f:
        for s in f:
            if not s.strip():
                continue
            try:
                з = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if з.get('адреса'):
                из.append((str(з['инн']), з['адреса']))
    return из


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    писать = '--pisat' in sys.argv or os.environ.get('ZAPIS_PISAT') == '1'
    очередь = _ochered()
    было = _sdelano()
    работа = [(и, а) for и, а in очередь if и not in было]
    d = {'компаний_в_выемке': len(очередь), 'уже_записано': len(было),
         'к_записи': len(работа),
         'адресов_к_записи': sum(len(а) for _, а in работа)}
    if not писать:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0

    import enrich_contacts as EC
    import enrich_db as EDB

    db = EDB.EnrichDB()
    # Ждём замок ДОЛГО, а не отскакиваем. Рядом пишет демон моста: он просыпается
    # раз в две минуты, и попытка с двадцатью секундами ожидания просто не
    # попадала в промежуток — за десять минут не прошло ни одной пачки.
    db.cx.execute('PRAGMA busy_timeout=180000')
    настоящее = db.cx
    настоящий_commit = настоящее.commit

    class _БезКоммита:
        """Соединение, которое молча глотает commit.

        Подменить `commit` прямо на sqlite3.Connection нельзя — атрибут только
        для чтения. Поэтому обёртка: всё передаём настоящему соединению, а
        commit гасим, чтобы пачка фиксировалась один раз, а не на каждый адрес.
        """

        def __init__(self, cx):
            object.__setattr__(self, '_cx', cx)

        def commit(self):
            return None

        def __getattr__(self, имя):
            return getattr(self._cx, имя)

    db.cx = _БезКоммита(настоящее)

    итог = {'компаний': 0, 'адресов': 0, 'мусор': 0, 'пачек': 0,
            'пачек_не_вышло': 0, 'ожиданий_замка': 0}
    журнал = open(ЖУРНАЛ, 'a', encoding='utf-8')
    t0 = time.time()

    # ПАЧКА ЦЕЛИКОМ ПОВТОРЯЕТСЯ. Замок ловится не только на commit, но и на
    # первой же записи, и тогда половина пачки уже применена. Поэтому вся
    # пачка — одна попытка: не вышло, откатываем и пробуем заново. Пятьдесят
    # компаний за транзакцию: длиннее держать замок нечестно по отношению к
    # панели и обходу, короче — теряется смысл пачки.
    ПАЧКА_КОМПАНИЙ = 20
    for н in range(0, len(работа), ПАЧКА_КОМПАНИЙ):
        кусок = работа[н:н + ПАЧКА_КОМПАНИЙ]
        for попытка in range(60):
            записано = []
            адресов = мусора = 0
            try:
                for инн, адреса in кусок:
                    for адрес, урл in адреса:
                        if EC._is_junk_email(адрес):
                            мусора += 1
                            continue
                        db.add_email(инн, адрес,
                                     role=EC.rol_iz_imeni_yashchika(адрес),
                                     source='кэш-добор', source_url=урл or '',
                                     pometka='кэш-добор')
                        адресов += 1
                    записано.append(инн)
                настоящий_commit()
                итог['пачек'] += 1
                итог['компаний'] += len(записано)
                итог['адресов'] += адресов
                итог['мусор'] += мусора
                for и in записано:
                    журнал.write(json.dumps(
                        {'инн': и, 'ts': time.strftime('%H:%M:%S')},
                        ensure_ascii=False) + '\n')
                журнал.flush()
                os.fsync(журнал.fileno())
                break
            except Exception as e:  # noqa: BLE001
                сообщение = str(e).lower()
                if 'locked' not in сообщение and 'busy' not in сообщение:
                    raise
                итог['ожиданий_замка'] += 1
                try:
                    настоящее.rollback()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(min(15, 2 + попытка))
        else:
            итог['пачек_не_вышло'] += 1
            for инн, _ in кусок:
                журнал.write(json.dumps({'инн': инн, 'сбой': 'замок'},
                                        ensure_ascii=False) + '\n')
            журнал.flush()
        if итог['компаний'] and итог['компаний'] % 2000 < ПАЧКА_КОМПАНИЙ:
            print(json.dumps({'секунд': round(time.time() - t0), **итог},
                             ensure_ascii=False), flush=True)
    журнал.close()
    db.cx = настоящее
    итог['секунд'] = round(time.time() - t0)
    d['запись'] = итог
    d['почт_в_базе_итого'] = настоящее.execute(
        'select count(*) from emails').fetchone()[0]
    d['компаний_с_почтой'] = настоящее.execute(
        'select count(distinct inn) from emails').fetchone()[0]
    d['с_меткой_кэш_добор'] = настоящее.execute(
        "select count(*) from emails where coalesce(pometka,'') like '%кэш-добор%'"
    ).fetchone()[0]
    настоящее.close()
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
