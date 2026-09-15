# -*- coding: utf-8 -*-
"""Наложение логотипа ENGER на панель машины с перспективой.

Логотип не просим у модели: генераторы корёжат буквы. Берём настоящий
из каталога и кладём на панель четырьмя углами, снятыми по сетке.
"""
import os
import sys

from PIL import Image

# Углы панели сняты по сетке setka.png, которая рисовалась в опорной рамке
# 1024x1024. Модель отдаёт кадры другого размера (видели 1254), поэтому углы
# пересчитываются под фактическую сторону, а не требуют точного совпадения.
OPORA = 1024
# Левый верх, правый верх, правый низ, левый низ, и какой логотип класть.
# «светлый» - там, где поверхность тёмная и чёрные буквы на ней пропадают:
# на передвижном это графитовый капот, на центробежном - рама-основание.
PANELI = {
    'nizkogo-davleniya': (((230, 575), (462, 571), (462, 641), (230, 646)), 'тёмный'),
    'spiralnye':         (((714, 688), (876, 694), (876, 757), (714, 751)), 'тёмный'),
    'peredvizhnye':      (((490, 355), (611, 366), (611, 408), (490, 398)), 'светлый'),
    'centrobezhnye':     (((106, 723), (294, 745), (294, 802), (106, 780)), 'светлый'),
}
PLOTNOST = 0.94        # чуть просвечивает, чтобы не выглядело наклейкой


def _koef(uglami, w, h):
    """Коэффициенты PIL для PERSPECTIVE: выходной квадрат -> входной прямоугольник."""
    cel = [(0, 0), (w, 0), (w, h), (0, h)]
    A, B = [], []
    for (x, y), (u, v) in zip(uglami, cel):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        B.append(v)
    # решаем 8x8 методом Гаусса, без numpy
    n = 8
    M = [A[i][:] + [B[i]] for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-12:
            raise ValueError('вырожденные углы панели')
        M[i], M[p] = M[p], M[i]
        d = M[i][i]
        M[i] = [v / d for v in M[i]]
        for r in range(n):
            if r == i:
                continue
            k = M[r][i]
            if k:
                M[r] = [a - k * b for a, b in zip(M[r], M[i])]
    return [M[i][n] for i in range(n)]


def polozhit(kadr, logotip, uglami, plotnost=PLOTNOST):
    holst = Image.new('RGBA', kadr.size, (0, 0, 0, 0))
    sloy = logotip.transform(kadr.size, Image.PERSPECTIVE,
                             _koef(uglami, logotip.width, logotip.height),
                             Image.BICUBIC)
    a = sloy.getchannel('A').point(lambda v: int(v * plotnost))
    sloy.putalpha(a)
    holst.alpha_composite(sloy)
    out = kadr.convert('RGBA')
    out.alpha_composite(holst)
    return out


def main():
    vhod = sys.argv[1] if len(sys.argv) > 1 else 'syrye'
    vyhod = sys.argv[2] if len(sys.argv) > 2 else 'syrye-logo'
    put_logo = sys.argv[3] if len(sys.argv) > 3 else 'logo.png'
    os.makedirs(vyhod, exist_ok=True)
    koren, rasshirenie = os.path.splitext(put_logo)
    logotipy = {'тёмный': Image.open(put_logo).convert('RGBA'),
                'светлый': Image.open(koren + '-svetlyy' + rasshirenie).convert('RGBA')}
    for imya, (uglami, kakoy) in PANELI.items():
        p = os.path.join(vhod, imya + '.png')
        if not os.path.exists(p):
            print('нет кадра:', p)
            continue
        kadr = Image.open(p).convert('RGBA')
        if kadr.width != kadr.height:
            raise ValueError('ожидался квадратный кадр, а тут %s' % (kadr.size,))
        k = kadr.width / OPORA
        masshtab = tuple((round(x * k), round(y * k)) for x, y in uglami)
        polozhit(kadr, logotipy[kakoy], masshtab).save(os.path.join(vyhod, imya + '.png'))
        print('%-20s логотип %s, масштаб углов x%.3f' % (imya, kakoy, k), flush=True)


if __name__ == '__main__':
    main()
