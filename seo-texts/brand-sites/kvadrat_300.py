# -*- coding: utf-8 -*-
"""Из сгенерированного кадра на белом - прозрачный PNG 300x300.

Порядок: снять белый фон заливкой от краёв, обрезать по содержимому,
вписать в квадрат с полем, сохранить с альфой. Пропорции не трогаем.
"""
import os
import sys

from PIL import Image

STORONA = 300
POLE = 10          # пикселей воздуха с каждой стороны итогового квадрата
PORAG = 18         # насколько пиксель может отличаться от белого и всё ещё фон


def _fon_proch(im, porog=PORAG):
    """Заливка от четырёх краёв: снимаем связный белый, внутренний белый корпуса
    при этом остаётся. Обычная маска «всё светлое - прозрачно» съедала бы
    светло-серые панели машины."""
    im = im.convert('RGBA')
    w, h = im.size
    px = im.load()
    belo = lambda t: t[0] >= 255 - porog and t[1] >= 255 - porog and t[2] >= 255 - porog
    vidno = bytearray(w * h)
    stek = []
    for x in range(w):
        stek.append((x, 0))
        stek.append((x, h - 1))
    for y in range(h):
        stek.append((0, y))
        stek.append((w - 1, y))
    while stek:
        x, y = stek.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        i = y * w + x
        if vidno[i]:
            continue
        if not belo(px[x, y]):
            continue
        vidno[i] = 1
        stek.append((x + 1, y))
        stek.append((x - 1, y))
        stek.append((x, y + 1))
        stek.append((x, y - 1))
    for y in range(h):
        b = y * w
        for x in range(w):
            if vidno[b + x]:
                r, g, bl, _ = px[x, y]
                px[x, y] = (r, g, bl, 0)
    return im


def _sgladit(im):
    """Край после заливки ступенчатый. Размываем альфу на полпикселя и
    поджимаем контраст - получается ровная кромка без ореола."""
    a = im.getchannel('A')
    from PIL import ImageFilter
    a = a.filter(ImageFilter.GaussianBlur(0.6)).point(lambda v: 0 if v < 90 else (255 if v > 165 else v))
    im.putalpha(a)
    return im


def kvadrat(put_vhod, put_vyhod, storona=STORONA, pole=POLE):
    im = Image.open(put_vhod).convert('RGBA')
    im = _sgladit(_fon_proch(im))
    kor = im.getbbox()
    if not kor:
        raise ValueError('после снятия фона ничего не осталось: ' + put_vhod)
    im = im.crop(kor)
    mesto = storona - 2 * pole
    k = min(mesto / im.width, mesto / im.height)
    novyy = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))),
                      Image.LANCZOS)
    holst = Image.new('RGBA', (storona, storona), (0, 0, 0, 0))
    holst.paste(novyy, ((storona - novyy.width) // 2, (storona - novyy.height) // 2), novyy)
    holst.save(put_vyhod)
    return kor, novyy.size


def main():
    vhod = sys.argv[1] if len(sys.argv) > 1 else 'syrye'
    vyhod = sys.argv[2] if len(sys.argv) > 2 else 'gotovo-300'
    os.makedirs(vyhod, exist_ok=True)
    for f in sorted(os.listdir(vhod)):
        if not f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            continue
        p = os.path.join(vyhod, os.path.splitext(f)[0] + '.png')
        kor, razmer = kvadrat(os.path.join(vhod, f), p)
        print('%-28s обрез %s -> %s, сохранено %s' % (f, kor, razmer, p), flush=True)


if __name__ == '__main__':
    main()
