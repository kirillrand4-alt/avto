# -*- coding: utf-8 -*-
"""P25: вычистить «должность из запроса» — предупреждение 3-й сессии по 006–009.

ЧТО СЛУЧИЛОСЬ У НЕЁ. Канал искал «предприятие + должность» и проверял наличие
должности на странице по последнему слову, обрезанному до шести букв. Для
«технический директор» это «директ» — и подходил ЛЮБОЙ директор. Трое поехали
как технические ЛПР с ролью «1 круг», а в цитате у них «Генеральный директор».
Страница должность не подтверждала — она просто не возражала.

ЕЁ ПРИЗНАК ДЛЯ ОТБОРА, дословно: строка со ссылкой `otc.ru/organization/` ЛИБО
роль «1 круг» при слове «Генеральный директор» в цитате. Беру оба и добавляю
третий, свой: должность в базе содержит «техническ», а цитата называет другую
должность целиком.

ЧТО ДЕЛАЮ С НАЙДЕННЫМ. Человека и номер НЕ выбрасываю — они настоящие, вранья
не было в них. Убираю ЛОЖНУЮ ДОЛЖНОСТЬ и признак технаря, ставлю то, что
говорит цитата, если она говорит внятно. Это ровно правило владельца
«разделять, а не отсеивать»: гендиректор — тоже человек предприятия, просто он
не технический ЛПР и в главную меру идти не должен.

КАРТОЧКА ОРГАНИЗАЦИИ ≠ КАРТОЧКА ЗАКУПКИ. `otc.ru/organization/…` — это выписка
ЕГРЮЛ в оформлении площадки, там по определению только руководитель по реестру.
Такую страницу первоисточником должности считать нельзя, и это отдельная
пометка в источнике.

Запуск: python p25_dolzhnost_iz_zaprosa.py [--apply]
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

P25 = r'C:\seostat\data\p25.db'
ПОТОК = r'C:\seostat\drop\p25_dolzhnost_iz_zaprosa.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv

КАРТОЧКА_ОРГ = re.compile(r'otc\.ru/organization/', re.I)
ЧУЖАЯ_ДОЛЖНОСТЬ = re.compile(
    r'(генеральн\w*\s+директор\w*|исполнительн\w*\s+директор\w*|'
    r'\bруководител\w*\s+организац|коммерческ\w*\s+директор\w*)', re.I)
НАША_ТЕХ = re.compile(
    r'(техническ\w*\s+директор\w*|главн\w*\s+инженер\w*|главн\w*\s+энергетик\w*|'
    r'главн\w*\s+механик\w*|начальник\w*\s+производств\w*|главн\w*\s+технолог\w*)',
    re.I)


def main():
    цб = sqlite3.connect(P25, timeout=30)
    цб.row_factory = sqlite3.Row
    поля = {r[1] for r in цб.execute('PRAGMA table_info(person)')}
    цитата_к = 'chem_podtverzhdena' if 'chem_podtverzhdena' in поля else ''
    строки = [dict(r) for r in цб.execute(
        'SELECT rowid AS rid, inn, COALESCE(person,\'\') AS person, '
        'COALESCE(position,\'\') AS position, COALESCE(role,\'\') AS role, '
        'COALESCE(source_url,\'\') AS url, COALESCE(is_tech,0) AS is_tech'
        + (f', COALESCE({цитата_к},\'\') AS citata' if цитата_к else ", '' AS citata")
        + ' FROM person')]

    # цитаты наблюдений — там текст со страницы, а не наша подпись
    набл = {}
    for инн, чел, ц, url in цб.execute(
            "SELECT inn, COALESCE(person,''), COALESCE(quote,''), "
            "COALESCE(source_url,'') FROM contact_source"):
        набл.setdefault((str(инн), str(чел)), []).append((str(ц), str(url)))

    стат = Counter()
    находки = []
    for ч in строки:
        цитаты = [ч['citata']] + [ц for ц, _u in набл.get((str(ч['inn']), ч['person']), [])]
        ссылки = [ч['url']] + [u for _ц, u in набл.get((str(ч['inn']), ч['person']), [])]
        весь_текст = ' /// '.join(x for x in цитаты if x)
        чужая = ЧУЖАЯ_ДОЛЖНОСТЬ.search(весь_текст)
        орг_карточка = any(КАРТОЧКА_ОРГ.search(u or '') for u in ссылки)
        должность_тех = bool(НАША_ТЕХ.search(ч['position']))
        # должность в базе техническая, а страница называет ДРУГУЮ целиком
        подложна = должность_тех and чужая and not НАША_ТЕХ.search(весь_текст)
        причина = ''
        if подложна:
            причина = f'цитата говорит «{чужая.group(0)}», а записано «{ч["position"]}»'
        elif орг_карточка and должность_тех:
            причина = 'должность взята с карточки ОРГАНИЗАЦИИ (выписка ЕГРЮЛ), не закупки'
        if not причина:
            continue
        стат[причина.split(',')[0][:52]] += 1
        находки.append({**ч, 'prichina': причина,
                        'chto_na_stranice': чужая.group(0) if чужая else ''})

    print('ДОЛЖНОСТЬ НЕ ПОДТВЕРЖДЕНА СТРАНИЦЕЙ:')
    for н in находки[:12]:
        print(f"   {н['inn']} {н['person'][:26]:26} записано «{н['position'][:24]}» "
              f"← страница: «{н['chto_na_stranice'][:24]}» тех={н['is_tech']}")
    if not находки:
        print('    ни одной — влитое чисто по её признаку')

    if not ПРИМЕНИТЬ or not находки:
        print()
        print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
        print('СУХОЙ ПРОГОН' if not ПРИМЕНИТЬ else 'чинить нечего')
        цб.close()
        return

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    журнал = []
    for н in находки:
        новая = н['chto_na_stranice'].strip() or ''
        цб.execute(
            'UPDATE person SET position=?, is_tech=0, role=?, '
            'chem_podtverzhdena=? WHERE rowid=?',
            (новая, '4 круг: руководство' if новая else '',
             'должность снята: страница её не подтверждала (сигнал 3-й сессии)',
             н['rid']))
        цб.execute(
            "UPDATE contact SET position=?, is_tech=0 WHERE inn=? AND person=?",
            (новая, н['inn'], н['person']))
        журнал.append({'inn': н['inn'], 'person': н['person'],
                       'bylo': н['position'], 'stalo': новая,
                       'prichina': н['prichina'], 'ts': ts})
    цб.commit()
    тех = цб.execute(
        'SELECT COUNT(*) FROM person WHERE COALESCE(is_tech,0)=1').fetchone()[0]
    тех_п = цб.execute(
        'SELECT COUNT(DISTINCT inn) FROM person WHERE COALESCE(is_tech,0)=1').fetchone()[0]
    людей = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    цб.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in журнал:
            ф.write(json.dumps(з, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print()
    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    print(f'ЛЮДЕЙ {людей}, никто не удалён')
    print(f'ТЕХНИЧЕСКИХ СТАЛО: {тех} на {тех_п} предприятиях')


if __name__ == '__main__':
    main()
