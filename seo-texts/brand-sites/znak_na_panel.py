# -*- coding: utf-8 -*-
"""Знак Enger на кадры категорий: место ищется по картинке, не на глаз.

Панели заданы руками - их видно точно. А КУДА внутри панели ляжет знак,
решает chistoe_mesto: под знаком не должно быть ни одной резкой детали.
Три захода до этого сажали знак поперёк стыка двух дверей, на защёлку, на
болт и на угол балки под кабелями - ровно потому, что место выбирал я.

Знак двухъярусный (ENGER + COMPRESSOR SYSTEM), как на настоящих машинах.
Исключение - центробежный: он широкий, любая плоская площадка на нём мелкая,
и подпись вторым ярусом превращается в кашу. Там одноярусный ENGER.
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chistoe_mesto as C  # noqa: E402

OPORA = 1024

# Углы панели: левый верх, правый верх, правый низ, левый низ.
# Сняты замером светлой области двери по строкам и столбцам.
PANELI = {
    'nizkogo-davleniya': (((336, 170), (712, 199), (712, 761), (336, 796)),
                          'тёмный', 'znak'),
    'spiralnye':         (((469, 232), (738, 245), (738, 839), (469, 866)),
                          'тёмный', 'znak'),
    'peredvizhnye':      (((445, 247), (621, 258), (621, 540), (445, 529)),
                          'светлый', 'znak'),
    # Площадка на корпусе редуктора - самая большая плоская на этой машине.
    'centrobezhnye':     (((673, 421), (841, 431), (836, 531), (673, 523)),
                          'светлый', 'znak1', (0.80, 0.70, 0.60)),
}


def main():
    vhod = sys.argv[1] if len(sys.argv) > 1 else 'syrye'
    vyhod = sys.argv[2] if len(sys.argv) > 2 else 'syrye-logo'
    risovat = '--risovat' in sys.argv
    os.makedirs(vyhod, exist_ok=True)
    kuski = []
    for imya, nastroyka in PANELI.items():
        panel, kakoy, nabor = nastroyka[:3]
        shiriny = nastroyka[3] if len(nastroyka) > 3 else None
        p = os.path.join(vhod, imya + '.png')
        if not os.path.exists(p):
            print('нет кадра:', p)
            continue
        kadr = Image.open(p).convert('RGBA')
        k = kadr.width / OPORA
        pan = tuple((x * k, y * k) for x, y in panel)
        put = nabor + ('-svetlyy.png' if kakoy == 'светлый' else '.png')
        znak = Image.open(put).convert('RGBA')
        doli, gryaz, dolya = C.nayti_mesto(kadr, pan, znak, shiriny=shiriny)
        ram = C.ramka(pan, doli)
        print('%-20s %-6s ширина %.0f%% панели, грязь %.1f'
              % (imya, nabor, dolya * 100, gryaz), flush=True)
        if risovat:
            im = kadr.convert('RGB')
            d = ImageDraw.Draw(im)
            d.polygon(list(pan), outline=(0, 210, 0), width=5)
            d.polygon(list(ram), outline=(255, 0, 0), width=5)
            im.thumbnail((440, 440))
            kuski.append((imya, im))
        else:
            rezhim = 'умножение' if kakoy == 'тёмный' else 'осветление'
            C.polozhit(kadr, znak, ram, rezhim=rezhim).save(
                os.path.join(vyhod, imya + '.png'))
    if risovat and kuski:
        W = sum(i.width + 10 for _, i in kuski)
        H = max(i.height for _, i in kuski) + 20
        lst = Image.new('RGB', (W, H), 'white')
        d = ImageDraw.Draw(lst)
        x = 0
        for imya, i in kuski:
            d.text((x + 4, 3), imya, fill=(0, 0, 0))
            lst.paste(i, (x, 18))
            x += i.width + 10
        lst.save('mesta.png')


if __name__ == '__main__':
    main()
