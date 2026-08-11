# -*- coding: utf-8 -*-
"""ИНН для строк площадок — ПО ДОМЕНУ ПОЧТЫ. Ключ надёжнее названия организатора.

ЗАЧЕМ. На карточках ТЭК-Торга ИНН напечатан у 16 строк из 102, а человек назван у 92. Без ИНН
строку не к чему привязать, и 92 живых человека с телефонами лежат мимо базы. Название
организатора на карточке даётся не всегда и в разной форме, зато ПОЧТА есть у всех 102 строк,
и домен в ней называет предприятие прямо:

    KuzminaNB@azp.rosneft.ru   -> azp.rosneft.ru
    ...@sibur.ru               -> sibur.ru

ЧТО ДЕЛАЮ. Собираю справочник «домен -> ИНН» из ЖИВОЙ базы (`PARK-BAZA-EDINAYA-3S.csv`):
домены почт и домены ссылок на сайт предприятия. Затем строкам площадок без ИНН ставлю ИНН,
если домен ведёт РОВНО К ОДНОМУ предприятию.

ЗАСЛОНЫ, и каждый из них уже стоил кому-то ошибки:
  • почтовые службы общего пользования (mail.ru, yandex, gmail, bk, list, inbox, rambler…)
    предприятие НЕ называют — такие домены выброшены из справочника целиком;
  • домен, ведущий к ДВУМ и более ИНН, не используется: это не доказательство, а совпадение;
  • поддомен приводится к своему корню только на два уровня (azp.rosneft.ru -> rosneft.ru
    НЕ делаю: дочернее предприятие имеет свой ИНН, и слияние их потеряло бы разницу);
  • источник пометки называется явно: `inn_otkuda = "домен почты совпал с базой"`.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: к строкам подмешивается выдуманный домен `@shvarckopfer-zavod.ru`.
Если ему найдётся ИНН — справочник склеивает что попало, и числам верить нельзя.

Числа в КОНЦЕ.
"""
import collections
import csv
import io
import json
import os
import re
import urllib.request

SCRATCH = os.environ.get('P25_SCRATCH', '.')
BAZA = os.path.join(SCRATCH, 'PARK-BAZA-EDINAYA-3S.csv')
FAJLY = ['PARK-TEKTORG-ZAKUPKI-3S.jsonl', 'PARK-ROSELTORG-ZAKUPKI-3S.jsonl']
OBSHCHIE = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru', 'inbox.ru',
            'rambler.ru', 'mail.com', 'internet.ru', 'yahoo.com', 'outlook.com', 'icloud.com',
            'hotmail.com', 'narod.ru', 'gmail.ru', 'ymail.com'}
KONTROL = 'shvarckopfer-zavod.ru'
# ЗАСЛОН НА УПОЛНОМОЧЕННЫЙ ОРГАН. Нашёлся глазами при разборе первых десяти сшитых строк:
# домен `goszakazyakutia.ru` ведёт к ГКУ «Госзакупки Якутии» — это площадка-организатор, а
# машина встанет у школы или больницы, для которых он закупает. Домен сшит верно, а вывод
# был бы ложным: предприятие не то. Тот же класс, что заслон посредника в приёмнике парка,
# только там он смотрит на имя заказчика, а здесь имени нет — смотрю на имя из справочника.
POSREDNIK = re.compile(r'госзаказ|госзакуп|уполномоченн\w+ орган|комитет\w* .{0,30}закупк|'
                       r'управлени\w* .{0,30}закупк|центр\w* .{0,20}закупок|'
                       r'агентств\w+ (государственн|муниципальн)|дирекци\w* .{0,20}закупок',
                       re.I)
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def domen(s):
    s = str(s or '').strip().lower()
    if '@' in s:
        return s.split('@')[-1].strip(' .,;')
    m = re.match(r'^https?://([^/]+)', s)
    return m.group(1).replace('www.', '') if m else ''


