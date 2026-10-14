# -*- coding: utf-8 -*-
r"""fixW (14.10): сегмент у компаний, где он пустой, – чтобы в фильтре «Все сегменты» были не только пищевые.

Владелец 14.10 (скрин фильтра: «1 экспортёры, 2 семеноводы, 3 пищевые, 4 элеваторы, 6 ягоды»): «сделай, чтобы можно
выбрать и остальные сегменты тоже, мы же не только пищевые сделали».

Шкала панели – ТЗ «1 экспортёры … 6 ягоды» (сегмент по основному ОКВЭД, таблица okved_segment_tz.json из Баз 2–4: только
пищевые коды). У компаний MEYER-7 вне этих кодов (стекло, руды, уголь, пластик, вторсырьё, белорусские без ОКВЭД…) сегмент
пустой – в фильтре их нет. Номера той же шкалы у них уже есть в сегменте сборки MEYER-7 (в скобках: «стекло (11)»,
«руды (22)», «изделия из пластмасс (7/8, …)»). Здесь пустой сегмент заполняется по названию сегмента MEYER-7 (без
«(Беларусь)», «— ИНН не определён», «(новый)»), а если его нет – по отрасли:
  пищевые переработчики -> «3 пищевые» (как и остальные пищевые в панели), семеноводство -> «2 семеноводы»,
  хранение/элеваторы -> «4 элеваторы», ягоды/дикоросы -> «6 ягоды», опт зерном -> «1 экспортёры» (как 46.21, 09.10),
  и новые по номерам ТЗ сборки: «7 изделия из пластмасс», «8 полимеры, гранула», «9 нерудные: камень, песок, кварц»,
  «10 соль», «11 стекло», «12 вторсырьё», «20 растениеводство», «21 опт продуктами», «22 руды, уголь, минералы»;
  без номера в ТЗ: «животноводство», «цветная металлургия», «корма».
Уже стоящие сегменты НЕ меняются. Прежнее значение – в segment_ishodnyy (если там пусто), segment_osn выравнивается.
Журнал «было/стало» – на дроп, копия базы – C:\centro2\_bekap\fixW-<время>\. Код панели не меняется.

    python3 zapusk_na_servere.py fixW_segmenty.py --suhoy      # план без записи
    python3 zapusk_na_servere.py fixW_segmenty.py --primenit   # запись
"""
import collections
import io
import json
import os
import re
import sqlite3
import sys
import time

KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
DROP = r'C:\seostat\drop\drop-storage'
VREMYA = time.strftime('%Y%m%d-%H%M%S')

# (подстрока названия сегмента MEYER-7 / отрасли) -> сегмент панели; порядок важен: первое совпадение
PRAVILA = [
    ('птицефабрики со своим убоем', '3 пищевые'), ('свиноводство со своим убоем', '3 пищевые'),
    ('молочное скотоводство', 'животноводство'), ('животноводство', 'животноводство'),
    ('изделия из пластмасс', '7 изделия из пластмасс'), ('полимеры, гранула', '8 полимеры, гранула'),
    ('обработка вторсырья', '12 вторсырьё'), ('опт отходами и ломом', '12 вторсырьё'),
    ('цветная металлургия', 'цветная металлургия'),
    ('стекло', '11 стекло'), ('соль', '10 соль'),
    ('прочие руды и минералы', '22 руды, уголь, минералы'), ('руды', '22 руды, уголь, минералы'),
    ('уголь', '22 руды, уголь, минералы'),
    ('камень, известняк', '9 нерудные: камень, песок, кварц'), ('песок, гравий', '9 нерудные: камень, песок, кварц'),
    ('нерудные', '9 нерудные: камень, песок, кварц'),
    ('семеноводство', '2 семеноводы'),
    ('хранение, элеваторы', '4 элеваторы'), ('послеуборочная обработка', '4 элеваторы'),
    ('зерно, семена, элеваторы', '4 элеваторы'),
    ('ягоды', '6 ягоды'), ('дикоросы', '6 ягоды'),
    ('опт зерном', '1 экспортёры'), ('неспециализированный опт', '21 опт продуктами'), ('опт:', '21 опт продуктами'),
    ('— выращивание', '20 растениеводство'), ('выращивание', '20 растениеводство'), ('лён, прядильные', '20 растениеводство'),
    ('корма, комбикорма', 'корма'),
    ('мясо и птица', '3 пищевые'), ('молоко, сыр', '3 пищевые'), ('хлеб, кондитерка', '3 пищевые'),
    ('кондитерка', '3 пищевые'), ('прочая пищевка', '3 пищевые'), ('пищевое производство', '3 пищевые'),
    ('МЭЗ, масложир', '3 пищевые'), ('мукомолье', '3 пищевые'), ('кофе, чай', '3 пищевые'), ('специи', '3 пищевые'),
    ('пряности', '3 пищевые'), ('крахмал', '3 пищевые'), ('фасовщики', '3 пищевые'), ('картофель, чипсы', '3 пищевые'),
    ('овощи, фрукты, орехи', '3 пищевые'),
]


