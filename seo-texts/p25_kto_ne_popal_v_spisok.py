# -*- coding: utf-8 -*-
"""Разбор ОТКАЗОВ: почему 138 контактных лиц ЕИС и 81 человек не попали в список звонка.

Счётчик отказов в сборщике списка печатает причину СЛИТНО:

    «контактное лицо: машина не доказана либо телефон короткий   138»
    «машина у предприятия не доказана                             81»

Слово «либо» — это две разные судьбы под одним ярлыком, и обе поправимы по-разному:

    телефон короткий      номер записан без кода города или это добавочный — чинится
                          разбором строки, а не выбрасыванием
    машина не доказана     у ЭТОГО ИНН машины нет в МОИХ трёх потоках. Но парк собирают
                          три сессии: у соседей есть свои доказанные машины, и ИНН может
                          быть доказан у них. Проверить, а не считать отсутствие приговором.

Правило владельца тут прямое: «разделять, а не отсеивать». Выброшенный контакт заново не
добывается, поэтому каждый отказ должен быть НАЗВАН и, где можно, отменён.

Беру у соседей их выложенные списки парка (доказанные машины со ссылками) и пересчитываю
отказы. Ничего не переписываю в чужих файлах — только читаю.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import urllib.request

PARK = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
        r'C:\sender\_ops\park_ingest_3c.jsonl']
KONT_LICO = r'C:\sender\_ops\PARK-EIS-KONTAKTNOE-LICO-3S.jsonl'
SVODKA = r'C:\sender\_ops\PARK-SVODKA-CHELOVEK-ROL-NOMER-3S.jsonl'
# файлы соседей на дропе: их доказанные машины
SOSEDI = ['PARK-SPISOK-DLYA-ZVONKA-1S.csv', 'SPISOK-OBZVONA-POLNYY.csv',
          'PARK-SROK-EPB-2S.jsonl', 'PARK-OPO-PO-INN-2S.jsonl']
VYHOD = r'C:\sender\_ops\PARK-OTKAZY-RAZOBRANY-3S.jsonl'
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def s_dropa(imya):
    try:
        return op.open(urllib.request.Request('%s/%s' % (drop, imya), headers=tok),
                       timeout=240).read().decode('utf-8-sig', 'replace')
    except Exception as e:  # noqa: BLE001
        print('  не скачался %s: %s' % (imya, str(e)[:60]))
        return ''


moi_mash = {}
for p in PARK:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if o.get('inn'):
            moi_mash.setdefault(o['inn'], o.get('vid') or 'машина')

# машины соседей: ИНН -> (что за машина, ссылка, чей файл)
sosed_mash = {}
for f in SOSEDI:
    syr = s_dropa(f)
    if not syr:
        continue
    if f.endswith('.jsonl'):
        for s in syr.splitlines():
            try:
                o = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            i = str(o.get('inn') or '').strip()
            u = ''
            for k in ('ssylka', 'istochniki', 'istochnik', 'url'):
                v = o.get(k)
                if v and str(v).startswith('http'):
                    u = str(v).split(' | ')[0]
                    break
            if i.isdigit() and i not in sosed_mash:
                sosed_mash[i] = (str(o.get('mashina') or o.get('vid') or 'машина')[:40], u, f)
    else:
        st = syr.splitlines()
        if not st:
            continue
        sh = [x.strip() for x in st[0].split(';')]

        def sto(imena):
            for n in imena:
                if n in sh:
                    return sh.index(n)
            return -1

        ji, jm, ju = sto(['inn']), sto(['mashina', 'vid', 'oborudovanie']), \
            sto(['ssylka_mashina', 'ssylka', 'istochnik'])
        for s in st[1:]:
            p_ = s.split(';')
            if ji < 0 or len(p_) <= ji:
                continue
            i = p_[ji].strip()
            if not i.isdigit() or i in sosed_mash:
                continue
            sosed_mash[i] = ((p_[jm].strip() if 0 <= jm < len(p_) else 'машина')[:40],
                             (p_[ju].strip() if 0 <= ju < len(p_) else ''), f)


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


potok, prichiny = [], collections.Counter()
if os.path.exists(KONT_LICO):
    for s in io.open(KONT_LICO, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        inn = str(o.get('inn') or '').strip()
        syroy = str(o.get('telefon') or '')
        d = desyat(syroy)
        # ДОБАВОЧНЫЙ НЕ ЕСТЬ КОРОТКИЙ НОМЕР. «(4852) 30-40-50 доб. 121» ломался целиком,
        # хотя основной номер там полный. Отрезаю добавочный и меряю то, что осталось.
        dob = ''
        m = re.search(r'(?:доб|вн|ext)\.?\s*(\d{1,5})', syroy, re.I)
        if m:
            dob = m.group(1)
            d = d or desyat(syroy[:m.start()])
        if not d:
            cif = re.sub(r'\D', '', syroy)
            prichiny['телефон не собирается в десять цифр (было %d цифр)'
                     % min(len(cif), 15)] += 1
            continue
        est_moya, est_sosed = inn in moi_mash, inn in sosed_mash
        if est_moya:
            prichiny['машина моя — строка должна была пройти, проверить сборщик'] += 1
            vid, ssyl_m, chey = moi_mash[inn], '', 'мой поток'
        elif est_sosed:
            vid, ssyl_m, chey = sosed_mash[inn]
            prichiny['ОТКАЗ ОТМЕНЁН: машина доказана у соседа (%s)' % chey[:28]] += 1
        else:
            prichiny['машина не доказана ни у меня, ни у соседей'] += 1
            continue
        potok.append({'inn': inn, 'chelovek': o.get('imya') or 'имя не названо',
                      'dolzhnost': 'контактное лицо закупки (рабочий телефон, НЕ личный)',
                      'nomer': '+7' + d, 'dobavochnyy': dob,
                      'vid_nomera': 'РАБОЧИЙ ТЕЛЕФОН КОНТАКТНОГО ЛИЦА, не личный',
                      'mashina': vid, 'mashina_chya': chey,
                      'istochniki': ' | '.join(x for x in
                                               [str(o.get('istochniki') or '').split(' | ')[0],
                                                ssyl_m] if x.startswith('http')),
                      'istochnikov': len([x for x in
                                          [str(o.get('istochniki') or '').split(' | ')[0],
                                           ssyl_m] if x.startswith('http')]),
                      'kto': '3-я сессия, разбор отказов'})

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=240).read().decode('utf-8', 'replace')[:90]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:60]

print('\n\n########## ВОЗВРАЩЁННЫЕ СТРОКИ, ПО ОДНОЙ')
for o in potok[:10]:
    print('  %-12s %-26s %-15s %-18s %s' % (o['inn'], o['chelovek'][:26], o['nomer'],
                                            o['mashina'][:18], o['mashina_chya'][:22]))
print('\n########## ЧИСЛА')
print('  ИНН с машиной у меня        %5d' % len(moi_mash))
print('  ИНН с машиной у соседей     %5d  (из файлов: %s)'
      % (len(sosed_mash), ', '.join(SOSEDI)[:60]))
print('  строк возвращено в оборот   %5d' % len(potok))
for k, v in prichiny.most_common():
    print('     %-58s %5d' % (k[:58], v))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'возвращено': len(potok),
                            'ИНН соседей': len(sosed_mash)}, ensure_ascii=False))
