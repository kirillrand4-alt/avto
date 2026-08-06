"""Shared Jinja2 templates environment."""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _numfmt(v) -> str:
    try:
        return f"{int(round(float(v))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(v)


def _pct(v) -> str:
    return "—" if v is None else f"{v:+.1f}%"


def _ctr(v) -> str:
    try:
        return f"{float(v) * 100:.2f}%"
    except (TypeError, ValueError):
        return "—"


def _pos(v) -> str:
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "—"


_SOURCE_LABELS = {
    "gsc": "Google",
    "yandex_webmaster": "Яндекс",
    "yandex_metrika": "Метрика",
}


def _srclabel(code) -> str:
    return _SOURCE_LABELS.get(code, code)


templates.env.filters["numfmt"] = _numfmt
templates.env.filters["pct"] = _pct
templates.env.filters["ctr"] = _ctr
templates.env.filters["pos"] = _pos
templates.env.filters["srclabel"] = _srclabel

def _podpis_istochnika(source: object, url: object = "") -> str:
    # Подпись источника: домен страницы вместо имени нашей выкладки.
    # На карточке стояло «Источник: P25-LYUDI-2S.csv» — имя файла, который
    # мы сами же и положили, при живой ссылке на настоящую страницу.
    # Продавцу нужна страница; имя файла остаётся в подсказке.
    s = str(source or "").strip()
    u = str(url or "").strip()
    if not u.startswith("http"):
        return s
    if not (s.lower().endswith((".csv", ".json", ".jsonl", ".xlsx"))
            or ".csv" in s.lower()):
        return s
    try:
        domen = u.split("//", 1)[1].split("/", 1)[0].replace("www.", "")
    except IndexError:
        return s
    return domen or s


templates.env.filters["podpis_istochnika"] = _podpis_istochnika


# Overridden in app.main.create_app() with the configured base path ("" or "/stat").
templates.env.globals.setdefault("base_path", "")


# ------------------------------------------------- человекочитаемые деньги
# Владелец 28.07: «1800000000.0 за 2025 год» нечитаемо, порядок считают
# пальцем. Живут ЗДЕСЬ, а не в роутере: centro.html рендерит routes_centro_sales,
# и помощник, положенный в контекст другого модуля, для него не существует
# (28.07 карточка легла с «money_ru is undefined»). В web.py объект templates
# и рождается — значит, помощники видит любой шаблон приложения.
_DEN_RAZRYADY = ((1e12, "трлн"), (1e9, "млрд"), (1e6, "млн"), (1e3, "тыс"))


def _kak_chislo(value):
    """Строку/число -> float, иначе None.

    ВАЖНО: сюда прилетает и jinja2.Undefined — в шаблоне цепочка
    «company.ssch or company.employees or company.staff» отдаёт последнее
    звено как Undefined, если ключа нет. Любая операция над ним (float,
    .replace, сравнение) бросает UndefinedError и роняет страницу в 500
    (наступили 28.07). Поэтому: работаем ТОЛЬКО с настоящими числами и
    строками, всё остальное — None, а не «попробуем и посмотрим».
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        chist = value.replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
        chist = chist.replace(",", ".")
        try:
            return float(chist)
        except ValueError:
            return None
    return None


def money_ru(value, suffix: str = " \u20bd") -> str:
    """1800000000.0 -> «1,8 млрд ₽»; 148100000 -> «148,1 млн ₽».

    Дробную часть пишем запятой и только когда она значима: «25 млрд», а не
    «25,0 млрд». Значение, которое источник уже отформатировал («1,2 млрд»)
    или которое вовсе не число («н/д»), отдаём как есть.
    """
    chislo = _kak_chislo(value)
    if chislo is None:
        # строку источника («1,2 млрд», «н/д») сохраняем, Undefined/None -> ""
        return value if isinstance(value, str) else ""
    znak = "-" if chislo < 0 else ""
    x = abs(chislo)
    for porog, imya in _DEN_RAZRYADY:
        if x >= porog:
            v = x / porog
            text = f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")
            return f"{znak}{text} {imya}{suffix}"
    return f"{znak}{x:,.0f}".replace(",", "\u202f") + suffix


def count_ru(value) -> str:
    """Штуки (сотрудники): точное число с разрядами, без ₽ и без «тыс».
    779 -> «779», 4500 -> «4 500». Округлять штат нельзя: продажник смотрит
    на размер предприятия, ему нужна точная цифра."""
    chislo = _kak_chislo(value)
    if chislo is None:
        return value if isinstance(value, str) else ""
    return f"{chislo:,.0f}".replace(",", "\u202f")


templates.env.globals["money_ru"] = money_ru
templates.env.globals["count_ru"] = count_ru
