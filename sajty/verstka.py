#!/usr/bin/env python3
# coding: utf-8
"""Вёрстка статей для всех сайтов из архива «дорогие плановые».

Исходники размечены классами cta, cta-knopka, na-stranice - их рисует
stili-dlya-sayta.css, которого на сайтах нет. Скрипт переводит статью в
инлайновые стили: страница выглядит одинаково на любом сайте и ничего от
темы не требует.

Отличия от версии для ac-kompressor.ru (ac-kompressor/verstka.py):

- цвета нейтральные. Плашка призыва - серая заливка rgba и полоса слева
  цветом текста (currentColor), таблицы и оглавление в серых rgba-рамках.
  У сайтов разные темы (синяя, красная, жёлтая, зелёная), свой акцент
  подрался бы с любой из них;
- кнопка оставлена в родном классе сайта (btn btn-primary и т.п.) - цвет
  берётся из темы. Инлайном добавлены только три правила: не растягиваться
  во всю ширину, не подчёркиваться, не съезжать по вертикали;
- обработчик кнопки дописывается только тем сайтам, где в Битрикс24 есть
  подходящая форма (см. САЙТЫ ниже). Где её нет - кнопка остаётся обычной
  ссылкой на страницу заявки, как в исходниках.

Запуск:  python3 verstka.py ishodniki/<домен>/*.html
"""

import io
import os
import re
import sys

# Что и куда. Форма - id формы Битрикс24 с видом click, которую открывает
# кнопка в статье. Проверено по загрузчикам loader_<id>_<sec>.js и по тому,
# есть ли эта форма на внутренних страницах каталога, а не только на главной.
SAJTY = {
    "abac-kompressor.ru": dict(
        klass="bxr-color-button", stil="color:#1a1a1a;",
        zakaz="https://abac-kompressor.ru/company/contacts/", forma=None),
    "berg-kompressor.ru": dict(
        klass="btn btn-primary", stil="color:#fff;",
        zakaz="https://berg-kompressor.ru/contacts/", forma=None, shapka=130),
    "crossair-compressor.ru": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://crossair-compressor.ru/about/contacts/", forma="click/173/5pc41r"),
    "dali-kompressor.ru": dict(
        klass="btn btn-outline-primary btn-request-kp", stil="",
        zakaz="https://dali-kompressor.ru/company/contacts/", forma="click/7/40ef1t"),
    "ekomak-kompressor.com": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://ekomak-kompressor.com/contacts/", forma=None),
    "enger-air.ru": dict(
        klass="enger-btn enger-btn--primary", stil="",
        zakaz="https://enger-air.ru/company/contacts/", forma=None, shapka=60),
    "fini-compressor.com": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://fini-compressor.com/about/contacts/", forma=None),
    "ironmac-compressor.com": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://ironmac-compressor.com/company/contacts/", forma=None),
    "remeza-kompressor.ru": dict(
        klass="bxr-color-button", stil="color:#1a1a1a;",
        zakaz="https://remeza-kompressor.ru/company/contacts/", forma=None),
    "zif-kompressor.ru": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://zif-kompressor.ru/company/where-buy/", forma="click/7/40ef1t"),
}

NADPIS = "Получить КП"
TRIGGER = "kp-trigger"

RAMKA = "rgba(0,0,0,.12)"
ZALIVKA = "rgba(0,0,0,.04)"
H2_STIL = "scroll-margin-top:{}px;margin-top:42px;"   # {} - высота липкой шапки сайта
TABL_STIL = ("width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;"
             f"margin:22px 0 30px;border:1px solid {RAMKA};")
TH_STIL = (f"padding:11px 12px;border:1px solid {RAMKA};background:{ZALIVKA};"
           "text-align:left;vertical-align:top;white-space:normal;")
TD_STIL = f"padding:11px 12px;border:1px solid {RAMKA};text-align:left;vertical-align:top;"
SERYY = "margin-top:28px;color:#6b747c;font-size:14px;"
KNOPKA_PRAVKI = ("display:inline-block !important;width:auto !important;max-width:100%;"
                 "text-decoration:none !important;vertical-align:middle;")

