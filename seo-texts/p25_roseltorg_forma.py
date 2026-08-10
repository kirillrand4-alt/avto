# -*- coding: utf-8 -*-
"""РОСЭЛТОРГ: найти РАБОЧУЮ форму запроса, а не признать площадку пустой.

Что уже известно и почему это не «нет закупок»:

    /procedures/search           открывается, список рисуется скриптом
    подставленные мной параметры  ?query= ?search= ?keyword=  дали ПУСТО во всех пробах

Ноль, повторённый несколько раз ОДНИМ способом, — диагноз прибора, а не факт о площадке
(правило выведено на РТС, где «ноль закупок» оказался игнорируемым параметром страницы).
Поэтому здесь я не подставляю параметры наугад, а **спрашиваю саму страницу**: ввожу слово в
её собственное поле, жму её собственную кнопку и смотрю, какой адрес получился и что за
ссылки появились. Форму диктует сайт, а не я.

Прибор — браузер (список рисуется скриптом, urllib увидит пустую разметку).

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: тем же способом ищется «щварцкопфер» — слова, которого нет. Если
площадка выдаст столько же карточек, сколько на «компрессор», значит поиск игнорирует запрос
и числа ничего не значат.

Числа в КОНЦЕ.
"""
import json
import os
import subprocess
import sys
import urllib.parse

DIR = os.path.dirname(os.path.abspath(__file__))
NACHALO = 'https://www.roseltorg.ru/procedures/search'
SLOVA = [('компрессор', 'настоящее слово'), ('щварцкопфер', 'ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ')]

# скрипт выполняется НА странице: находит поле поиска, вводит слово, отправляет форму,
# затем возвращает адрес и первые ссылки на процедуры
SKRIPT = '''
var slovo = %s;
function vidno(e){ var r = e.getBoundingClientRect(); return r.width > 40 && r.height > 8; }
var polya = [].slice.call(document.querySelectorAll('input[type=text],input[type=search],input:not([type])'))
              .filter(vidno);
var pole = polya[0];
var otchet = {polej_vidno: polya.length,
              imena_polej: polya.slice(0,5).map(function(p){return (p.name||'')+'/'+(p.id||'')+'/'+(p.placeholder||'').slice(0,24);})};
if (!pole) { otchet.beda = 'поле ввода не найдено'; window.__otchet = JSON.stringify(otchet); return; }
otchet.vzyato_pole = (pole.name||'')+'/'+(pole.id||'')+'/'+(pole.placeholder||'').slice(0,30);
var ust = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
ust.call(pole, slovo);
pole.dispatchEvent(new Event('input', {bubbles:true}));
pole.dispatchEvent(new Event('change', {bubbles:true}));
var f = pole.form;
otchet.forma_est = !!f;
if (f) { otchet.dejstvie_formy = (f.getAttribute('action')||'') + ' [' + (f.method||'') + ']'; }
pole.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', keyCode:13, which:13, bubbles:true}));
var knopki = [].slice.call(document.querySelectorAll('button,input[type=submit],a'))
               .filter(function(b){ var t=(b.innerText||b.value||'').trim().toLowerCase();
                                    return (t==='найти'||t==='поиск'||t==='искать') && vidno(b); });
otchet.knopok_najti = knopki.length;
if (knopki.length) { knopki[0].click(); otchet.nazhal = true; }
else if (f) { try { f.submit(); otchet.otpravil_formu = true; } catch(e) { otchet.beda_submit = String(e).slice(0,60); } }
window.__otchet = JSON.stringify(otchet);
'''

POSLE = '''
var ssylki = [].slice.call(document.querySelectorAll('a[href]'))
               .map(function(a){ return a.getAttribute('href'); })
               .filter(function(h){ return h && /procedure|purchase|tender|lot/i.test(h); });
var uniq = []; ssylki.forEach(function(h){ if (uniq.indexOf(h) < 0) uniq.push(h); });
window.__vyhod = JSON.stringify({adres: location.href,
                       kartochek: uniq.length,
                       primery: uniq.slice(0,6),
                       est_slovo_v_tekste: (document.body.innerText||'').toLowerCase().indexOf(%s) >= 0,
                       dlina_teksta: (document.body.innerText||'').length});
'''


def proba(zadanie):
    p = subprocess.run([sys.executable, os.path.join(DIR, 'server', 'run_on_server.py'),
                        'browser_probe', json.dumps(zadanie, ensure_ascii=False)],
                       capture_output=True, text=True, timeout=600)
    syr = p.stdout or ''
    i = syr.find('{')
    if i < 0:
        return {'беда': (p.stderr or syr)[:100]}
    try:
        o = json.loads(syr[i:syr.rfind('}') + 1])
    except Exception:  # noqa: BLE001
        return {'беда': syr[:120]}
    # ОТВЕТ РАННЕРА ЛЕЖИТ ПОД `data`. Первый заход читал `result`, получал пустой словарь —
    # и печатал вывод «поиск игнорирует запрос» на ПУСТОТЕ. Ноль прибора, выданный за факт
    # о площадке: ровно та ошибка, которую я ловлю у других.
    return o.get('data') or o.get('result') or o


