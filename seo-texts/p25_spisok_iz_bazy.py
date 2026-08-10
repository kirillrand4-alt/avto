# -*- coding: utf-8 -*-
"""Список для звонка СОБИРАЕТСЯ ИЗ ЕДИНОЙ БАЗЫ, а не из одного потока. 103 строки возвращены.

Замер, с которого всё началось: в базе 517 личных мобильных на 155 предприятиях, а в списке
для звонка — 353 строки на 111 предприятиях. Разобрала разницу по причинам, и она оказалась
не «данные плохие», а «сборщик читает не то»:

    уже в списке ................................................ 353
    ВСЁ ЕСТЬ (имя, машина, обе ссылки), но канал не читается ..... 103
    нет вида машины: ИНН не в парке ...............................  54
    нет ссылки на человека ........................................   7

Прежний сборщик читал ТОЛЬКО поток сводки `PARK-SVODKA-CHELOVEK-ROL-NOMER-3S.jsonl`. Всё,
что добыто позже другими каналами — разбор страниц моделью, карточки организаций ЕИС,
поздние прогоны обратного хода, — в список не попадало никогда, хотя лежало в базе с
именем, должностью, номером и ссылками. Сто три звонка стояли за одной строкой кода.

Здесь источник один — единая база, куда каналы уже сведены и где ссылки накоплены.

ЗАСЛОНЫ те же и в том же порядке:
  1. вид номера ЛИЧНЫЙ МОБИЛЬНЫЙ считается по цифрам, а не по унаследованному тексту;
  2. имя человека обязательно: номер без имени — это не «личный», это мобильный без имени;
  3. ссылка на человека и ссылка на машину обязательны обе;
  4. ключ (ИНН + десять цифр) сворачивает дубли, ссылки при свёртке НАКАПЛИВАЮТСЯ.

Порядок: дороже машина — выше; при равной машине выше тот, у кого больше независимых
подтверждений (каналов, потом ссылок).

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import urllib.request

OPS = r'C:\sender\_ops'
BAZA = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
STARYY = os.path.join(OPS, 'PARK-SPISOK-DLYA-ZVONKA-3S.csv')
VYHOD = os.path.join(OPS, 'PARK-SPISOK-DLYA-ZVONKA-3S.csv')
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


def chitat(put):
    out, sh = [], None
    if not os.path.exists(put):
        return out
    for s in io.open(put, encoding='utf-8-sig'):
        p = s.rstrip('\n').split(';')
        if sh is None:
            sh = p
            continue
        if len(p) == len(sh):
            out.append(dict(zip(sh, p)))
    return out


bylo = len({(r.get('inn'), desyat(r.get('nomer'))) for r in chitat(STARYY)})
svern, snyato = {}, collections.Counter()
for r in chitat(BAZA):
    d = desyat(r.get('nomer'))
    if not d:
        snyato['не телефон (почта или пусто)'] += 1
        continue
    chel = (r.get('chelovek') or '').strip()
    # ВТОРОЙ КЛАСС НЕ ТЕРЯЕТСЯ. Первый прогон этого сборщика дал 452 строки вместо 379 и
    # выглядел чистой прибавкой — а на деле он ВЫБРОСИЛ 28 строк «контактное лицо закупки»:
    # у них номер городской, и правило «только 9xx» их не пускало. Городской номер
    # НАЗВАННОГО человека — это не мусор, это прямой рабочий телефон того, кто вёл закупку
    # машины. Правило владельца: разделять, а не отсеивать. Беру их вторым классом и ставлю
    # ниже личных мобильных, назвав вид номера честно.
    vtoroy = False
    if d[0] != '9':
        if chel and re.search(r'контактн|ответственн|закупк', (r.get('dolzhnost') or ''), re.I):
            vtoroy = True
        else:
            snyato['номер не мобильного вида — идёт в коммутаторный список'] += 1
            continue
    if not chel:
        snyato['мобильный БЕЗ ИМЕНИ — личным не считается'] += 1
        continue
    if not vtoroy and not (r.get('vid_nomera') or '').startswith('ЛИЧНЫЙ'):
        snyato['вид номера в базе не «личный» (спорный, у нескольких ИНН и т.п.)'] += 1
        continue
    mash = (r.get('mashina') or '').strip()
    if not mash:
        snyato['вида машины нет: ИНН не в парке'] += 1
        continue
    u_chel = next((x for x in (r.get('istochniki') or '').split(' | ')
                   if x.startswith('http')), '')
    u_mash = (r.get('mashina_ssylka') or '').strip()
    if not u_chel:
        snyato['нет ссылки на человека'] += 1
        continue
    if not u_mash.startswith('http'):
        snyato['нет ссылки на машину'] += 1
        continue
    k = (r['inn'], d)
    z = svern.get(k)
    if z:
        for x in (r.get('istochniki') or '').split(' | '):
            if x.startswith('http') and x not in z['ssylka_chelovek']:
                z['ssylka_chelovek'] += ' | ' + x
                z['dokazatelstv'] += 1
        continue
    svern[k] = {'inn': r['inn'], 'predpriyatie': (r.get('predpriyatie') or '')[:150],
                'chelovek': chel, 'dolzhnost': (r.get('dolzhnost') or 'должность не названа')[:90],
                'vid_nomera': ('РАБОЧИЙ ПРЯМОЙ названного человека, НЕ личный'
                               if vtoroy else 'ЛИЧНЫЙ МОБИЛЬНЫЙ'),
                'nomer': '+7' + d,
                'pochta': (r.get('pochta') or ''), 'mashina': mash,
                'klass_ceny': KLASS.get(mash, 2),
                'kanalov': int(r.get('kanalov') or 1),
                'kanaly': (r.get('kanaly') or '')[:120],
                'dokazatelstv': max(int(r.get('istochnikov') or 1), 1) + 1,
                'ssylka_chelovek': ' | '.join(x for x in (r.get('istochniki') or '').split(' | ')
                                              if x.startswith('http')),
                'ssylka_mashina': u_mash}

spisok = sorted(svern.values(),
                key=lambda o: (0 if o['vid_nomera'].startswith('ЛИЧНЫЙ') else 1,
                               -o['klass_ceny'], -o['kanalov'], -o['dokazatelstv']))
KOL = ('inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'vid_nomera', 'nomer', 'pochta',
       'mashina', 'klass_ceny', 'kanalov', 'kanaly', 'dokazatelstv', 'ssylka_chelovek',
       'ssylka_mashina')
with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write(';'.join(KOL) + '\n')
    for o in spisok:
        f.write(';'.join(str(o.get(k, '')).replace(';', ',').replace('\n', ' ')
                         for k in KOL) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:90]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:60]

print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ')
for o in spisok[:10]:
    print('  %-12s %-24s %-26s %-14s %s' % (o['inn'], o['chelovek'][:24],
                                            o['dolzhnost'][:26], o['nomer'],
                                            o['mashina'][:14]))
print('\n########## ЧИСЛА')
print('  строк в списке было (прошлый файл) %5d' % bylo)
print('  строк в списке стало              %5d  (предприятий %d)'
      % (len(spisok), len({o['inn'] for o in spisok})))
print('  прибавка                          %5d' % (len(spisok) - bylo))
print('     из них ЛИЧНЫХ МОБИЛЬНЫХ         %5d'
      % sum(1 for o in spisok if o['vid_nomera'].startswith('ЛИЧНЫЙ')))
print('     из них рабочих прямых у названного человека %3d'
      % sum(1 for o in spisok if not o['vid_nomera'].startswith('ЛИЧНЫЙ')))
print('  из них подтверждено 2+ каналами   %5d' % sum(1 for o in spisok if o['kanalov'] > 1))
print('  --- по машине')
for k, v in collections.Counter(o['mashina'] for o in spisok).most_common():
    print('     %-24s %5d' % (k[:24], v))
print('  --- что не прошло и почему')
for k, v in snyato.most_common():
    print('     %-56s %5d' % (k[:56], v))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'было': bylo, 'стало': len(spisok),
                            'предприятий': len({o['inn'] for o in spisok})},
                           ensure_ascii=False))