def chistoe(s):
    s = re.sub(r'\s*\((?:Беларусь|новый)\)', '', s or '')
    return re.sub(r'\s*—\s*ИНН не определён', '', s).strip()


def segment_po(m7, otrasl):
    for istochnik in (chistoe(m7), chistoe(otrasl)):
        if not istochnik:
            continue
        perv = istochnik.split(';')[0].strip()          # «молочное скотоводство; зерно…» – по первому
        for pod, seg in PRAVILA:
            if pod.lower() in perv.lower():
                return seg, istochnik
    return None, chistoe(m7) or chistoe(otrasl)


def main():
    primenit = '--primenit' in sys.argv
    k = sqlite3.connect(KAT, timeout=30)
    k.row_factory = sqlite3.Row
    kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
    rows = [dict(r) for r in k.execute("SELECT inn, predpriyatie, segment, segment_osn, segment_ishodnyy, segment_meyer7, otrasl "
                                       "FROM company WHERE COALESCE(TRIM(segment),'')=''")]
    plan, net = [], collections.Counter()
    for r in rows:
        seg, ist = segment_po(r.get('segment_meyer7'), r.get('otrasl'))
        if seg:
            plan.append({'inn': r['inn'], 'nazvanie': r['predpriyatie'], 'bylo': r.get('segment') or '', 'stalo': seg, 'po': ist})
        else:
            net[ist or '(ни сегмента MEYER-7, ни отрасли)'] += 1
    print('пустой сегмент: %d; получат сегмент: %d; не распознано: %d' % (len(rows), len(plan), sum(net.values())))
    print('\nпо новым сегментам:')
    for s, n in sorted(collections.Counter(p['stalo'] for p in plan).items(), key=lambda x: (int(x[0].split()[0]) if x[0][0].isdigit() else 99, x[0])):
        print('  %4d  %s' % (n, s))
    if net:
        print('\nне распознано:', dict(net))
    print('\nпримеры:')
    for s in sorted({p['stalo'] for p in plan}):
        p = next(x for x in plan if x['stalo'] == s)
        print('  %s  %s  <- %s' % (p['inn'], s, p['po']))
    if not primenit:
        print('\nСУХОЙ ПРОГОН: ничего не записано')
        return
    papka = os.path.join(KOREN, '_bekap', 'fixW-' + VREMYA)
    os.makedirs(papka, exist_ok=True)
    b = sqlite3.connect(os.path.join(papka, 'meyer_baza1.db'))
    k.backup(b)
    b.close()
    for _ in range(20):
        try:
            k.execute('BEGIN IMMEDIATE')
            break
        except sqlite3.OperationalError:
            time.sleep(3)
    else:
        raise SystemExit('база занята')
    try:
        for p in plan:
            tek = k.execute('SELECT segment FROM company WHERE inn=?', (p['inn'],)).fetchone()[0]
            if (tek or '').strip():
                p['propushcheno'] = 'сегмент уже стоит: %s' % tek
                continue
            k.execute("UPDATE company SET segment=?, segment_ishodnyy=CASE WHEN COALESCE(TRIM(segment_ishodnyy),'')='' "
                      "THEN COALESCE(segment,'') ELSE segment_ishodnyy END%s WHERE inn=?" % (
                          ', segment_osn=?' if 'segment_osn' in kol else ''),
                      (p['stalo'], p['stalo'], p['inn']) if 'segment_osn' in kol else (p['stalo'], p['inn']))
        n = k.execute("SELECT COUNT(*) FROM company WHERE COALESCE(TRIM(segment),'')=''").fetchone()[0]
        k.execute('COMMIT')
    except Exception:
        k.execute('ROLLBACK')
        raise
    zh = os.path.join(DROP, 'fixW-segmenty-zhurnal-%s.json' % VREMYA)
    io.open(zh, 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=0))
    print('\nЗАПИСАНО: %d; пустых сегментов осталось %d; журнал %s; копия базы %s' % (
        sum(1 for p in plan if 'propushcheno' not in p), n, os.path.basename(zh), papka))
    sch = collections.Counter(s.strip() for (seg,) in k.execute('SELECT segment FROM company') for s in str(seg or '').split('|') if s.strip())
    print('сегменты панели теперь:', sorted(sch.items()))


if __name__ == '__main__':
    main()
