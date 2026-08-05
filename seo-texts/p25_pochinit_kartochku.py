# -*- coding: utf-8 -*-
"""Карточка печатает должность из поля, которого в таблице нет. Починить по месту.

ЧТО НАЙДЕНО. Шаблон `centro_card.html` рисует значок должности так:

    {% if p.post %}<span class="ct-badge ...">{{ p.post }}</span>{% endif %}

А в таблице `person` поля `post` НЕТ ВОВСЕ — есть `position`, и оно заполнено у 8 909
человек из 16 397. То есть значок должности на карточке пуст всегда, сколько бы
должностей ни добыли: `persons()` отдаёт строку целиком, шаблон спрашивает не то имя.
Промах того же рода, что я ловлю у себя весь день, — угаданное имя поля даёт
правдоподобную пустоту вместо ошибки.

ВТОРАЯ ПРАВКА — ради чего всё и затевалось. Перепроверка 543 спорных привязок записала
в базу, у кого привязка подтверждена строкой источника, а у кого в источнике назван
ДРУГОЙ работодатель. Продавец этого не видит: шаблон про новые колонки не знает. Добавляю
одну строку — она печатает пометку, если та есть.

Скрывать людей не стал намеренно. Правило владельца — разделять, а не отсеивать: человек
настоящий, и «Ахмадишин — директор Дома народного творчества» полезнее пустоты. Продавец
должен видеть, что привязка не подтверждена, и решать сам.

ОСТОРОЖНО, ФАЙЛ ЧУЖОЙ. Он принадлежит панели владельца, и рядом работают другие сессии.
Поэтому: правка только точным совпадением куска (не нашлось — ничего не делаем и говорим
об этом), рядом кладётся резервная копия с отметкой времени, и печатается, что именно
изменилось.

Без --apply ничего не пишется.
"""
import io
import json
import os
import shutil
import sys
import time

SHABLON = r'C:\seostat\app\templates\centro_card.html'
APPLY = '--apply' in sys.argv

BYLO_DOLZHNOST = (
    "{% if p.post %}<span class=\"ct-badge "
    "{{ 'ct-badge--buy' if p.is_tech else 'ct-badge--muted' }}\">{{ p.post }}</span>{% endif %}")
STALO_DOLZHNOST = (
    "{% if p.position %}<span class=\"ct-badge "
    "{{ 'ct-badge--buy' if p.is_tech else 'ct-badge--muted' }}\">{{ p.position }}</span>{% endif %}")

# Строка про привязку встаёт сразу за блоком строк человека.
YAKOR_PRIVYAZKA = '      <div class="ct-person-lines">'
STALO_PRIVYAZKA = (
    '      {% if p.privyazka_somnitelna %}\n'
    '      <div class="ct-note" style="color:#a33">привязка к предприятию не '
    'подтверждена: {{ p.privyazka_somnitelna }}</div>\n'
    '      {% elif p.privyazka_proverena and \'ПОДТВЕРЖДЕНО\' in p.privyazka_proverena %}\n'
    '      <div class="ct-note" style="color:#282">привязка проверена по строке '
    'источника</div>\n'
    '      {% endif %}\n'
    '      <div class="ct-person-lines">')


def main():
    if not os.path.exists(SHABLON):
        print('REC шаблона нет по пути\t1')
        print('ИТОГ ' + json.dumps({'сделано': False, 'почему': 'файла нет'},
                                   ensure_ascii=False))
        return
    t = io.open(SHABLON, encoding='utf-8').read()
    itog = {}
    novy = t

    n1 = novy.count(BYLO_DOLZHNOST)
    itog['кусок про должность найден раз'] = n1
    if n1 == 1:
        novy = novy.replace(BYLO_DOLZHNOST, STALO_DOLZHNOST)
    elif n1 == 0:
        # Не совпало дословно — значит файл уже другой. Молча не гадаем.
        itog['должность'] = 'кусок не найден дословно, не трогаю'

    n2 = novy.count(YAKOR_PRIVYAZKA)
    itog['якорь строк человека найден раз'] = n2
    if 'privyazka_somnitelna' in novy:
        itog['привязка'] = 'уже показывается, второй раз не добавляю'
    elif n2 == 1:
        novy = novy.replace(YAKOR_PRIVYAZKA, STALO_PRIVYAZKA)
    else:
        itog['привязка'] = 'якорь не единственный, не трогаю'

    if novy == t:
        print('REC изменений нет\t1')
        print('ИТОГ ' + json.dumps(dict(itog, сделано=False), ensure_ascii=False))
        return

    print('--- что изменится (строки, которых не было)')
    staroe = set(t.split('\n'))
    for s in novy.split('\n'):
        if s not in staroe and s.strip():
            print('  + %s' % s[:150])

    if not APPLY:
        print('REC сухой прогон, файл не тронут\t1')
        print('ИТОГ ' + json.dumps(dict(itog, сделано=False), ensure_ascii=False))
        return

    kopiya = SHABLON + '.bak-3s-' + time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(SHABLON, kopiya)
    io.open(SHABLON, 'w', encoding='utf-8', newline='').write(novy)
    proverka = io.open(SHABLON, encoding='utf-8').read()
    itog['резервная копия'] = os.path.basename(kopiya)
    itog['должность теперь из position'] = 'p.position' in proverka
    itog['пометка привязки показывается'] = 'privyazka_somnitelna' in proverka
    print('REC записано\t1')
    print('ИТОГ ' + json.dumps(dict(itog, сделано=True), ensure_ascii=False))


if __name__ == '__main__':
    main()
