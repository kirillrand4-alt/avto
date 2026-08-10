# -*- coding: utf-8 -*-
"""Пересев отвала. Заслон общих запросов сначала выбрасывал «Поставка комплекса
подготовки сжатого воздуха» — а это ровно наша обвязка. Слова добавлены; отвал писался
в файл именно ради этого: пересеиваем без повторного обхода ЕИС.

Ничего не удаляем: то, что прошло новый заслон, дописывается в основной поток
park_obshchie.jsonl с пометкой, что пришло из пересева.
"""
import json, os, re, time
BAZA = r'C:\sender'
OTVAL = os.path.join(BAZA, 'park_obshchie_otval.jsonl')
OUT = os.path.join(BAZA, 'park_obshchie.jsonl')
NASHE = re.compile(
    r'компрессор|воздуходувк|газодувк|турбокомпрессор|нагнетател|воздухораздел|'
    r'(генератор\w{0,4}(азота|кислорода))|(азотн\w{0,4}станци)|(кислородн\w{0,4}станци)|'
    r'ресивер|осушител|(винтов\w{0,4}(блок|пар))|компрессорн|мотокомпрессор|'
    r'(сжат\w{0,4}воздух)|воздухосборник|пневмосет|влагоотделител|маслоотделител|'
    r'(концев\w{0,4}холодильник)|(дожимн\w{0,4}(компрессор|станци|установк))|'
    r'(азотн\w{0,4}установк)|(кислородн\w{0,4}установк)|(криогенн\w{0,4}(установк|блок))|'
    r'(мембранн\w{0,4}(азот|газоразделит))|(адсорбцион\w{0,4}(азот|кислород))|'
    r'воздухоснабжен|(станци\w{0,4}компримирован)|компримирован')
CHUZHOE = re.compile(
    r'стоматолог|аквариум|(медицинск\w{0,4}компрессор)|(компрессор\w{0,4}(матрас|ингалятор|'
    r'небулайзер|тонометр))|(садов\w{0,4}воздуходувк)|ранцев|(бытов\w{0,4}компрессор)|'
    r'(автомобильн\w{0,4}компрессор)|(холодильн\w{0,4}(витрин|ларь|шкаф|агрегат))|'
    r'(компрессор\w{0,4}кондиционер)|(компрессор\w{0,4}холодильник)|автошин|'
    r'(компрессор\w{0,4}сплит)')


def bp(t):
    return re.sub(r'\s+', '', (t or '').lower().replace('\u0451', '\u0435'))


def kartochka(n):
    if len(n) == 11:
        return 'https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber=' + n
    return 'https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=' + n


est = set()
if os.path.exists(OUT):
    for ln in open(OUT, encoding='utf-8', errors='replace'):
        try:
            est.add(json.loads(ln)['nomer'])
        except Exception:
            pass
vsego = vernuto = 0
paket = []
for ln in open(OTVAL, encoding='utf-8', errors='replace'):
    try:
        d = json.loads(ln)
    except Exception:
        continue
    vsego += 1
    if d['nomer'] in est:
        continue
    n = bp(d.get('predmet'))
    if NASHE.search(n) and not CHUZHOE.search(n):
        est.add(d['nomer'])
        paket.append({'nomer': d['nomer'], 'zakazchik': d.get('zakazchik', ''),
                      'predmet': d.get('predmet', ''), 'zapros': d.get('zapros', ''),
                      'okno': d.get('okno', ''), 'ssylka_kartochka': kartochka(d['nomer']),
                      'os': 'парк машин',
                      'kto': '1-я сессия, пересев отвала расширенным заслоном',
                      'ts': time.strftime('%Y-%m-%d %H:%M:%S')})
        vernuto += 1
if paket:
    with open(OUT, 'a', encoding='utf-8') as f:
        for s in paket:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
print(json.dumps({'otvala_prosmotreno': vsego, 'vernuto_v_potok': vernuto,
                  'primery': [s['predmet'][:80] for s in paket[:6]]}, ensure_ascii=False))
