# -*- coding: utf-8 -*-
"""Поиск чистой площадки под знак внутри панели.

Три захода подряд знак садился физически невозможно: поперёк стыка двух
дверей, на защёлку, на болт, на угол балки под кабелями. Причина одна - я
выбирал место сам, по долям от краёв панели, и не смотрел, что на этом
месте нарисовано.

Здесь место ищется по картинке. Панель разворачивается в прямоугольник,
считается карта резкости (стыки, петли, болты, кабели дают всплеск), и
окно под знак ставится туда, где сумма всплесков минимальна. Наклейка
физически не может лежать на стыке - значит и мы туда не кладём.
"""
from PIL import Image, ImageChops, ImageFilter

# Доли взяты с настоящей машины Enger HB-37DT: знак занимает около 40%
# ширины панели. Если чистого места столько не набирается, пробуем меньше.
SHIRINY = (0.42, 0.36, 0.30, 0.24)
# Куда тянет при прочих равных: низ-лево, как на настоящих машинах.
TYAGA_VNIZ = 0.55
TYAGA_VLEVO = 0.45
KRAY = 0.06          # к краям панели не прижимаемся


def _koef_tochki(vyhod, vhod):
    """Коэффициенты PIL: точка ВЫХОДА -> точка ВХОДА. Порядок важен.

    Тут я ошибся один раз: разворачивал панель матрицей «панель -> квадрат»,
    а PIL ждёт обратную, и на выходе была пустота. Карта помех при этом
    честно показывала ноль помех где угодно.
    """
    A, B = [], []
    for (x, y), (u, v) in zip(vyhod, vhod):
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
        d = M[i][i]
        M[i] = [v / d for v in M[i]]
        for r in range(n):
            if r == i:
                continue
            k = M[r][i]
            if k:
                M[r] = [a - k * b for a, b in zip(M[r], M[i])]
    return [M[i][n] for i in range(n)]


def _koef(uglami, w, h):
    return _koef_tochki(uglami, [(0, 0), (w, 0), (w, h), (0, h)])


def _tochka(panel, u, v):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = panel
    vx = x0 + (x1 - x0) * u
    vy = y0 + (y1 - y0) * u
    nx = x3 + (x2 - x3) * u
    ny = y3 + (y2 - y3) * u
    return (vx + (nx - vx) * v, vy + (ny - vy) * v)


def razvernut(kadr, panel, storona=360):
    """Панель -> прямоугольник storona x storona, чтобы искать в плоскости."""
    S = storona
    kv = [(0, 0), (S, 0), (S, S), (0, S)]
    return kadr.convert('RGB').transform(
        (S, S), Image.PERSPECTIVE, _koef_tochki(kv, list(panel)), Image.BICUBIC)


def karta_pomeh(ploskost):
    """Резкость: стыки, петли, болты, кабели дают всплеск, гладкая краска нет."""
    g = ploskost.convert('L').filter(ImageFilter.GaussianBlur(0.8))
    kray = ChopsMax(g.filter(ImageFilter.FIND_EDGES))
    return kray


def ChopsMax(im):
    # Раздуваем: мелкий болт в шесть пикселей иначе теряется при выборке.
    return im.filter(ImageFilter.MaxFilter(9))


PORAG_KROMKI = 60
# Выше этого под знаком не должно быть НИЧЕГО: это болт, петля, стык,
# кабель. Мягкий штраф такую мелочь не ловил - она давала доли балла.
ZAPRET = 120


def _summa_okna(pom, x1, y1, x2, y2):
    """Оценка загрязнённости окна.

    Среднего мало: тонкий стык двери поднимает его на единицы, и окно
    поперёк стыка выигрывает у чистого. Поэтому доля резких пикселей
    входит с большим весом - одна кромка через знак уже дисквалифицирует.
    """
    px = pom.load()
    s = 0
    rezkih = 0
    n = 0
    for y in range(y1, y2):
        for x in range(x1, x2):
            v = px[x, y]
            if v > ZAPRET:
                return None          # деталь под знаком - место не годится
            s += v
            if v > PORAG_KROMKI:
                rezkih += 1
            n += 1
    n = max(1, n)
    return s / n + 90.0 * rezkih / n


def nayti_mesto(kadr, panel, znak, storona=360):
    """Доли (u1, v1, u2, v2) под знак: самое чистое место в панели."""
    pl = razvernut(kadr, panel, storona)
    pom = karta_pomeh(pl)
    otn = znak.width / znak.height
    luchshee = None
    for dolya in SHIRINY:
        w = int(storona * dolya)
        h = int(w / otn)
        if h >= storona * 0.6:
            continue
        shag = max(4, storona // 45)
        m = int(storona * KRAY)
        for y in range(m, storona - h - m + 1, shag):
            for x in range(m, storona - w - m + 1, shag):
                gryaz = _summa_okna(pom, x, y, x + w, y + h)
                if gryaz is None:
                    continue
                # при прочих равных тянем вниз и влево, как на живых машинах
                nizh = (y + h / 2) / storona
                levo = (x + w / 2) / storona
                shtraf = TYAGA_VNIZ * (1 - nizh) * 14 + TYAGA_VLEVO * levo * 14
                ocenka = gryaz + shtraf - dolya * 10
                if luchshee is None or ocenka < luchshee[0]:
                    luchshee = (ocenka, gryaz, x / storona, y / storona,
                                (x + w) / storona, (y + h) / storona, dolya)
        # если для этой ширины нашлось совсем чисто - дальше не мельчим
        if luchshee is not None:
            break     # нашлось чистое место этой ширины - мельчить незачем
    if not luchshee:
        raise ValueError('не нашлось места под знак')
    _, gryaz, u1, v1, u2, v2, dolya = luchshee
    return (u1, v1, u2, v2), gryaz, dolya


def ramka(panel, doli):
    u1, v1, u2, v2 = doli
    return tuple(_tochka(panel, u, v) for u, v in
                 ((u1, v1), (u2, v1), (u2, v2), (u1, v2)))


def polozhit(kadr, znak, uglami, plotnost=0.95, rezhim='умножение'):
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
