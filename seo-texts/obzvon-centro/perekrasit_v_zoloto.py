# -*- coding: utf-8 -*-
"""Перекрасить боевой centro.css в «ivory & gold» прошлой базы обзвона.

Владелец: «дизайн уже не такой как в прошлой базе обзвона, та мне больше
нравилась». Прошлая база — ivory & gold из `app.css`: тёплый фон, золотые
акценты, заголовки Cinzel, скин золото / нежно салатовый.

ПОЧЕМУ ПЕРЕСЧЁТ ЦВЕТОВ, А НЕ НОВЫЙ ФАЙЛ. Боевой centro.css минифицирован в
одну строку и написан НЕ под ту разметку, что лежит в репозитории (11 762
байта против 38 706). Написать тему заново значит угадать, какие из сотен
селекторов ещё используются живым шаблоном, и часть потерять молча — а
пропавшее правило не падает, оно просто делает страницу некрасивой там, куда
никто не смотрит. Здесь же меняется ТОЛЬКО тон: светлота каждого цвета
сохраняется, поэтому контраст текста к фону остаётся ровно прежним.

Что с чем делаем:
  * серые (насыщенность < 10%) — в тёплый ivory той же светлоты;
  * сине-фиолетовые (тон 175–285°) — в золото 42°;
  * зелёные и красные НЕ трогаем: это статусы «дозвонились» и «отказ»,
    их смысл в цвете, и перекрасить их значит соврать продавцу.

Сверху докладывается слой `centro-gold-layer.css` — то, что тоном не лечится:
шрифты, светлая шапка вместо тёмно-синей плиты, золотые раскрывашки.

Запуск: python perekrasit_v_zoloto.py <живой centro.css> [куда]
"""
import colorsys
import os
import re
import sys

СЛОЙ = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'centro-gold-layer.css')


def _разобрать(h):
    s = h[1:]
    if len(s) == 3:
        s, a = ''.join(c * 2 for c in s), ''
    elif len(s) == 4:
        a, s = s[3] * 2, ''.join(c * 2 for c in s[:3])
    elif len(s) == 8:
        a, s = s[6:], s[:6]
    elif len(s) == 6:
        a = ''
    else:
        return None
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4)), a


def в_золото(h):
    р = _разобрать(h)
    if not р:
        return h
    (r, g, b), a = р
    тон, светлота, нас = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    град = тон * 360
    if нас < 0.10:                      # нейтральный серый
        тон, нас = 42 / 360, 0.14 if светлота > .55 else 0.10
    elif 175 <= град <= 285:            # синий, фиолетовый
        тон, нас = 42 / 360, min(0.58, нас * 1.02)
    else:                               # зелёный и красный — смысловые
        тон = град / 360
    r2, g2, b2 = colorsys.hls_to_rgb(тон, светлота, нас)
    return '#' + ''.join(f'{max(0, min(255, round(x * 255))):02x}'
                         for x in (r2, g2, b2)) + a


def main():
    ист = sys.argv[1] if len(sys.argv) > 1 else ''
    куда = sys.argv[2] if len(sys.argv) > 2 else 'centro-gold.css'
    if not (ист and os.path.exists(ист)):
        print('нужно: perekrasit_v_zoloto.py <живой centro.css> [куда]')
        return
    сыр = open(ист, encoding='utf-8', errors='replace').read()
    нов = re.sub(r'#[0-9a-fA-F]{3,8}\b', lambda m: в_золото(m.group(0)), сыр)
    нов = нов.replace(
        'font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif',
        'font-family:"Cormorant Garamond","PT Serif",Georgia,'
        '"Times New Roman",serif')
    if os.path.exists(СЛОЙ):
        нов += open(СЛОЙ, encoding='utf-8').read()
    else:
        print('ВНИМАНИЕ: слоя centro-gold-layer.css нет, тема будет неполной')
    with open(куда, 'w', encoding='utf-8') as ф:
        ф.write(нов)
    print(f'{ист} ({len(сыр)}) → {куда} ({len(нов)})')


if __name__ == '__main__':
    main()
