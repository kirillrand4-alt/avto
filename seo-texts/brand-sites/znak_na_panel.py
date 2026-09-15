# -*- coding: utf-8 -*-
"""Наложение фирменного знака ENGER на панель машины.

Почему так, а не проще. Две прошлые попытки сажали знак «не туда», и обе
по одной причине: я на глаз ловил маленький прямоугольник под сам знак.
Промах в пять пикселей на такой рамке - это уже перекос или съезд с кромки.

Теперь задаются углы ВСЕЙ панели: их видно точно, ошибка в те же пять
пикселей на панели в пятьсот - ничто. Положение знака внутри панели
считается долями, снятыми с настоящей машины (prokompressor, карточка
Enger HB-37DT): знак стоит внизу слева, ширина примерно 45% ширины панели.

Знак берётся двухъярусный - ENGER плюс COMPRESSOR SYSTEM. Одноярусный,
которым я пользовался раньше, на машинах Enger не стоит нигде.
"""
import os
import sys

from PIL import Image, ImageChops, ImageFilter

OPORA = 1024      # в этой рамке сняты углы; кадр может быть крупнее

# Углы ПАНЕЛИ: левый верх, правый верх, правый низ, левый низ.
# Второе поле - какой знак, тёмный или светлый.
PANELI = {
    # Углы панелей сняты ЗАМЕРОМ, а не на глаз: по строкам и столбцам ищется
    # сплошная светлая область двери. На глаз я промахивался трижды.
    'nizkogo-davleniya': (((336, 170), (712, 199), (712, 761), (336, 796)), 'тёмный', {}),
    'spiralnye':         (((469, 232), (738, 245), (738, 839), (469, 866)), 'тёмный', {}),
    'peredvizhnye':      (((445, 247), (621, 258), (621, 540), (445, 529)), 'светлый', {}),
    # У центробежного ровных дверей нет вовсе: знак идёт на переднюю полку
    # рамы. Полка низкая, поэтому доли свои - иначе знак не влезает по высоте.
    'centrobezhnye':     (((132, 821), (430, 864), (430, 919), (132, 875)), 'светлый',
                          {'shirina': 0.52, 'snizu': 0.16, 'sleva': 0.08}),
}

# Доли сняты с настоящей машины: отступ слева, отступ снизу, ширина знака -
# всё в долях панели.
OTSTUP_SLEVA = 0.10
OTSTUP_SNIZU = 0.09
SHIRINA = 0.45
PLOTNOST = 0.95


def _koef(uglami, w, h):
    """Коэффициенты PIL PERSPECTIVE: выходной квадрат -> входной прямоугольник."""
    cel = [(0, 0), (w, 0), (w, h), (0, h)]
    A, B = [], []
    for (x, y), (u, v) in zip(uglami, cel):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        B.append(v)
    n = 8
    M = [A[i][:] + [B[i]] for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-12:
            raise ValueError('вырожденные углы панели')
        M[i], M[p] = M[p], M[i]
        dl = M[i][i]
        M[i] = [v / dl for v in M[i]]
        for r in range(n):
            if r == i:
                continue
            k = M[r][i]
            if k:
                M[r] = [a - k * b for a, b in zip(M[r], M[i])]
    return [M[i][n] for i in range(n)]


def _tochka(panel, u, v):
    """Точка внутри четырёхугольника по долям u (слева направо) и v (сверху вниз)."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = panel
    verh = (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u)
    niz = (x3 + (x2 - x3) * u, y3 + (y2 - y3) * u)
    return (verh[0] + (niz[0] - verh[0]) * v, verh[1] + (niz[1] - verh[1]) * v)


def ramka_znaka(panel, znak, sleva=OTSTUP_SLEVA, snizu=OTSTUP_SNIZU, shirina=SHIRINA):
    """Четырёхугольник под знак внутри панели, по долям."""
    # высота в долях: считаем через реальные пропорции панели по верхней кромке
    (x0, y0), (x1, y1), _, (x3, y3) = panel
    shir_px = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    vys_px = ((x3 - x0) ** 2 + (y3 - y0) ** 2) ** 0.5
    vysota = shirina * shir_px / (znak.width / znak.height) / vys_px
    u1, u2 = sleva, sleva + shirina
    v2 = 1.0 - snizu
    v1 = v2 - vysota
    return tuple(_tochka(panel, u, v) for u, v in
                 ((u1, v1), (u2, v1), (u2, v2), (u1, v2)))


def polozhit(kadr, znak, uglami, plotnost=PLOTNOST, rezhim='умножение'):
    """Не простой альфой: краска на панели подхватывает её освещение.

    Тёмный знак кладём умножением, светлый осветлением - иначе он светится
    ровно, пока панель под ним уходит в тень, и читается наклейкой.
    """
    sloy = znak.transform(kadr.size, Image.PERSPECTIVE,
                          _koef(uglami, znak.width, znak.height), Image.BICUBIC)
    a = sloy.getchannel('A').filter(ImageFilter.GaussianBlur(0.5))
    a = a.point(lambda v: int(v * plotnost))
    osnova = kadr.convert('RGBA')
    b = osnova.convert('RGB')
    l = sloy.convert('RGB')
    smes = ImageChops.multiply(b, l) if rezhim == 'умножение' else ImageChops.screen(b, l)
    out = osnova.copy()
    out.paste(smes, (0, 0), a)
    return out


def main():
    vhod = sys.argv[1] if len(sys.argv) > 1 else 'syrye'
    vyhod = sys.argv[2] if len(sys.argv) > 2 else 'syrye-logo'
    put = sys.argv[3] if len(sys.argv) > 3 else 'znak.png'
    os.makedirs(vyhod, exist_ok=True)
    koren, rasshirenie = os.path.splitext(put)
    znaki = {'тёмный': Image.open(put).convert('RGBA'),
             'светлый': Image.open(koren + '-svetlyy' + rasshirenie).convert('RGBA')}
    for imya, (panel, kakoy, svoi) in PANELI.items():
        p = os.path.join(vhod, imya + '.png')
        if not os.path.exists(p):
            print('нет кадра:', p)
            continue
        kadr = Image.open(p).convert('RGBA')
        k = kadr.width / OPORA
        pan = tuple((x * k, y * k) for x, y in panel)
        znak = znaki[kakoy]
        ramka = ramka_znaka(pan, znak,
                            sleva=svoi.get('sleva', OTSTUP_SLEVA),
                            snizu=svoi.get('snizu', OTSTUP_SNIZU),
                            shirina=svoi.get('shirina', SHIRINA))
        rezhim = 'умножение' if kakoy == 'тёмный' else 'осветление'
        polozhit(kadr, znak, ramka, rezhim=rezhim).save(os.path.join(vyhod, imya + '.png'))
        print('%-20s знак %s, рамка %s' % (
            imya, kakoy, tuple((round(x), round(y)) for x, y in ramka)), flush=True)


if __name__ == '__main__':
    main()
