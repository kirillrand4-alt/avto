# -*- coding: utf-8 -*-
"""Наложение логотипа ENGER на панель машины с перспективой.

Логотип не просим у модели: генераторы корёжат буквы. Берём настоящий
из каталога и кладём на панель четырьмя углами, снятыми по сетке.
"""
import os
import sys

from PIL import Image, ImageChops

# Углы панели сняты по сетке setka.png, которая рисовалась в опорной рамке
# 1024x1024. Модель отдаёт кадры другого размера (видели 1254), поэтому углы
# пересчитываются под фактическую сторону, а не требуют точного совпадения.
OPORA = 1024
# Левый верх, правый верх, правый низ, левый низ, и какой логотип класть.
# «светлый» - там, где поверхность тёмная и чёрные буквы на ней пропадают:
# на передвижном это графитовый капот, на центробежном - рама-основание.
PANELI = {
    # Углы сняты по зум-сетке с шагом 32 px, а не на глаз: прошлый заход давал
    # наклейку именно потому, что логотип лежал плоско, пока панель уходила вбок.
    'nizkogo-davleniya': (((384, 642), (506, 638), (506, 675), (384, 679)), 'тёмный'),
    'spiralnye':         (((588, 696), (702, 694), (702, 728), (588, 730)), 'тёмный'),
    'peredvizhnye':      (((498, 351), (612, 357), (612, 391), (498, 385)), 'светлый'),
    # На центробежном ровных панелей нет: кладём на стенку рамы-основания.
    # Кромки полосы сняты замером яркости по колонкам, а не на глаз: первый
    # заход промахнулся ниже кромки и логотип свесился на белый фон.
    # Полоса: верх y=900+0,2*(x-180), низ y=948+0,233*(x-180).
    'centrobezhnye':     (((176, 747), (261, 766), (261, 792), (176, 773)), 'светлый'),
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


def polozhit(kadr, logotip, uglami, plotnost=PLOTNOST, rezhim='умножение'):
    """Кладём логотип НЕ простой альфой.

    Простая альфа даёт наклейку: краска светится ровно, пока панель под ней
    уходит в тень. Настоящая печать подхватывает освещение поверхности,
    поэтому тёмный логотип кладём умножением (тень панели проступает сквозь
    буквы), светлый - осветлением. Разница видна сразу.
    """
    from PIL import ImageFilter
    sloy = logotip.transform(kadr.size, Image.PERSPECTIVE,
                             _koef(uglami, logotip.width, logotip.height),
                             Image.BICUBIC)
    # Мягкий край: после перспективы ступеньки, рендер вокруг гладкий.
    a = sloy.getchannel('A').filter(ImageFilter.GaussianBlur(0.5))
    a = a.point(lambda v: int(v * plotnost))
    osnova = kadr.convert('RGBA')
    b = osnova.convert('RGB')
    l = sloy.convert('RGB')
    if rezhim == 'умножение':
        smes = ImageChops.multiply(b, l)
    else:
        smes = ImageChops.screen(b, l)
    out = osnova.copy()
    out.paste(smes, (0, 0), a)
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
        rezhim = 'умножение' if kakoy == 'тёмный' else 'осветление'
        polozhit(kadr, logotipy[kakoy], masshtab, rezhim=rezhim).save(
            os.path.join(vyhod, imya + '.png'))
        print('%-20s логотип %s (%s), масштаб углов x%.3f'
              % (imya, kakoy, rezhim, k), flush=True)


if __name__ == '__main__':
    main()
