# -*- coding: utf-8 -*-
# 13.10, владелец: «у нас деление по компании: если у компании есть сделка, она исключается, при том можно писать другим
# компаниям холдинга». 171 компания ушла в «Не вошли» по правилу «сайт принадлежит клиенту с активной сделкой» — своей
# сделки у них нет. Вернуть; модель делит: «своя»/«группа» (сайт её или холдинга, куда она входит) — контакты остаются,
# пометка о сделке у холдинга; «чужой» (тёзка/не связана — как воронежский «Агро Альянс» с сайтом холдинга) — контакты
# этого сайта снимаются (это контакты клиента), компания остаётся; «неясно» — остаётся с пометкой.
# Цели — meyer7-kholding-celi.jsonl с дропа. Итог — meyer7-kholding-chleny.jsonl + дроп.
import collections, io, json, os, re, sys, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender'); os.chdir(DIR)
os.environ.update({'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna'})
import pilot_konveyer as PK  # noqa: E402
os.environ.update(PK.Волны().env_шага('kc_kontakty.py'))
import kc_kontakty as KK  # noqa: E402
import _inn_zamer_meyer7 as Z  # noqa: E402
import sqlite3  # noqa: E402
print('===ИТОГ===', time.strftime('%H:%M:%S'))
цели = [json.loads(s) for s in io.open(r'C:\seostat\drop\drop-storage\meyer7-kholding-celi.jsonl', encoding='utf-8') if s.strip()]
сд = {x['инн_сделки'] for x in цели}
имя_сд = {}
for бд, q in ((r'C:\sender\obzvon-index.db', 'select inn, name_short, region, okved_main from obzvon'),
              (r'C:\sender\enrich.db', 'select inn, name, region, okved from companies')):
    c = sqlite3.connect('file:%s?mode=ro' % бд.replace('\\', '/'), uri=True, timeout=120)
    for i, и, р, о in c.execute(q):
        if str(i) in сд and str(i) not in имя_сд:
            имя_сд[str(i)] = '%s, %s, ОКВЭД %s' % (и or '', р or '', о or '')
    c.close()
карта = json.load(io.open(os.path.join(DIR, 'meyer7-zenno-surrogat.json'), encoding='utf-8'))
сур = collections.defaultdict(list)
for кл, i in карта.items():
    сур[i].append(кл)


def юр_сайта(x):
    r = Z.одна((x['ключ'], x['сайт'] or '', сур.get(x['ключ'], []), {}))
    return list(r['юр'])[:8], list(r['инн'])[:5]


ПР = ('Компания из нашей базы НЕ имеет своей сделки; её сайт принадлежит клиенту (юрлицу сделки) или его холдингу. Реши, '
      'кем компания приходится этому клиенту/холдингу:\n'
      '«своя» — сайт её собственный (клиент сделки — другое юрлицо той же фирмы: ТД, управляющая, переоформление);\n'
      '«группа» — компания входит в тот же холдинг/группу (предприятие, дочка, площадка, филиал группы);\n'
      '«чужой» — компания с холдингом не связана: тёзка, другой регион/профиль, сайт к ней приписан ошибочно;\n'
      '«неясно» — данных мало.\n'
      'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер,"класс":"своя|группа|чужой|неясно","почему":"до 20 слов"}}]\n\n{б}')
out = []


def пачка(п_):
    блоки = []
    for j, x in enumerate(п_, 1):
        юр, инн = юр_сайта(x)
        блоки.append('%d. КОМПАНИЯ: %s, ИНН %s, %s, ОКВЭД %s (%s); как попала к нам: %s\n САЙТ: %s | юрлица на сайте: %s | ИНН на сайте: %s\n'
                     ' КЛИЕНТ СДЕЛКИ: ИНН %s (%s); найден: %s\n Прежние проверки: сайт-проверка «%s»; опровергатель «%s»; строгая «%s»' % (
                         j, x['имя'], x['инн'], x['регион'], x['оквэд'], x['сегм'][:50], x['откуда'][:120], x['сайт'], '; '.join(юр) or '-',
                         ', '.join(инн) or '-', x['инн_сделки'], имя_сд.get(x['инн_сделки'], '?'), x['как'][:120], x['проверка'][:150],
                         x['опровержение'][:150], x['строго'][:120]))
    о = KK.модель(ПР.format(б='\n\n'.join(блоки)), True) or {}
    return [dict(x, класс=(о.get(j) or {}).get('класс') or '', почему_кл=(о.get(j) or {}).get('почему') or '',
                 клиент=имя_сд.get(x['инн_сделки'], '')) for j, x in enumerate(п_, 1)]


from concurrent.futures import ThreadPoolExecutor  # noqa: E402
with ThreadPoolExecutor(6) as ex:
    for р_ in ex.map(пачка, [цели[k:k + 8] for k in range(0, len(цели), 8)]):
        out += р_
ВЫХ = os.path.join(DIR, 'meyer7-kholding-chleny.jsonl')
with io.open(ВЫХ, 'w', encoding='utf-8') as f:
    f.write('\n'.join(json.dumps(x, ensure_ascii=False) for x in out) + '\n')
    f.flush(); os.fsync(f.fileno())
import shutil  # noqa: E402
shutil.copyfile(ВЫХ, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХ)))
print(dict(collections.Counter(x['класс'] for x in out)))