GLAGOLY = r"(?:Получить|Рассчитать|Подобрать|Прислать|Отправить|Уточнить|Оставить|Заказать|Запросить)"


def knopka(sajt):
    return (f'<a href="{sajt["zakaz"]}" class="{sajt["klass"]} {TRIGGER}" '
            f'style="{KNOPKA_PRAVKI}{sajt["stil"]}">{NADPIS}</a>')


def snippet(sajt):
    """Обработчик кнопки. Нажимает ту кнопку сайта, к которой Битрикс24 привязал
    форму, и открывается тот же попап. Дописывается только если форма есть."""
    if not sajt["forma"]:
        return ""
    return f'''<!-- Кнопки "{NADPIS}" в статье открывают форму Битрикс24 {sajt["forma"]}:
     нажимают ту кнопку сайта, к которой её привязал сам Битрикс24. -->
<script>
(function () {{
\tif (window.kpTriggerReady) {{ return; }}
\twindow.kpTriggerReady = true;

\tvar TRIGGER  = "{TRIGGER}";
\tvar B24_FORM = "{sajt["forma"]}";
\tvar FALLBACK = "{sajt["zakaz"]}";
\tvar WAIT_MS  = 2500;
\tvar STEP_MS  = 150;

\t/* Битрикс24 вешает обработчик на элемент сразу за своим тегом script и
\t   помечает этот script атрибутом data-b24-loaded. */
\tfunction knopkaSajta() {{
\t\tvar scripts = document.querySelectorAll('script[data-b24-form="' + B24_FORM + '"][data-b24-loaded]');
\t\tfor (var i = scripts.length - 1; i >= 0; i--) {{
\t\t\tvar el = scripts[i].nextElementSibling;
\t\t\tif (!el || el.tagName === "SCRIPT") {{ continue; }}
\t\t\treturn (el.querySelector && el.querySelector(".b24-form-click-btn")) || el;
\t\t}}
\t\treturn null;
\t}}

\tfunction izTriggera(node) {{
\t\twhile (node && node !== document) {{
\t\t\tif (node.classList && node.classList.contains(TRIGGER)) {{ return node; }}
\t\t\tnode = node.parentNode;
\t\t}}
\t\treturn null;
\t}}

\tfunction otkryt(waited, link) {{
\t\tvar btn = knopkaSajta();
\t\tif (btn) {{
\t\t\t/* кнопка сайта часто <a href="#"> - не даём странице прыгнуть наверх */
\t\t\tvar y = window.pageYOffset;
\t\t\tbtn.click();
\t\t\tsetTimeout(function () {{ if (Math.abs(window.pageYOffset - y) > 4) {{ window.scrollTo(0, y); }} }}, 0);
\t\t\treturn;
\t\t}}
\t\tif (waited >= WAIT_MS) {{
\t\t\twindow.location.href = (link && link.getAttribute("href")) || FALLBACK;
\t\t\treturn;
\t\t}}
\t\tsetTimeout(function () {{ otkryt(waited + STEP_MS, link); }}, STEP_MS);
\t}}

\tdocument.addEventListener("click", function (e) {{
\t\tvar link = izTriggera(e.target);
\t\tif (!link) {{ return; }}
\t\te.preventDefault();
\t\totkryt(0, link);
\t}}, false);
}})();
</script>'''


TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}


def yakor(tekst, zanyatye):
    """Якорь для заголовка, у которого его нет в исходнике."""
    lat = "".join(TRANSLIT.get(c, c) for c in tekst.lower())
    lat = re.sub(r"[^a-z0-9]+", "-", lat).strip("-")[:60].rstrip("-")
    ident, n = lat or "razdel", 2
    while ident in zanyatye:
        ident, n = f"{lat}-{n}", n + 1
    zanyatye.add(ident)
    return ident