spravochnik = collections.defaultdict(set)
imya_po_inn = {}
posredniki = set()
sch = collections.Counter()
with io.open(BAZA, encoding='utf-8-sig') as f:
    for r in csv.DictReader(f, delimiter=';'):
        inn = (r.get('inn') or '').strip()
        if not inn:
            continue
        imya = (r.get('predpriyatie') or '')
        if imya and inn not in imya_po_inn:
            imya_po_inn[inn] = imya
            if POSREDNIK.search(imya):
                posredniki.add(inn)
        d = domen(r.get('pochta'))
        if d and d not in OBSHCHIE:
            spravochnik[d].add(inn)
        for u in str(r.get('istochniki') or '').split(' | '):
            d2 = domen(u)
            if d2 and d2 not in OBSHCHIE and not d2.endswith('.gov.ru') \
                    and 'zakupki' not in d2 and 'tektorg' not in d2 and 'roseltorg' not in d2 \
                    and 'monitor-pb' not in d2 and 'etpgpb' not in d2 and 'tender.pro' not in d2 \
                    and 'checko' not in d2 and 'rts-tender' not in d2:
                spravochnik[d2].add(inn)
odnoznachnye = {d: list(v)[0] for d, v in spravochnik.items() if len(v) == 1}
sch['доменов в справочнике'] = len(spravochnik)
sch['предприятий-посредников в справочнике'] = len(posredniki)
sch['   из них ведут ровно к одному ИНН'] = len(odnoznachnye)
sch['   ведут к нескольким ИНН — не годятся'] = len(spravochnik) - len(odnoznachnye)

itogo = collections.Counter()
for imya in FAJLY:
    put = os.path.join(SCRATCH, imya)
    if not os.path.exists(put):
        itogo['НЕТ ФАЙЛА: %s' % imya] += 1
        continue
    stroki = []
    for s in io.open(put, encoding='utf-8'):
        try:
            z = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if not str(z.get('inn') or '').strip():
            d = domen(z.get('pochta'))
            if not d:
                itogo['%s: почты нет — сшить не по чему' % imya[:12]] += 1
            elif d in OBSHCHIE:
                itogo['%s: почта общей службы — предприятие не названо' % imya[:12]] += 1
            elif d in odnoznachnye and odnoznachnye[d] in posredniki:
                itogo['%s: ЗАСЛОН: домен ведёт к уполномоченному органу' % imya[:12]] += 1
            elif d in odnoznachnye:
                z['inn'] = odnoznachnye[d]
                z['inn_otkuda'] = 'домен почты совпал с базой: %s' % d
                itogo['%s: ИНН ПОСТАВЛЕН по домену' % imya[:12]] += 1
            else:
                itogo['%s: домена нет в базе' % imya[:12]] += 1
        stroki.append(z)
    with io.open(put, 'w', encoding='utf-8') as f:
        for z in stroki:
            f.write(json.dumps(z, ensure_ascii=False) + '\n')
    itogo['%s: строк всего' % imya[:12]] = len(stroki)
    itogo['%s: с ИНН стало' % imya[:12]] = len([z for z in stroki if z.get('inn')])
    try:
        rq = urllib.request.Request('%s/%s' % (drop, imya), data=io.open(put, 'rb').read(),
                                    method='PUT', headers=tok)
        op.open(rq, timeout=300).read()
        itogo['%s: выложен' % imya[:12]] = 1
    except Exception as e:  # noqa: BLE001
        print('НЕ ВЫЛОЖЕН %s: %s' % (imya, str(e)[:50]))

print('\n\n########## ЧИСЛА')
for k, v in sch.most_common():
    print('  %-52s %5d' % (k[:52], v))
for k, v in itogo.most_common():
    print('  %-52s %5d' % (k[:52], v))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ (выдуманный домен %s): %s'
      % (KONTROL, 'ИНН НЕ нашёлся — справочник не склеивает что попало'
         if KONTROL not in odnoznachnye else 'НАШЁЛСЯ ИНН — СПРАВОЧНИКУ ВЕРИТЬ НЕЛЬЗЯ'))
print('ИТОГ ' + json.dumps({'доменов однозначных': len(odnoznachnye),
                            'ИНН поставлено': sum(v for k, v in itogo.items()
                                                  if 'ИНН ПОСТАВЛЕН' in k),
                            'контроль чист': KONTROL not in odnoznachnye},
                           ensure_ascii=False))
