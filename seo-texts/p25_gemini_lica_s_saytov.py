# -*- coding: utf-8 -*-
"""Модель читает страницу контактов и достаёт СВЯЗКУ «ФИО + должность + номер».

Зачем модель, если есть регулярка. Регулярка вынимает номера, но не знает, ЧЕЙ номер. На
странице контактов рядом стоят приёмная, факс, отдел сбыта, телефон разработчика сайта в
подвале и мобильный главного энергетика — все одного вида. Связку «этот номер принадлежит
этому человеку в этой должности» даёт только чтение, и это ровно то, что владелец просил
делать через провайдера («продолжай на гемини»).

ЗАСЛОН НА ВЫДУМКУ, и он здесь главный. Модель охотно сочиняет правдоподобное: допишет
отчество, придумает добавочный, соберёт номер из двух соседних. Поэтому каждый её ответ
проверяется ПРОТИВ ИСХОДНОГО ТЕКСТА:

    номер   — цифры номера должны стоять в тексте страницы подряд (без разделителей);
    почта   — должна встречаться в тексте буквально;
    ФИО     — фамилия должна встречаться в тексте буквально.

Не прошло — строка снимается, причина считается. Доля снятого печатается: это и есть
отрицательный контроль на самого разборщика, без которого его числам верить нельзя.

ВИД НОМЕРА НАЗЫВАЕТСЯ ЯВНО, по правилу владельца «разделять, а не отсеивать». Приёмная и
8-800 не выбрасываются — они путь к человеку через коммутатор; они просто помечены своим
видом и лежат отдельно от личных мобильных.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as gp  # noqa: E402

# МОДЕЛЬ ВЫБИРАЕТСЯ ЗАМЕРОМ, А НЕ ПОЖЕЛАНИЕМ. Владелец просил идти на gemini, но шлюз на
# оба имени отвечает 503 «No available channel for model … under group default»: канала под
# эти модели у него сейчас нет. Это ответ шлюза, а не моя догадка — короткая проба тремя
# именами: gemini-3.1-pro-preview 503, gemini-3.6-flash 503, gemini-3-pro-preview 404,
# claude-fable-5 ответила. Поэтому список кандидатов пробуется по порядку, и в каждой строке
# результата пишется, КАКАЯ модель её разобрала: подменить модель молча — значит соврать
# в провенансе.
KANDIDATY = [x for x in os.environ.get('P25_MODEL', 'gemini-3.6-flash,gemini-3.1-pro-preview,'
                                       'claude-fable-5').split(',') if x.strip()]
MODEL = KANDIDATY[0]
VHOD_IMYA = 'PARK-SAYTY-TEKST-3S.jsonl'
VYHOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PARK-SAYTY-LICA-3S.jsonl')
POTOKOV = int(os.environ.get('P25_POTOKOV', '6'))
SKOLKO = int(os.environ.get('P25_SKOLKO', '400'))
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PROMPT = '''Ты разбираешь текст страницы контактов российского промышленного предприятия.

Верни ТОЛЬКО JSON-массив, без пояснений и без markdown-обёртки. Каждый элемент:
{"fio": "...", "dolzhnost": "...", "telefon": "...", "dobavochnyy": "...", "pochta": "...",
 "vid": "личный мобильный|рабочий прямой|приёмная|общий телефон предприятия|8-800|факс"}

Правила, нарушение любого делает ответ негодным:
1. Бери ТОЛЬКО то, что буквально написано в тексте. Ничего не достраивай: нет отчества —
   пиши как есть; не знаешь должность — пустая строка.
2. Номер записывай ровно теми цифрами, что стоят в тексте.
3. Человека без номера тоже возвращай (телефон пустой) — имя и должность сами по себе ценны.
4. Номер без человека возвращай с пустым fio, но обязательно назови вид: приёмная, факс,
   8-800, общий телефон предприятия.
5. Не бери телефоны разработчика сайта, поставщиков, партнёров и служб поддержки хостинга.
6. Мобильный вид (9xx) называй «личный мобильный» ТОЛЬКО если он стоит рядом с именем
   конкретного человека. Мобильный без имени — это «общий телефон предприятия».

Текст страницы:
'''


def s_dropa(imya):
    return op.open(urllib.request.Request('%s/%s' % (drop, imya), headers=tok),
                   timeout=180).read().decode('utf-8', 'replace')


def cifry(t):
    return re.sub(r'\D', '', str(t or ''))


zapisi = []
for s in s_dropa(VHOD_IMYA).splitlines():
    try:
        o = json.loads(s)
    except Exception:  # noqa: BLE001
        continue
    if o.get('tekst'):
        zapisi.append(o)
zapisi = zapisi[:SKOLKO]

zamok = threading.Lock()
ochered = list(zapisi)
potok, snyato, sch = [], collections.Counter(), {'sprosheno': 0, 'sboev': 0, 'vernula': 0}
klient = gp.make_client()


def tekst_otveta(msg):
    """gp.call отдаёт объект с блоками, а не строку. Первый заход об это и споткнулся."""
    if isinstance(msg, str):
        return msg
    out = []
    for b in getattr(msg, 'content', []) or []:
        if getattr(b, 'type', '') == 'text':
            out.append(getattr(b, 'text', '') or '')
    return ''.join(out)


def razobrat(z):
    tekst = z['tekst'][:14000]
    otvet, model_dala = '', ''
    for m in KANDIDATY:
        try:
            otvet = tekst_otveta(gp.call(klient, [{'role': 'user', 'content': PROMPT + tekst}],
                                         model=m, attempts=1))
            model_dala = m
            break
        except Exception as e:  # noqa: BLE001
            with zamok:
                snyato['%s не ответила: %s' % (m, str(e)[:34])] += 1
    if not otvet:
        with zamok:
            sch['sboev'] += 1
        return
    z['_model'] = model_dala
    m = re.search(r'\[.*\]', otvet or '', re.S)
    if not m:
        with zamok:
            snyato['ответ без JSON-массива'] += 1
        return
    try:
        spisok = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        with zamok:
            snyato['битый JSON в ответе'] += 1
        return
    tekst_cifry = cifry(tekst)
    tekst_niz = tekst.lower()
    with zamok:
        sch['sprosheno'] += 1
        sch['vernula'] += len(spisok)
        for o in spisok if isinstance(spisok, list) else []:
            if not isinstance(o, dict):
                continue
            fio = re.sub(r'\s+', ' ', str(o.get('fio') or '')).strip()
            tel = cifry(o.get('telefon'))
            pochta = str(o.get('pochta') or '').strip().lower()
            # ЗАСЛОН 1: фамилия обязана стоять в тексте буквально
            if fio:
                fam = fio.split()[0]
                if len(fam) < 4 or fam.lower() not in tekst_niz:
                    snyato['ФИО в тексте страницы нет — снимаю'] += 1
                    continue
            # ЗАСЛОН 2: цифры номера обязаны стоять в тексте подряд
            if tel:
                hvost = tel[-10:] if len(tel) >= 10 else tel
                if len(hvost) < 6 or hvost not in tekst_cifry:
                    snyato['номера в тексте страницы нет — снимаю'] += 1
                    continue
            # ЗАСЛОН 3: почта обязана стоять в тексте буквально
            if pochta and pochta not in tekst_niz:
                snyato['почты в тексте страницы нет — снимаю'] += 1
                continue
            if not fio and not tel and not pochta:
                snyato['пустая строка'] += 1
                continue
            vid = str(o.get('vid') or '').strip() or 'вид не назван'
            # Моя проверка поверх модели: 9xx без имени личным быть не может, как бы модель
            # его ни назвала. Правило владельца — вид номера должен быть назван честно.
            if tel and len(tel) >= 10 and tel[-10] == '9' and fio:
                vid_moy = 'ЛИЧНЫЙ МОБИЛЬНЫЙ'
            elif tel and len(tel) >= 10 and tel[-10] == '9':
                vid_moy = 'мобильный без имени — общий'
            elif tel and tel.startswith(('8800', '78800')):
                vid_moy = '8-800'
            elif tel:
                vid_moy = 'городской, вид по модели: %s' % vid[:30]
            else:
                vid_moy = 'номера нет, только имя'
            potok.append({'inn': z.get('inn', ''), 'chelovek': fio,
                          'dolzhnost': str(o.get('dolzhnost') or '')[:120],
                          'nomer': ('+7' + tel[-10:]) if len(tel) >= 10 else tel,
                          'dobavochnyy': str(o.get('dobavochnyy') or '')[:12],
                          'pochta': pochta, 'vid_nomera': vid_moy,
                          'vid_po_modeli': vid[:40],
                          'istochniki': z.get('ssylka', ''), 'istochnikov': 1,
                          'kto': '3-я сессия, сайт предприятия, разбор моделью %s'
                                 % (z.get('_model') or MODEL)})


def rabotnik():
    while True:
        with zamok:
            if not ochered:
                return
            z = ochered.pop(0)
        try:
            razobrat(z)
        except Exception as e:  # noqa: BLE001
            with zamok:
                snyato['исключение: %s' % str(e)[:40]] += 1


nitki = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in nitki:
    n.start()
for n in nitki:
    n.join()

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:90]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:70]

lich = [o for o in potok if o['vid_nomera'] == 'ЛИЧНЫЙ МОБИЛЬНЫЙ']
s_imenem = [o for o in potok if o['chelovek']]
print('\n\n########## ЛИЧНЫЕ МОБИЛЬНЫЕ, ПО ОДНОМУ')
for o in lich[:12]:
    print('  %-12s %-26s %-28s %s' % (o['inn'], o['chelovek'][:26], o['dolzhnost'][:28],
                                      o['nomer']))
print('\n########## ЧИСЛА')
print('  страниц во входе                  %5d' % len(zapisi))
print('  спрошено у модели                 %5d  (сбоев %d)' % (sch['sprosheno'], sch['sboev']))
print('  строк модель вернула              %5d' % sch['vernula'])
print('  строк прошло заслоны              %5d' % len(potok))
print('  --- снято заслонами (это и есть контроль на выдумку)')
for k, v in snyato.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('  людей с именем                    %5d' % len(s_imenem))
print('  ЛИЧНЫХ МОБИЛЬНЫХ с именем         %5d  на %d предприятиях'
      % (len(lich), len({o['inn'] for o in lich})))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'страниц': len(zapisi), 'вернула': sch['vernula'],
                            'прошло': len(potok), 'личных': len(lich)}, ensure_ascii=False))