def bez_tegov(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def zagolovok_i_podpis(tekst):
    t = re.sub(r"</?strong>", "", tekst).strip()
    dvoetochie = t.find(":")
    if 0 < dvoetochie < 90:
        zag, pod = t[:dvoetochie], t[dvoetochie + 1:]
    else:
        tochka = re.search(r"\.\s+", t)
        if tochka and tochka.start() < 90:
            zag, pod = t[:tochka.start()], t[tochka.end():]
        elif " - " in t:
            zag, pod = t.split(" - ", 1)
        else:
            return t.rstrip(" .:"), ""
    pod = pod.strip()
    if pod:
        pod = pod[0].upper() + pod[1:]
        if not pod.endswith((".", "!", "?")):
            pod += "."
    return zag.strip(" .:"), pod


def razvesti_prizyvy(tekst, skolko):
    if skolko < 2:
        return [tekst]
    granicy = [m.start() + 1 for m in re.finditer(rf"\.\s+(?={GLAGOLY}\s)", tekst)]
    if len(granicy) != skolko - 1:
        return [tekst]
    chasti, nachalo = [], 0
    for g in granicy + [len(tekst)]:
        chasti.append(tekst[nachalo:g].strip())
        nachalo = g
    return chasti


def plashka(tekst, nadpisi, sajt):
    out = []
    for chast, _ in zip(razvesti_prizyvy(tekst, len(nadpisi)), nadpisi):
        zag, pod = zagolovok_i_podpis(chast)
        blok = ('<div style="margin:22px 0 30px;padding:18px 20px;'
                f'border-left:4px solid currentColor;background:rgba(0,0,0,.055);">'
                f'<p style="margin:0;font-size:18px;"><strong>{zag}</strong></p>')
        if pod:
            blok += f'<p style="margin:4px 0 0;color:#69757f;font-size:14px;">{pod}</p>'
        blok += f'<p style="margin:14px 0 0;">{knopka(sajt)}</p></div>'
        out.append(blok)
    return "\n".join(out)


def soderzhanie(razdely, sajt):
    punkty = "\n".join(
        f'<li style="margin:0 0 7px;break-inside:avoid;"><a href="#{ident}">{nazvanie}</a></li>'
        for ident, nazvanie in razdely)
    return (
        f'<div style="margin:24px 0 30px;padding:18px 20px;border:1px solid {RAMKA};background:{ZALIVKA};">'
        '<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;'
        'gap:14px;margin:0 0 12px;">'
        '<p style="margin:0;"><strong>Содержание страницы</strong></p>'
        f'{knopka(sajt)}</div>'
        '<ol style="margin:0;padding-left:22px;columns:280px 2;column-gap:36px;">\n'
        f'{punkty}\n</ol></div>')


def tablica(vnutri):
    t = re.sub(r"<table[^>]*>",
               '<table style="width:100%;min-width:720px;border-collapse:collapse;margin:0;">', vnutri)
    t = re.sub(r"<th[^>]*>", f'<th style="{TH_STIL}">', t)
    t = re.sub(r"<td[^>]*>", f'<td style="{TD_STIL}">', t)
    return f'<div class="tablica-prokrutka" style="{TABL_STIL}">{t.strip()}</div>'


BLOK = re.compile(
    r'<div class="tablica-prokrutka">(?P<tabl>.*?)</div>'
    r'|<h2(?P<h2attr>[^>]*)>(?P<h2>.*?)</h2>'
    r'|<h3[^>]*>(?P<h3>.*?)</h3>'
    r'|<p(?P<attr>[^>]*)>(?P<p>.*?)</p>', re.S)


def perevesti(ishodnik, sajt):
    koren = re.search(r'<div class="statya-ruspro"[^>]*>(.*)</div>', ishodnik, re.S)
    assert koren, "не найден div.statya-ruspro"
    telo = koren.group(1)
    zanyatye, razdely, yakorya = set(), [], {}
    for m in re.finditer(r'<h2([^>]*)>(.*?)</h2>', telo, re.S):
        nazvanie = bez_tegov(m.group(2))
        est = re.search(r'id="([^"]+)"', m.group(1))
        ident = est.group(1) if est else yakor(nazvanie, zanyatye)
        zanyatye.add(ident)
        yakorya[m.start()] = ident
        razdely.append((ident, nazvanie))
    est_faq = any(i == "chastye-voprosy" for i, _ in razdely)
    est_toc = 'class="na-stranice"' in telo
    if not est_faq and "<h3" in telo:                 # FAQ без своего заголовка
        razdely.append(("chastye-voprosy", "Частые вопросы"))

    bloki = list(BLOK.finditer(telo))
    out, faq, prizyv, i = [], False, None, 0
    while i < len(bloki):
        m = bloki[i]
        tekst = m.group("p")
        klass = re.search(r'class="([^"]*)"', m.group("attr") or "") if tekst is not None else None
        klass = klass.group(1) if klass else ""

        if m.group("tabl") is not None:
            out.append(tablica(m.group("tabl")))
        elif m.group("h2") is not None:
            ident = yakorya.get(m.start(), "")
            out.append(f'<h2 id="{ident}" style="{H2_STIL.format(sajt.get("shapka", 90))}">{m.group("h2")}</h2>')
            if ident == "chastye-voprosy":
                out.append('<div style="margin:18px 0 30px;">')
                faq = True
        elif m.group("h3") is not None:
            if not faq:                                # в исходнике FAQ без заголовка
                out.append(f'<h2 id="chastye-voprosy" style="{H2_STIL}">Частые вопросы</h2>')
                out.append('<div style="margin:18px 0 30px;">')
                faq = True
            otvety, j = [], i + 1
            while j < len(bloki) and bloki[j].group("p") is not None:
                t = bloki[j].group("p")
                if "Дата обновления" in t or bez_tegov(t).startswith("Сведения"):
                    break
                otvety.append(f'<p style="margin:0;">{t.strip()}</p>')
                j += 1
            out.append(
                '<details style="border-bottom:1px solid #e1e5e8;padding:0;">\n'
                '<summary style="cursor:pointer;padding:17px 0;font-size:18px;'
                f'font-weight:600;line-height:1.4;">{m.group("h3").strip()}</summary>\n'
                f'<div style="padding:0 0 18px;">{"".join(otvety)}</div>\n</details>')
            i = j - 1
        elif klass == "na-stranice":
            out.append(soderzhanie(razdely, sajt))
        elif klass == "cta":
            prizyv = tekst
        elif klass == "cta-knopka":
            nadpisi = re.findall(r">([^<]+)</a>", tekst)
            out.append(plashka(prizyv if prizyv is not None else "", nadpisi, sajt))
            prizyv = None
        elif "Дата обновления" in tekst or bez_tegov(tekst).startswith("Сведения"):
            if faq:
                out.append("</div>")
                faq = False
            data = bez_tegov(tekst)
            if data.startswith("Дата обновления") and not data.endswith("."):
                data += "."
            out.append(f'<p style="{SERYY}">{data}</p>')
        else:
            out.append(f"<p>{tekst.strip()}</p>")
            if not est_toc:                            # оглавления в исходнике нет
                out.append(soderzhanie(razdely, sajt))
                est_toc = True
        i += 1

    if faq:
        out.append("</div>")
    # text-align:left - у части сайтов контейнер раздела центрует текст,
    # и статья на 40 тысяч знаков ложится по центру
    statya = ('<div class="statya-ruspro" style="line-height:1.65;overflow-wrap:break-word;'
              'text-align:left;">\n'
              + "\n".join(out) + "\n</div>")
    hvost = snippet(sajt)
    return statya + ("\n\n" + hvost if hvost else "") + "\n"


def main():
    korn = os.path.dirname(os.path.abspath(__file__))
    for put in sys.argv[1:]:
        domen = os.path.basename(os.path.dirname(os.path.abspath(put)))
        sajt = SAJTY.get(domen)
        if not sajt:
            print(f"пропуск {put}: домен {domen} не в реестре")
            continue
        gotovo = perevesti(io.open(put, encoding="utf-8").read(), sajt)
        papka = os.path.join(korn, domen)
        os.makedirs(papka, exist_ok=True)
        imya = re.sub(r'^[a-z0-9-]+--', '', os.path.basename(put))
        io.open(os.path.join(papka, imya), "w", encoding="utf-8", newline="\r\n").write(gotovo)
        print(f'{domen}/{imya:40} {len(gotovo.encode("utf-8")):6} байт'
              f'{"  + обработчик формы " + sajt["forma"] if sajt["forma"] else ""}')


if __name__ == "__main__":
    main()
