# -*- coding: utf-8 -*-
"""Вернуть в работу тех, кого пересуд оправдал новыми доказательствами.

СМЫСЛ. Доливка фактов и реестр ЭПБ дали новые доказательства по предприятиям,
которые суд ранее закрыл приговором «нет» и спрятал из панели. Дела таких
переоткрыты и пересужены. Если новый приговор «есть», «покупает» или
«планирует» — предприятие обязано вернуться продавцу, иначе вся доливка была
работой в стол: доказательство добыли, а карточка так и осталась скрытой.

ПОЧЕМУ СНИМАЕМ ТОЛЬКО СВОЁ СКРЫТИЕ. В `hidden_item` лежат скрытия из разных
рук: суд, ручная чистка непрофильных, снятие мусора соседними сессиями. Мы
снимаем только те, что поставил суд (по подписи в `reason`) — чужое решение
отменять нельзя, у него была своя причина, нам не видная.

СТАРЫЙ ПРИГОВОР БЕРЁМ ИЗ ЖУРНАЛА, а не из таблицы: переоткрытие дела удаляет
строку приговора, и к моменту сравнения прежнего вердикта в базе уже нет.
`sud_centro.jsonl` пишется с fsync на каждый приговор и переживает всё, включая
перезапуск контейнера, — ровно для таких случаев он и заведён.

По умолчанию СУХОЙ ПРОГОН. Запуск: python vernut_dokazannyh.py [--apply]
"""
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ЖУРНАЛ = r'C:\sender\server\sud_centro.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ДОКАЗАН = ('есть', 'покупает', 'планирует')
# Подпись суда в причине скрытия: только такие скрытия мы вправе снимать.
_НАШЕ_СКРЫТИЕ = re.compile(r'суд\s+моделей|приговор', re.I)


def инн_кл(т):
    return re.sub(r'\D', '', str(т or ''))[:12]


def прежние_приговоры():
    """ИНН → список приговоров по журналу, в порядке появления."""
    было = {}
    if not os.path.exists(ЖУРНАЛ):
        return было
    with open(ЖУРНАЛ, encoding='utf-8', errors='replace') as ж:
        for стр in ж:
            try:
                з = json.loads(стр)
            except Exception:  # noqa: BLE001
                continue
            и = инн_кл(з.get('inn'))
            в = (з.get('verdikt') or '').strip()
            if и and в:
                было.setdefault(и, []).append(в)
    return было


def main():
    db = EDB.EnrichDB()
    сейчас_пр = {}
    for и, в, п, у in db.cx.execute(
            "SELECT inn, verdikt, COALESCE(pochemu,''), "
            "COALESCE(uverennost,'') FROM sud_centro"):
        сейчас_пр[инн_кл(и)] = (в or '', п, у)

    имена = {}
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    for и, н in цб.execute('SELECT inn, predpriyatie FROM company'):
        имена[инн_кл(и)] = н or ''
    цб.close()

    пр = sqlite3.connect(ПР, timeout=20)
    пр.execute('PRAGMA busy_timeout=20000')
    скрытые = {}
    for и, з, пр_ч in пр.execute(
            "SELECT inn, value, COALESCE(reason,'') FROM hidden_item "
            "WHERE kind='company'"):
        скрытые[инн_кл(и)] = (з, пр_ч)

    было = прежние_приговоры()
    вернуть, чужие = [], 0
    остаток = Counter()
    откуда = Counter()
    for и, (значение, причина) in скрытые.items():
        новый = сейчас_пр.get(и)
        if not новый:
            # ПРИГОВОРА НЕТ ВОВСЕ — дело переоткрыто и ещё не пересужено.
            # Считать это «приговор не изменился» нельзя: тогда «вернуть 0»
            # означает то ли «никого не оправдали», то ли «суд ещё идёт», а
            # это два разных ответа и два разных следующих шага.
            остаток['ждёт пересуда, приговор снят'] += 1
            continue
        if новый[0] not in ДОКАЗАН:
            остаток[f'приговор прежний: {новый[0]}'] += 1
            continue
        if not _НАШЕ_СКРЫТИЕ.search(причина):
            # скрыто не судом: непрофильный ОКВЭД, ручная чистка соседей
            чужие += 1
            continue
        прежний = ''
        for в in reversed(было.get(и, [])):
            if в != новый[0]:
                прежний = в
                break
        откуда[прежний or 'прежний приговор неизвестен'] += 1
        вернуть.append((и, значение, имена.get(и, ''), прежний, новый[0],
                        новый[1][:150], новый[2]))

    print(json.dumps({
        'скрытых_предприятий_всего': len(скрытые),
        'ВЕРНУТЬ_В_РАБОТУ': len(вернуть),
        'из_какого_приговора_вернулись': откуда.most_common(),
        'скрыто_не_судом_не_трогаем': чужие,
        'почему_остальные_остались': остаток.most_common(),
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False, indent=1))
    for и, _з, имя, стар, нов, поч, ув in вернуть[:25]:
        print(f'  {и} {имя[:40]:<40} {стар or "?"} → {нов} ({ув}) — {поч[:90]}')

    if not ПРИМЕНИТЬ or not вернуть:
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        пр.close()
        return

    пр.executemany(
        "DELETE FROM hidden_item WHERE kind='company' AND inn=? AND value=?",
        [(и, з) for и, з, _н, _с, _нов, _п, _у in вернуть])
    пр.commit()
    стало = пр.execute(
        "SELECT COUNT(*) FROM hidden_item WHERE kind='company'").fetchone()[0]
    пр.close()
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    всего = цб.execute('SELECT COUNT(*) FROM company').fetchone()[0]
    цб.close()
    print(json.dumps({'скрыто_предприятий_осталось': стало,
                      'ВИДИМЫХ_В_ПАНЕЛИ': всего - стало,
                      'вернули': len(вернуть),
                      'когда': time.strftime('%Y-%m-%dT%H:%M:%S')},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
