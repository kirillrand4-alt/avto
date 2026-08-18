# -*- coding: utf-8 -*-
r"""Отправить работнику на VPS задание проверить адреса партии.

Штатный цикл probe_sync публикует только адреса ОЧЕРЕДИ ПОДТВЕРЖДЕНИЯ — то есть
те, по которым письмо уже написано. Адреса свежезалитой партии писем ещё не
имеют, и до проверки дошли бы только по мере генерации. Это поздно: непригодный
адрес выясняется в момент отправки и бьёт по репутации домена.

Здесь берём адреса группы, у которых вердикта нет, и отдаём их тем же путём,
каким панель отдаёт срочные (ProbeSync.срочно): задание дописывается на дроп,
работнику кладётся задача-толчок. Ничего своего в сеть не ходит — только на наш
дроп; проверку делает VPS со своей обратной записью.

    python probe_zadanie_gruppy.py "Партия 935" [сколько]           посчитать
    python probe_zadanie_gruppy.py "Партия 935" [сколько] --otpravit отправить
"""
import json
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')
КОНФИГ = r'C:\sender\sender.yaml'
БД = r'C:\sender\sender.db'


def адреса_группы(группа):
    s = sqlite3.connect('file:%s?mode=ro' % БД.replace('\\', '/'), uri=True)
    из = []
    for em, ex in s.execute("select lower(coalesce(email,'')), coalesce(extra_json,'') "
                            "from recipients where extra_json like ?",
                            ('%' + группа + '%',)):
        if not em:
            continue
        try:
            d = json.loads(ex) if ex.strip() else {}
        except Exception:  # noqa: BLE001
            continue
        # разбором JSON, а не по LIKE: та же строка остаётся в gruppy_ubrano —
        # следе снятого тега, и снятый получатель выглядел бы состоящим в группе
        if группа in [str(g) for g in (d.get('gruppy') or [])]:
            из.append(em)
    s.close()
    return sorted(set(из))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    доводы = [a for a in sys.argv[1:] if not a.startswith('--')]
    группа = доводы[0] if доводы else 'Партия 935'
    предел = int(доводы[1]) if len(доводы) > 1 and доводы[1].isdigit() else 0
    отправлять = '--otpravit' in sys.argv

    from sender.config import Config
    from sender.store import Store
    from sender.addr_probe import build_addr_probe
    from sender.probe_sync import build_probe_sync

    config = Config.load(КОНФИГ, env=__import__('os').environ)
    store = Store(БД)
    проба = build_addr_probe(store, config)
    цикл = build_probe_sync(store, getattr(проба, 'probe_', проба), config)

    все = адреса_группы(группа)
    надо = [a for a in все if not цикл.probe.cached(a)]
    if предел:
        надо = надо[:предел]
    итог = {'группа': группа, 'адресов_в_группе': len(все),
            'без_вердикта': len(надо), 'отправлено': None}
    if отправлять and надо:
        итог['отправлено'] = цикл.срочно(надо)
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
