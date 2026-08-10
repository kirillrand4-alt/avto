# -*- coding: utf-8 -*-
"""ПРОВАЙДЕР по сериям: определить принцип там, где он «не установлен». И проверить дефект.

ДЕФЕКТ, НАЗВАННЫЙ 2-Й СЕССИЕЙ, ПОДТВЕРЖДАЮ ПО КОДУ. `gen_provider.call()` возвращает НЕ
строку, а объект ответа: в `gen_provider.py` строка `return msg` — то есть у вызывающего на
руках `msg`, а текст лежит в блоках `msg.content` (тип `text`). Кто пишет `call(...).strip()`
или ищет в результате JSON как в строке, получает исключение либо пустоту, и пустота потом
читается как «модель ничего не разобрала». Здесь текст берётся правильно:

    tekst = ''.join(b.text for b in msg.content if b.type == 'text')

и это записано отдельной функцией, чтобы дефект не воспроизвёлся в третий раз.

ЧТО РАЗБИРАЕТСЯ. Живой файл `PARK-SLOVAR-EDINYY.csv`: 986 серий из документов и закупок,
принцип назван у 598 (центробежный 549, винтовой 45, поршневой 4), **у 388 стоит «не
установлен»** — их и отдаю провайдеру пачками. Каталожные модели владельца (2 920) не трогаю:
у них принцип уже известен из его же каталога.

ЗАСЛОНЫ НА ОТВЕТ, а не на вопрос:
   • обозначение из ответа обязано быть в отправленной пачке — иначе строка отбрасывается;
   • принцип обязан быть из списка; всё прочее считается как «непонятно»;
   • «не наша машина» — отдельный законный исход, он НЕ смешивается с «непонятно»:
     первое про предмет, второе про недостаток сведений.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: в каждую пачку подмешивается выдуманное обозначение
«ЩВАРЦКОПФЕРЪ-5». Если провайдер назовёт ему принцип уверенно — значит он угадывает, и
числам прогона верить нельзя.

Числа в КОНЦЕ.
"""
import collections
import csv
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G  # noqa: E402

SCRATCH = os.environ.get('P25_SCRATCH', '.')
SLOVAR = os.path.join(SCRATCH, 'PARK-SLOVAR-EDINYY.csv')
VYHOD = os.path.join(SCRATCH, 'PARK-SERII-PRINCIP-PROVAJDER-3S.jsonl')
PACHKA = int(os.environ.get('P25_PACHKA', '25'))
PACHEK = int(os.environ.get('P25_PACHEK', '6'))
MODEL = os.environ.get('P25_MODEL', 'claude-fable-5')
KONTROL = 'ЩВАРЦКОПФЕРЪ-5'
PRINCIPY = {'центробежный', 'винтовой', 'поршневой', 'мембранный', 'роторный', 'спиральный',
            'осевой', 'непонятно'}

PROMPT = '''Ты разбираешь обозначения промышленных машин из российских документов
(заключения экспертизы промышленной безопасности, предметы закупок).

По каждому обозначению скажи:
  princip       — принцип действия компрессора/нагнетателя: центробежный, винтовой,
                  поршневой, мембранный, роторный, спиральный, осевой.
                  Если по обозначению принцип определить нельзя — строго слово: непонятно
  nasha_mashina — true, если это компрессор, воздуходувка, нагнетатель, турбокомпрессор,
                  осушитель сжатого воздуха, генератор азота/кислорода, ВРУ или ГПА;
                  false, если это другая машина (насос, вентилятор, дымосос, турбина,
                  трансформатор и т. п.) или вообще не машина
  pochemu       — короткая причина: по какому признаку обозначения ты так решил

ВАЖНО: не угадывай. Если серия тебе неизвестна — princip: непонятно. Выдуманные и
бессмысленные обозначения обязаны получить непонятно и nasha_mashina: false.

Ответь ТОЛЬКО JSON-массивом без пояснений:
[{"oboznachenie": "...", "princip": "...", "nasha_mashina": true, "pochemu": "..."}]

Обозначения:
%s'''


def tekst_otveta(msg):
    """Текст из ОБЪЕКТА ответа. Тот самый дефект: call() отдаёт msg, а не строку."""
    if isinstance(msg, str):
        return msg
    try:
        return ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception:  # noqa: BLE001
        return ''


def massiv(t):
    """Самый длинный разобравшийся JSON-массив в тексте."""
    luchshiy = []
    nachalo = -1
    while True:
        nachalo = t.find('[', nachalo + 1)
        if nachalo < 0:
            return luchshiy
        for konec in range(len(t), nachalo, -1):
            if t[konec - 1] != ']':
                continue
            try:
                z = json.loads(t[nachalo:konec])
            except Exception:  # noqa: BLE001
                continue
            if isinstance(z, list) and len(z) > len(luchshiy):
                luchshiy = z
            break


# ОТБОР ЦЕЛЕЙ ЗАДАЁТСЯ СНАРУЖИ. Второй заход спрашивает не «серии без принципа», а строки,
# которые МОЙ новый заслон счёл позиционными номерами и которых провайдер ещё не видел:
# среди них стоят «К-250» и «К-500», а это короткая запись НАСТОЯЩИХ серий центробежных
# машин. Своему чутью тут верить нельзя — пусть скажет второй прибор.
POZICIONNYY = re.compile(r'^(АК|К|Ц)[-\s]?\d{1,3}([/\-]\d{1,3})?$', re.I)
TOLKO_POZICII = os.environ.get('P25_TOLKO_POZICII') == '1'