def razobrat(z):
    """eval_js_value приходит строкой JSON — разворачиваю, иначе печатаю как есть."""
    v = z.get('eval_js_value')
    try:
        return json.loads(v) if isinstance(v, str) else (v or {})
    except Exception:  # noqa: BLE001
        return {'сырое': str(v)[:120]}


itog = {}
for slovo, chto in SLOVA:
    # шаг 1: ввести слово и отправить форму САМОЙ страницы
    z1 = proba({'url': NACHALO, 'wait_ms': 9000, 'inn': 'ROSELTORG-' + chto[:8],
                'eval_js': {'script': SKRIPT % json.dumps(slovo, ensure_ascii=False),
                            'return': 'window.__otchet || ""', 'after_ms': 7000}})
    o1 = razobrat(z1)
    # ШАГ 2 НЕ МОЖЕТ ПРОДОЛЖИТЬ ТУ ЖЕ СТРАНИЦУ: раннер отдаёт значение `return` СРАЗУ после
    # скрипта (пауза `after_ms` идёт уже после), а каждое задание открывает браузер заново —
    # значит состояние SPA после нажатия «Найти» до меня не доедет. Поэтому беру у страницы
    # не результат, а САМУ ФОРМУ: адрес `action` и ИМЯ поля ввода. Из них собираю обычную
    # ссылку и открываю её отдельным заданием. Форму по-прежнему диктует сайт, а не я.
    dejstvie = str(o1.get('dejstvie_formy') or '').split(' [')[0].strip()
    imya_polya = str(o1.get('vzyato_pole') or '').split('/')[0].strip()
    if dejstvie.startswith('/'):
        dejstvie = 'https://www.roseltorg.ru' + dejstvie
    if dejstvie.startswith('http') and imya_polya:
        adres = '%s?%s=%s' % (dejstvie, imya_polya,
                              urllib.parse.quote(slovo.encode('utf-8')))
    elif imya_polya:
        adres = '%s?%s=%s' % (NACHALO, imya_polya, urllib.parse.quote(slovo.encode('utf-8')))
    else:
        adres = NACHALO
    z2 = proba({'url': adres, 'wait_ms': 9000,
                'screenshot': True, 'screenshot_drop': True,
                'inn': 'ROSELTORG-SNIMOK-' + chto[:8],
                'eval_js': {'script': POSLE % json.dumps(slovo.lower(), ensure_ascii=False),
                            'return': 'window.__vyhod || ""', 'after_ms': 4000}})
    itog[chto] = {'слово': slovo, 'что нашла форма': o1, 'что вышло': razobrat(z2),
                  'собранный адрес': adres,
                  'отметки': {'шаг 1': (z1.get('error') or '')[:60],
                              'шаг 2': (z2.get('error') or '')[:60]}}

print('\n\n########## ЧТО СКАЗАЛА САМА ПЛОЩАДКА')
for chto, v in itog.items():
    print('\n  %s — «%s»' % (chto, v['слово']))
    for k, z in v['что нашла форма'].items():
        print('      %-22s %s' % (k, str(z)[:110]))
    print('      собранный по форме адрес: %s' % str(v['собранный адрес'])[:120])
    for k, z in v['что вышло'].items():
        print('      %-22s %s' % (k, str(z)[:110]))

nast = itog.get('настоящее слово', {}).get('что вышло', {}) or {}
kont = itog.get('ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ', {}).get('что вышло', {}) or {}
print('\n########## ЧИСЛА')
print('  карточек на «компрессор»   %s' % nast.get('kartochek', '—'))
print('  карточек на выдуманное слово %s' % kont.get('kartochek', '—'))
prochel = isinstance(nast.get('dlina_teksta'), int) and nast['dlina_teksta'] > 500 \
    and isinstance(kont.get('dlina_teksta'), int) and kont['dlina_teksta'] > 500
mozhno = prochel and isinstance(nast.get('kartochek'), int) and nast['kartochek'] > 0
chisto = mozhno and (kont.get('kartochek', 0) < nast['kartochek'])
if not prochel:
    print('  ВЫВОДА НЕТ: браузер не прочёл страницу площадки (длина текста %s и %s).'
          % (nast.get('dlina_teksta', '—'), kont.get('dlina_teksta', '—')))
    print('  Это состояние прибора, а не факт о Росэлторге.')
else:
    print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: %s'
          % ('поиск РАЗЛИЧАЕТ слова — числам можно верить' if chisto else
             'выдуманное слово дало столько же — поиск запрос игнорирует, числам верить нельзя'))
print('ИТОГ ' + json.dumps({'страница прочтена': bool(prochel),
                            'форма найдена': mozhno, 'контроль чист': bool(chisto),
                            'адрес': str(itog.get('настоящее слово', {})
                                         .get('собранный адрес', ''))[:150]},
                           ensure_ascii=False))
