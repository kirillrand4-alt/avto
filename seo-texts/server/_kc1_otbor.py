# -*- coding: utf-8 -*-
# 14.10, владелец: база КЦ, этап 1 — отбор из нашей базы обзвона (obzvon-index.db, обе базы) по ОКВЭД сводки этапа 0
# (kc0-svodka.json): основной список (2+ модели) и пробный (1 модель) по группам 1–4. Для группы 4 вручную добавлены
# покупатели дизельных передвижных (модели их почти не назвали): дорожное/общее строительство, бурение, трубопроводы, ЖКХ.
# Совпадение — по основному ОКВЭД (сильное) и по дополнительным (слабое). Моделей нет.
# ВАЖНО (владелец): контакты в базе обзвона — от старой версии Зенки, неполные; поэтому здесь контакты только считаются,
# полный сбор — на этапе 4 (обход сайта). Итог — kc1-otbor.jsonl (fsync) + дроп.
import collections, io, json, os, re, shutil, sqlite3, time
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
ВЫХ = os.path.join(DIR, 'kc1-otbor.jsonl')
ГР = {'винтовые': 1, 'мкс': 2, 'генераторы': 3, 'дизельные_центробежные': 4}
РУЧНЫЕ_4 = {'42.11': 'дороги', '42.12': 'ж/д пути', '42.13': 'мосты, тоннели', '42.21': 'трубопроводы, сети',
            '42.22': 'ЛЭП, сети связи', '42.91': 'гидротехника', '42.99': 'прочие инж. сооружения', '43.11': 'снос зданий',
            '43.12': 'подготовка площадок', '43.13': 'разведочное бурение', '43.99': 'спецработы в строительстве',
            '08.11': 'добыча камня, песка', '08.12': 'карьеры щебня, гравия', '09.90': 'услуги в горнодобыче',
            '36.00': 'водоснабжение', '37.00': 'водоотведение', '41.20': 'строительство зданий'}


def код(s):
    м = re.match(r'\s*(\d{2}(?:\.\d{1,2}){0,3})', str(s or ''))
    return м.group(1) if м else ''


def совпал(c, L):
    return bool(c and L) and (c == L or c.startswith(L + '.') or L.startswith(c + '.'))


def main():
    t0 = time.time()
    св = json.load(io.open(os.path.join(DIR, 'kc0-svodka.json'), encoding='utf-8'))
    списки = []  # (код, группа, ярус, пояснение)
    for г, д in св['группы'].items():
        for к, мм in д.get('оквэд', []):
            списки.append((к, ГР[г], 'основной' if len(мм) >= 2 else 'пробный', '%d модел.' % len(мм)))
    for к, п in РУЧНЫЕ_4.items():
        списки.append((к, 4, 'основной', 'вручную: ' + п))
    c = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True, timeout=120)
    cur = c.execute('select division, base_label, inn, name_short, status, region, okved_main, okved_all_codes, revenue_rub, '
                    'sites, phones_base, emails_base, phones_site, emails_site, director, equip_categories, priority_max from obzvon')
    поля = [d[0] for d in cur.description]
    out, видели, сч = [], set(), collections.Counter()
    for r in cur:
        x = dict(zip(поля, r))
        i = str(x['inn'] or '')
        сч['строк'] += 1
        if not i or i in видели:
            continue
        видели.add(i)
        if 'ликвид' in (x['status'] or '').lower() or 'прекрат' in (x['status'] or '').lower() or 'банкрот' in (x['status'] or '').lower():
            сч['не действует'] += 1
            continue
        осн = код(x['okved_main'])
        доп = [код(k) for k in (x['okved_all_codes'] or '').split('|') if код(k)]
        hits = []
        for L, г, ярус, пояс in списки:
            if совпал(осн, L):
                hits.append((г, ярус, 'основной ОКВЭД', L, пояс))
            elif any(совпал(d, L) for d in доп if d != осн):
                hits.append((г, ярус, 'доп. ОКВЭД', L, пояс))
        if not hits:
            continue
        # лучшее совпадение по каждой группе: основной список > пробный, основной ОКВЭД > доп.
        лучш = {}
        for h in hits:
            вес = (h[1] == 'основной') * 2 + (h[2] == 'основной ОКВЭД')
            if h[0] not in лучш or вес > лучш[h[0]][0]:
                лучш[h[0]] = (вес, h)
        try:
            выр = float(x['revenue_rub'] or 0)
        except ValueError:
            выр = 0.0
        почты = {a.strip().lower() for f in ('emails_base', 'emails_site') for a in (x[f] or '').split('|') if '@' in a}
        тел = {re.sub(r'\D', '', a) for f in ('phones_base', 'phones_site') for a in (x[f] or '').split('|') if re.sub(r'\D', '', a)}
        z = {'инн': i, 'база': x['division'], 'имя': x['name_short'], 'регион': x['region'], 'оквэд': x['okved_main'],
             'выручка': выр, 'сайт': (x['sites'] or '').split('|')[0].strip(), 'директор': x['director'] or '',
             'почт_в_базе': len(почты), 'тел_в_базе': len(тел), 'оборуд_базы': x['equip_categories'] or '',
             'приоритет_базы': x['priority_max'] or '',
             'группы': {str(г): {'ярус': h[1], 'как': h[2], 'код': h[3], 'пояснение': h[4], 'вес': в} for г, (в, h) in sorted(лучш.items())}}
        z['лучший_вес'] = max(в for в, _ in лучш.values())
        out.append(z)
        сч['отобрано'] += 1
    c.close()
    with io.open(ВЫХ, 'w', encoding='utf-8') as f:
        for z in out:
            f.write(json.dumps(z, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())
    shutil.copyfile(ВЫХ, os.path.join(ДРОП, os.path.basename(ВЫХ)))
    по_гр = collections.Counter()
    for z in out:
        for г, v in z['группы'].items():
            по_гр['%s/%s/%s' % (г, v['ярус'], v['как'])] += 1
    print('===ИТОГ===', json.dumps({'счёт': сч, 'по_группам': dict(sorted(по_гр.items())),
                                    'с_сайтом': sum(1 for z in out if z['сайт'])}, ensure_ascii=False),
          'за %.1f мин' % ((time.time() - t0) / 60))


if __name__ == '__main__':
    main()