celi = []
with io.open(SLOVAR, encoding='utf-8-sig') as f:
    for r in csv.DictReader(f, delimiter=';'):
        if TOLKO_POZICII:
            if not POZICIONNYY.match((r.get('oboznachenie') or '').strip()):
                continue
            if (r.get('mashina_provajder') or '').strip():
                continue
        else:
            if not (r.get('vid_zapisi') or '').startswith('серия'):
                continue
            if (r.get('princip') or '').strip() != 'не установлен':
                continue
        celi.append({'oboznachenie': (r.get('oboznachenie') or '').strip(),
                     'vid_mashiny': (r.get('vid_mashiny') or '').strip(),
                     'istochnik': (r.get('istochnik') or '')[:120]})
print('живой файл: %s' % SLOVAR)
print('серий с принципом «не установлен»: %d' % len(celi))

uzhe = {}
if os.path.exists(VYHOD):
    for s in io.open(VYHOD, encoding='utf-8'):
        try:
            z = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        uzhe[z.get('oboznachenie')] = z
celi = [c for c in celi if c['oboznachenie'] not in uzhe]
print('не разобрано прежде: %d' % len(celi))

klient = G.make_client()
sch = collections.Counter()
kontrol_otvety = []
novye = []
for nomer in range(min(PACHEK, (len(celi) + PACHKA - 1) // PACHKA)):
    pachka = celi[nomer * PACHKA:(nomer + 1) * PACHKA]
    if not pachka:
        break
    spisok = [c['oboznachenie'] for c in pachka] + [KONTROL]
    zapros = PROMPT % '\n'.join('- %s' % o for o in spisok)
    t0 = time.time()
    try:
        msg = G.call(klient, [{'role': 'user', 'content': zapros}], model=MODEL, attempts=3)
    except Exception as e:  # noqa: BLE001
        sch['вызов провайдера не удался: %s' % str(e)[:34]] += 1
        continue
    t = tekst_otveta(msg)
    sch['пачек отправлено'] += 1
    sch['знаков текста получено'] += len(t)
    if not t:
        sch['ответ пуст — текст не пришёл'] += 1
        continue
    otvety = massiv(t)
    if not otvety:
        sch['в ответе нет JSON-массива'] += 1
        continue
    poslano = {o.upper(): o for o in spisok}
    for z in otvety:
        ob = str(z.get('oboznachenie') or '').strip()
        if ob.upper() not in poslano:
            sch['ЗАСЛОН: в ответе обозначение, которого не посылали'] += 1
            continue
        pr = str(z.get('princip') or '').strip().lower()
        nash = bool(z.get('nasha_mashina'))
        if ob.upper() == KONTROL.upper():
            kontrol_otvety.append({'princip': pr, 'nasha_mashina': nash,
                                   'pochemu': str(z.get('pochemu') or '')[:70]})
            continue
        if pr not in PRINCIPY:
            sch['принцип не из списка — считаю «непонятно»'] += 1
            pr = 'непонятно'
        if not nash:
            sch['НЕ НАША МАШИНА'] += 1
        elif pr == 'непонятно':
            sch['непонятно'] += 1
        else:
            sch['РАЗОБРАНО: принцип назван'] += 1
            sch['   принцип %s' % pr] += 1
        novye.append({'oboznachenie': poslano[ob.upper()], 'princip': pr,
                      'nasha_mashina': nash, 'pochemu': str(z.get('pochemu') or '')[:160],
                      'model': MODEL, 'kto': '3-я сессия, разбор провайдером'})
    sch['секунд на пачку (сумма)'] += int(time.time() - t0)

for z in novye:
    uzhe[z['oboznachenie']] = z
with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for z in uzhe.values():
        f.write(json.dumps(z, ensure_ascii=False) + '\n')

print('\n\n########## ПО ОДНОЙ, ПЕРВЫЕ ДЕСЯТЬ')
for z in novye[:10]:
    print('  %-22s %-14s %s %s' % (z['oboznachenie'][:22], z['princip'],
                                   'наша' if z['nasha_mashina'] else 'НЕ наша',
                                   z['pochemu'][:60]))

print('\n########## ЧИСЛА')
for k, v in sch.most_common():
    print('  %-52s %5d' % (k[:52], v))
print('  строк в накопительном файле                       %5d' % len(uzhe))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ «%s»:' % KONTROL)
for k in kontrol_otvety:
    print('     принцип «%s», наша машина: %s — %s' % (k['princip'], k['nasha_mashina'],
                                                       k['pochemu']))
chisto = all(k['princip'] == 'непонятно' and not k['nasha_mashina'] for k in kontrol_otvety)
print('  контроль %s' % ('ЧИСТ: выдумке дан «непонятно»' if kontrol_otvety and chisto
                         else 'ПРОБИТ — провайдер угадывает, числам верить нельзя'
                         if kontrol_otvety else 'НЕ ПОЛУЧЕН — контрольной строки в ответах нет'))
print('ИТОГ ' + json.dumps({'разобрано': sch['РАЗОБРАНО: принцип назван'],
                            'непонятно': sch['непонятно'],
                            'не наша машина': sch['НЕ НАША МАШИНА'],
                            'контроль чист': bool(kontrol_otvety and chisto)},
                           ensure_ascii=False))
