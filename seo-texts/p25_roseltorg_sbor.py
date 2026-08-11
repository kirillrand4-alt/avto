# -*- coding: utf-8 -*-
"""РОСЭЛТОРГ: сбор закупок наших машин и заказчиков по ним. Форму выдала сама площадка.

Как форма нашлась. Подставлять параметры наугад (`query`, `search`, `keyword`) я перестала —
это давало ноль, а ноль одним способом есть диагноз прибора. Вместо этого проба ввела слово в
собственное поле страницы и прочитала у формы `action` и `name`:

    поле    query_field   «Ключевое слово, номер процедуры»
    форма   /procedures/search_ajax   [get]

Замер по этой форме, с сервера, браузером:

    компрессор     59 карточек, текст 8 521 знак
    щварцкопфер     0 карточек, текст   128 знаков  (пустая выдача — так и должно быть)

Первая же проба с ПРАВИЛЬНЫМ полем разошлась с прежней в 59 карточек: до этого прибор брал
поле подписки на рассылку (`email`) и получал 33 карточки И на настоящее слово, И на
выдуманное. Поймал это отрицательный контроль, а не я.

ЧТО СОБИРАЕТСЯ. По каждому слову — карточки процедур, по каждой карточке — организатор,
его ИНН и контактное лицо, если напечатано. Каждая строка несёт ДВЕ ссылки: выдачу по слову
и саму карточку.

ЗАСЛОНЫ (иначе «поле заполнено» выдаст себя за «факт доказан»):
   • слово машины обязано стоять в НАЗВАНИИ процедуры, а не где-то на странице;
   • ИНН берётся только если стоит сразу после слова «ИНН» — цифры «где-то в тексте» не в счёт
     (ЕИС уже показала, что выдуманный ИНН находится по ОГРН чужой организации);
   • номер телефона обязан быть телефонного вида, ФИО — похоже на ФИО;
   • выдуманное слово-контроль идёт тем же путём: если по нему найдутся карточки, числа не
     печатаются как истина.

ПУТЬ ДО ПЛОЩАДКИ. Задания идут мимо мёртвого прокси (`proxy: false`) и с выключенной
проверкой сертификата — прямой путь сервера подменяет сертификат. Без этих двух ключей
браузер не открывает даже example.com, и любая пустота была бы принята за «нет закупок».

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DIR, 'server', 'run_on_server.py')
SCRATCH = os.environ.get('P25_SCRATCH', '.')
VYHOD = os.path.join(SCRATCH, 'PARK-ROSELTORG-ZAKUPKI-3S.jsonl')
POISK = 'https://www.roseltorg.ru/procedures/search_ajax?query_field=%s'
SLOVA = [w for w in os.environ.get(
    'P25_SLOVA',
    'компрессор|компрессорная станция|воздуходувка|турбокомпрессор|азотная станция|'
    'генератор азота|генератор кислорода|воздухоразделительная установка|нагнетатель|'
    'осушитель воздуха|щварцкопфер').split('|') if w.strip()]
KARTOCHEK = int(os.environ.get('P25_KARTOCHEK', '12'))   # сколько карточек открывать на слово
KONTROL_SLOVO = 'щварцкопфер'
MASH = re.compile(r'компрессор|воздуходув|нагнетател|осушител|азотн|кислородн|'
                  r'воздухоразделит|ГПА', re.I)
INN_POSLE = re.compile(r'ИНН[^0-9A-Za-zА-Яа-я]{0,8}(\d{10}|\d{12})')
TELEFON = re.compile(r'(?:\+7|8)[\s\-()]*\d{3,5}[\s\-()]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}')
POCHTA = re.compile(r'[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
FIO = re.compile(r'\b([А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}(?:вич|вна))\b')
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def proba(url, skript, vozvrat, zhdat=9000, imya=''):
    """Одно браузерное задание. Мимо прокси и без проверки сертификата — см. шапку."""
    zadanie = {'url': url, 'wait_ms': zhdat, 'proxy': False, 'ignore_https_errors': True,
               'eval_js': {'script': skript, 'return': vozvrat}}
    if imya:
        zadanie['inn'] = imya
    try:
        p = subprocess.run([sys.executable, RUNNER, 'browser_probe',
                            json.dumps(zadanie, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=420)
    except Exception as e:  # noqa: BLE001
        return {}, str(e)[:60]
    syr = p.stdout or ''
    i = syr.find('{')
    if i < 0:
        return {}, (p.stderr or syr)[:60]
    try:
        d = json.loads(syr[i:syr.rfind('}') + 1]).get('data') or {}
    except Exception:  # noqa: BLE001
        return {}, syr[:60]
    v = d.get('eval_js_value')
    try:
        return (json.loads(v) if isinstance(v, str) and v else {}), (d.get('error') or '')[:60]
    except Exception:  # noqa: BLE001
        return {}, 'значение не разобрано: %s' % str(v)[:50]


SPISOK = '''
var a = [].slice.call(document.querySelectorAll('a[href*="/procedure/"]'));
var vid = [];
a.forEach(function(x){
  var h = x.getAttribute('href');
  var t = (x.innerText||'').replace(/\\s+/g,' ').trim();
  if (!h) return;
  var est = false;
  vid.forEach(function(z){ if (z.h === h) est = true; });
  if (!est) vid.push({h: h, t: t});
});
// СТРАНИЦА «НЕ НАЙДЕНО» УСПЕВАЕТ ПОКАЗАТЬ СПИСОК ПО УМОЛЧАНИЮ. Прогон дважды печатал
// «контроль пробит: выдуманное слово дало 4 карточки», а отдельная проба тех же адресов
// давала 0 и пометку «не найден». Значит дело во ВРЕМЕНИ: карточки видны, пока не встало
// пустое состояние. Поэтому считаю карточки нулём, если страница прямо говорит «не найдено»,
// и печатаю этот признак — чтобы ноль был виден как ответ площадки, а не как удача.
var telo = document.body ? document.body.innerText : '';
var ne_najdeno = /не найден|ничего не найдено|нет результатов/i.test(telo);
window.__v = JSON.stringify({kartochek: ne_najdeno ? 0 : vid.length,
                             ne_najdeno: ne_najdeno,
                             spisok: ne_najdeno ? [] : vid.slice(0, 60),
                             dlina: telo.length});
'''

KARTA = '''
var t = (document.body.innerText||'').replace(/\\s+/g,' ');
window.__v = JSON.stringify({tekst: t.slice(0, 6000), zagolovok: (document.title||'').slice(0,160),
                             dlina: t.length});
'''

uzhe = {}
if os.path.exists(VYHOD):
    for s in io.open(VYHOD, encoding='utf-8'):
        try:
            z = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        uzhe[z.get('ssylka_kartochki')] = z

sch = collections.Counter()
novye = []
po_slovam = {}
for slovo in SLOVA:
    u = POISK % urllib.parse.quote(slovo.encode('utf-8'))
    spis, osh = proba(u, SPISOK, 'window.__v || ""', 10000)
    po_slovam[slovo] = {'карточек в выдаче': spis.get('kartochek', 0),
                        'длина текста': spis.get('dlina', 0), 'ошибка': osh}
    if osh:
        sch['выдача не открылась: %s' % osh[:24]] += 1
        continue
    if slovo == KONTROL_SLOVO:
        continue                      # контроль только считаем, карточки не открываем
    celi = [x for x in spis.get('spisok', [])
            if MASH.search(x.get('t') or '')][:KARTOCHEK]
    sch['карточек с машиной в названии'] += len(celi)
    for x in celi:
        h = x['h']
        adres = h if h.startswith('http') else 'https://www.roseltorg.ru' + h
        if adres in uzhe:
            sch['карточка уже разобрана прежде'] += 1
            continue
        k, osh2 = proba(adres, KARTA, 'window.__v || ""', 9000)
        if osh2 or not k.get('tekst'):
            sch['карточка не открылась'] += 1
            continue
        t = k['tekst']
        inn = INN_POSLE.search(t)
        # ЗАСЛОН: НОМЕР ПРОЦЕДУРЫ — НЕ ТЕЛЕФОН. Первый заход записал «телефоны» 8261154155,
        # 8261712116, 8092500264 — это куски кода самой процедуры (B0508261154155,
        # ATOM18092500264): десять цифр подряд, начинаются с восьмёрки, и образец телефона
        # их принимает. Семь строк из 41. Отбрасываю всё, чьи цифры входят в код процедуры.
        # ВТОРОЙ ЗАСЛОН НА ТЕЛЕФОН: ДЛИНА И РЕКВИЗИТЫ. Первый (цифры процедуры) поймал
        # семь строк, но пропустил другой класс: «8300013326001», «8001058022801» — по
        # ТРИНАДЦАТЬ цифр, слипшиеся куски строки реквизитов «ИНН … КПП …». По живому файлу
        # ТЭК-Торга таких 14 из 80. Российский номер это 10 цифр (без кода страны) или 11
        # (с 7/8); всё прочее — не телефон. Плюс отбрасываю номер, у которого начало
        # совпадает с ИНН: это цифры юрлица, а не человека.
        DLINA_NOMERA = (10, 11)
        cifry_procedury = re.sub(r'\D', '', adres)
        inn_cifry = inn.group(1) if inn else ''
        tel = None
        for m in TELEFON.finditer(t):
            d = re.sub(r'\D', '', m.group(0))
            if d and d in cifry_procedury:
                sch['ЗАСЛОН: номер процедуры принят за телефон'] += 1
                continue
            if len(d) not in DLINA_NOMERA:
                sch['ЗАСЛОН: не телефонная длина (цифры реквизитов)'] += 1
                continue
            if inn_cifry and (d[:6] == inn_cifry[:6] or inn_cifry[:6] in d):
                sch['ЗАСЛОН: цифры совпадают с ИНН — это реквизиты'] += 1
                continue
            tel = m
            break
        fio = FIO.search(t)
        poch = POCHTA.search(t)
        if not MASH.search(x.get('t') or ''):
            sch['ЗАСЛОН: машины нет в названии процедуры'] += 1
            continue
        novye.append({
            'inn': inn.group(1) if inn else '',
            'inn_otkuda': 'стоит после слова ИНН на карточке Росэлторга' if inn else '',
            'zakupka': (x.get('t') or '')[:200],
            'vid': (MASH.search(x.get('t') or '') or MASH.search(t)).group(0).lower(),
            'chelovek': fio.group(1) if fio else '',
            'telefon': tel.group(0) if tel else '',
            'pochta': poch.group(0) if poch else '',
            'slovo_zaprosa': slovo,
            'ssylka_vydachi': u,
            'ssylka_kartochki': adres,
            'istochniki': adres + ' | ' + u,
            'istochnikov': 2,
            'kto': '3-я сессия, Росэлторг по форме площадки'})
        sch['взято'] += 1
        time.sleep(0.4)

for z in novye:
    uzhe[z['ssylka_kartochki']] = z
with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for z in uzhe.values():
        if z:
            f.write(json.dumps(z, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:70]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:50]

print('\n\n########## ВЫДАЧА ПО СЛОВАМ')
for slovo, v in po_slovam.items():
    print('  %-34s карточек %4s, текст %6s %s'
          % (slovo[:34], v['карточек в выдаче'], v['длина текста'],
             ('| ' + v['ошибка']) if v['ошибка'] else ''))

print('\n########## ПЕРВЫЕ ВОСЕМЬ ВЗЯТЫХ')
for z in novye[:8]:
    print('  %-12s %-46s %s %s' % (z['inn'] or '—', z['zakupka'][:46],
                                   z['telefon'] or '', z['chelovek'] or ''))
    print('        %s' % z['ssylka_kartochki'][:100])

kontrol = po_slovam.get(KONTROL_SLOVO, {}).get('карточек в выдаче', None)
nastoyashchie = [v['карточек в выдаче'] for s, v in po_slovam.items() if s != KONTROL_SLOVO]
print('\n########## ЧИСЛА')
print('  слов запрошено                %d' % len(SLOVA))
print('  карточек в выдаче, всего      %d' % sum(nastoyashchie))
for k, v in sch.most_common():
    print('     %-50s %5d' % (k[:50], v))
print('  строк в накопительном файле   %d' % len([z for z in uzhe.values() if z]))
print('  с ИНН                         %d' % len([z for z in uzhe.values()
                                                  if z and z.get('inn')]))
print('  с телефоном                   %d' % len([z for z in uzhe.values()
                                                  if z and z.get('telefon')]))
print('  с названным человеком         %d' % len([z for z in uzhe.values()
                                                  if z and z.get('chelovek')]))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ «%s»: карточек %s — %s'
      % (KONTROL_SLOVO, kontrol,
         'поиск различает слова, числам можно верить' if kontrol == 0 else
         'ВЫДУМАННОЕ СЛОВО ТОЖЕ НАШЛОСЬ — числам верить нельзя'))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'взято': sch['взято'], 'в файле': len(uzhe),
                            'контроль карточек': kontrol}, ensure_ascii=False))
