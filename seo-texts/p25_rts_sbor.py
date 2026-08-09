# -*- coding: utf-8 -*-
"""РТС-тендер: сбор вводом в поле. Адресом поиск не вызывается — доказано пятью именами.

История канала, чтобы никто не повторял:

    заход 1   простой запрос -> 503 на все восемь слов подряд. Восемь одинаковых ответов
              это ОДИН диагноз прибора, а не восемь фактов о площадке
    заход 2   браузером -> страницы открываются (52 тыс. знаков), но слова запроса на них
              нет ни разу: адрес `?searchtext=` поиск не запускает
    заход 3   пять имён параметра (Text, SearchText, searchString, query, searchtext) —
              у всех одна и та же лента из десяти лотов
    заход 4   форма снята у самой площадки: поле `input.search__text` с подсказкой
              «Введите ключевое слово или номер извещения» и кнопка
              `button.search__btn.mainButtonSearch`. Ни то, ни другое в адрес не выносится
    заход 5   fill_seq заполнил поле, но Enter поиск НЕ запускает — нужна кнопка

С кнопкой выдача наконец меняется по словам:

    генератор азота  246 368 знаков, слово 10 раз, карточек 2
    воздуходувка     740 316 знаков, слово 28 раз, карточек 10
    компрессор       523 916 знаков, слово 1 раз  — не успела отрисоваться, ждать дольше

ЗАСЛОН: слово запроса обязано встретиться в тексте выдачи больше одного раза (один раз —
это само поле ввода). Если у слова единица, строка помечается «выдача не отрисовалась», и
такие в счёт не идут.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DIR, 'server', 'run_on_server.py')
SLOVA = ['компрессор', 'винтовой компрессор', 'поршневой компрессор', 'генератор азота',
         'генератор кислорода', 'азотная станция', 'кислородная станция',
         'компрессорная станция', 'воздуходувка', 'осушитель сжатого воздуха']
VYHOD = os.path.join(DIR, 'PARK-RTS-3S.jsonl')
TEG = re.compile(r'<[^>]+>')
# ТРЕТИЙ РАЗ ОДИН И ТОТ ЖЕ ДЕФЕКТ, теперь называю его правилом. Текст ссылки на карточку —
# это НЕ название закупки: у B2B ссылки на лот в разметке нет вовсе, у ЭТП ГПБ в адресе
# внутренний id, а здесь якорь содержит слово «ПОДРОБНЕЕ». Название лежит в теле карточки
# ПЕРЕД кнопкой. Правило: на площадках с отрисовкой скриптом брать плоский текст вокруг
# ссылки, а не текст самой ссылки.
KARTA = re.compile(r'href="(/poisk/id/([a-z0-9\-]+)/)"')


def probe(slovo, zhdat):
    args = {'url': 'https://www.rts-tender.ru/poisk', 'screenshot': False,
            'return_html': True, 'html_cap': 1200000, 'wait_ms': zhdat,
            'card_wait_ms': 15000, 'proxy': False, 'ignore_https_errors': True,
            'fill_seq': {'steps': [{'selector': '.search__text', 'value': slovo}],
                         'submit': 'button.mainButtonSearch'}}
    try:
        r = subprocess.run([sys.executable, RUNNER, 'browser_probe',
                            json.dumps(args, ensure_ascii=False)], capture_output=True,
                           timeout=600)
    except Exception as e:  # noqa: BLE001
        return '', str(e)[:50]
    s = r.stdout.decode('utf-8', 'replace')
    i = s.find('{')
    if i < 0:
        return '', 'раннер не вернул JSON'
    try:
        d = (json.loads(s[i:]).get('data') or {})
    except Exception:  # noqa: BLE001
        return '', 'битый JSON'
    return d.get('html') or '', str(d.get('error') or '')[:50]


potok, svod, oshibki = [], collections.Counter(), collections.Counter()
for slovo in SLOVA:
    h, err = probe(slovo, 34000)
    if err:
        oshibki['%s: %s' % (slovo, err)] += 1
    t = re.sub(r'\s+', ' ', TEG.sub(' ', h))
    osnova = slovo.split()[-1][:7].lower()
    vstrech = t.lower().count(osnova)
    # ВТОРАЯ ПОПРАВКА к тому же месту. Текст ПЕРЕД ссылкой оказался служебной шапкой карточки
    # («Коммерческие Закупка Система электронных торгов B2B-Center ЗАПРОС ПРЕДЛОЖЕНИЙ»), а
    # название стоит дальше. Значит резать надо не «до ссылки», а НА КУСКИ ПО КНОПКЕ: плоский
    # текст страницы делится словом «ПОДРОБНЕЕ», и каждый кусок — это одна карточка целиком.
    # Порядок кусков и порядок ссылок совпадает, потому что оба идут по документу.
    kuski = [re.sub(r'\s+', ' ', x).strip() for x in t.split('ПОДРОБНЕЕ')]
    karty = []
    for i, m in enumerate(KARTA.finditer(h)):
        kusok = kuski[i] if i < len(kuski) else ''
        # из куска выбрасываю служебные слова карточки, чтобы осталось название предмета
        kusok = re.sub(r'(Коммерческие|Закупка|Система электронных торгов|B2B-Center|'
                       r'ЗАПРОС ПРЕДЛОЖЕНИЙ|Аукцион|Конкурс|44-ФЗ|223-ФЗ|Электронный)',
                       ' ', kusok)
        karty.append((m.group(1), m.group(2), re.sub(r'\s+', ' ', kusok).strip()[-260:]))
    vid, ryad = set(), []
    for put, nom, naz in karty:
        if nom in vid:
            continue
        vid.add(nom)
        ryad.append({'nomer': nom, 'nazvanie': naz[:220], 'slovo': slovo,
                     'istochniki': 'https://www.rts-tender.ru' + put, 'istochnikov': 1,
                     'slovo_v_nazvanii': osnova in naz.lower(),
                     'kto': '3-я сессия, РТС-тендер'})
    if vstrech <= 1:
        svod['%s: выдача не отрисовалась (слово %d раз)' % (slovo, vstrech)] += 1
    else:
        svod['%s: слово %d раз, карточек %d' % (slovo, vstrech, len(ryad))] += 1
        potok.extend(ryad)
    print('  %-34s знаков %7d | слово %3d раз | карточек %3d %s'
          % (slovo, len(t), vstrech, len(ryad), err))

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')

podtv = [o for o in potok if o['slovo_v_nazvanii']]
print('\n\n########## ПРИМЕРЫ')
for o in podtv[:8]:
    print('  %-22s %-16s %s' % (o['nomer'][:22], o['slovo'][:16], o['nazvanie'][:70]))
print('\n########## ЧИСЛА')
print('  слов опрошено             %4d' % len(SLOVA))
print('  карточек собрано          %4d' % len(potok))
print('  слово стоит в названии    %4d' % len(podtv))
print('  --- по словам')
for k, v in svod.most_common():
    print('     %s' % k)
if oshibki:
    print('  --- ошибки')
    for k, v in oshibki.most_common(6):
        print('     %-56s %3d' % (k[:56], v))
print('  файл: %s' % VYHOD)
print('ИТОГ ' + json.dumps({'карточек': len(potok), 'слово в названии': len(podtv)},
                           ensure_ascii=False))
