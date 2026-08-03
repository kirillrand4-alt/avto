# -*- coding: utf-8 -*-
"""Пересудить тех, у кого появились НОВЫЕ факты после приговора.

Приговор выносился по фактам, которые были в базе на тот момент. Доливка
принесла 5813 фактов на 921 предприятие — значит по части дел появились
доказательства, которых судья не видел. Оставить старый приговор значит
держать скрытым завод, доказательство по которому уже лежит в базе.

Обратное тоже верно и тоже важно: у предприятия с приговором «есть» новые
факты приговор не отменят, поэтому их не трогаем — пересуживать доказанное
значит платить дважды за тот же ответ.

Пересуживаем только тех, кто ОДНОВРЕМЕННО:
  * получил новый факт при доливке (id факта больше отметки),
  * и имеет приговор «нет» или «не установлено».

Механика простая: удаляем их приговоры из `sud_centro`, и резюмируемый суд
берёт их следующим кругом сам. Скрытие предприятия при этом НЕ снимаем здесь —
его снимет новый приговор, если он изменится; снимать заранее значит вернуть
продавцу непроверенное.

По умолчанию СУХОЙ ПРОГОН. Запуск: python _pereotkryt_dela.py [--apply]
"""
import json
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПРИМЕНИТЬ = '--apply' in sys.argv
# отметка: id последнего факта ДО доливки (было 34248 строк, id идут подряд)
ОТМЕТКА = int(sys.argv[sys.argv.index('--otmetka') + 1]
              if '--otmetka' in sys.argv else 34248)


def main():
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    свежие = {str(r[0]) for r in цб.execute(
        'SELECT DISTINCT inn FROM fact WHERE id > ?', (ОТМЕТКА,))}
    цб.close()
    db = EDB.EnrichDB()
    приговоры = {r[0]: r[1] for r in db.cx.execute(
        'SELECT inn, verdikt FROM sud_centro')}
    к_пересуду = {и: приговоры[и] for и in свежие
                  if приговоры.get(и) in ('нет', 'не установлено')}
    рас = Counter(к_пересуду.values())
    print(json.dumps({
        'предприятий_с_новыми_фактами': len(свежие),
        'из_них_имеют_приговор': sum(1 for и in свежие if и in приговоры),
        'К_ПЕРЕСУДУ': len(к_пересуду),
        'разбивка': рас.most_common(),
        'не_трогаем_доказанных': sum(
            1 for и in свежие
            if приговоры.get(и) in ('есть', 'покупает', 'планирует')),
        'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)',
    }, ensure_ascii=False, indent=1))
    if not ПРИМЕНИТЬ or not к_пересуду:
        if not ПРИМЕНИТЬ:
            print('\nсухой прогон. Повторить с --apply')
        return
    db.cx.executemany('DELETE FROM sud_centro WHERE inn=?',
                      [(и,) for и in к_пересуду])
    db.cx.commit()
    осталось = db.cx.execute('SELECT COUNT(*) FROM sud_centro').fetchone()[0]
    print(json.dumps({'приговоров_осталось': осталось,
                      'пересудить_в_очереди': len(к_пересуду)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
