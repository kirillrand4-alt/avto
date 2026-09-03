#!/usr/bin/env python3
# coding: utf-8
"""Вёрстка статей для всех сайтов из архивов «дорогие плановые» и
«есть категория».

Исходники размечены классами cta, cta-knopka, na-stranice - их рисует
stili-dlya-sayta.css, которого на сайтах нет. Скрипт переводит статью в
инлайновые стили: страница выглядит одинаково на любом сайте и ничего от
темы не требует.

Два профиля оформления:

- ac-kompressor.ru - как уже стоит на живом сайте: своя белая кнопка с
  текстом акцентного цвета, цветная полоса у плашек призыва;
- все остальные - нейтральный: серая заливка rgba, полоса слева цветом
  текста (currentColor), кнопка в родном классе сайта (btn btn-primary
  и т.п.), цвет берёт из темы. У сайтов разные темы, свой акцент подрался
  бы с любой из них.

Обработчик кнопки дописывается только тем сайтам, где в Битрикс24 есть
подходящая форма (поле forma в реестре). Где её нет - кнопка остаётся
обычной ссылкой на страницу заявки, как в исходниках.

Запуск:  python3 verstka.py <файлы исходников>
Домен определяется по имени папки, в которой лежит исходник.
"""

import io
import os
import re
import sys

# Что и куда. forma - id формы Битрикс24 с видом click, которую открывает
# кнопка в статье; проверено по загрузчикам loader_<id>_<sec>.js и по тому,
# есть ли форма на внутренних страницах каталога, а не только на главной.
# shapka - высота липкой шапки сайта, замерена в браузере.
SAJTY = {
    "abac-kompressor.ru": dict(
        klass="bxr-color-button", stil="color:#1a1a1a;",
        zakaz="https://abac-kompressor.ru/company/contacts/", forma="click/7/40ef1t"),
    "ac-kompressor.ru": dict(
        klass=None, stil="", akcent="#0096d6", trigger="ac-kp-trigger", shapka=110,
        zakaz="https://ac-kompressor.ru/company/zakaz/", forma="click/7/40ef1t"),
    "berg-kompressor.ru": dict(
        klass="btn btn-primary", stil="color:#fff;", shapka=130,
        zakaz="https://berg-kompressor.ru/contacts/", forma="click/164/7higok",
        nadpis="Оставить заявку"),
    "crossair-compressor.ru": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://crossair-compressor.ru/about/contacts/", forma="click/173/5pc41r"),
    "dali-kompressor.ru": dict(
        klass="btn btn-outline-primary btn-request-kp", stil="",
        zakaz="https://dali-kompressor.ru/company/contacts/", forma="click/7/40ef1t"),
    "ekomak-kompressor.com": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://ekomak-kompressor.com/contacts/", forma="click/8/cosa3e",
        nadpis="Оставить заявку"),
    "enger-air.ru": dict(
        klass="enger-btn enger-btn--primary", stil="", shapka=60,
        zakaz="https://enger-air.ru/company/contacts/", forma="click/160/lzzwog"),
    "fini-compressor.com": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://fini-compressor.com/about/contacts/", forma="click/200/pkoq43",
        nadpis="Оставить заявку"),
    "ironmac-compressor.com": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://ironmac-compressor.com/company/contacts/", forma="click/193/h77r1g",
        nadpis="Оставить заявку"),
    "kraftmann-kompressor.com": dict(
        klass="bxr-color-button", stil="",
        zakaz="https://kraftmann-kompressor.com/contacts/", forma="click/7/40ef1t"),
    "remeza-kompressor.ru": dict(
        klass="bxr-color-button", stil="color:#1a1a1a;",
        zakaz="https://remeza-kompressor.ru/company/contacts/", forma="click/7/40ef1t"),
    "zif-kompressor.ru": dict(
        klass="btn btn-primary", stil="",
        zakaz="https://zif-kompressor.ru/company/where-buy/", forma="click/7/40ef1t"),
}

NADPIS = "Получить КП"
TRIGGER = "kp-trigger"

RAMKA = "rgba(0,0,0,.12)"
ZALIVKA = "rgba(0,0,0,.04)"
SERYY = "margin-top:28px;color:#6b747c;font-size:14px;"
KNOPKA_PRAVKI = ("display:inline-block !important;width:auto !important;max-width:100%;"
                 "text-decoration:none !important;vertical-align:middle;")
KNOPKA_SVOYA = ("display:inline-block !important;box-sizing:border-box;min-width:168px;"
                "padding:15px 28px;background:#fff !important;border:1px solid #e5e5e5;"
                "color:{} !important;font-size:15px;line-height:20px;font-weight:700;"
                "text-align:center;text-decoration:none !important;cursor:pointer;"
                "vertical-align:middle;")

GLAGOLY = r"(?:Получить|Рассчитать|Подобрать|Прислать|Отправить|Уточнить|Оставить|Заказать|Запросить)"
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}


def cveta(sajt):
    """У ac-kompressor свой акцент, у остальных нейтральные серые."""
    if sajt.get("akcent"):
        return dict(polosa=sajt["akcent"], zalivka="#f6f8fa", ramka="#d9e0e5",
                    ramka_t="#dfe5ea", zalivka_t="#eef3f6")
    return dict(polosa="currentColor", zalivka="rgba(0,0,0,.055)", ramka=RAMKA,
                ramka_t=RAMKA, zalivka_t=ZALIVKA)


def knopka(sajt):
    trigger = sajt.get("trigger", TRIGGER)
    nadpis = sajt.get("nadpis", NADPIS)
    if sajt.get("akcent"):
        return (f'<a href="{sajt["zakaz"]}" class="{trigger}" '
                f'style="{KNOPKA_SVOYA.format(sajt["akcent"])}">{nadpis}</a>')
    return (f'<a href="{sajt["zakaz"]}" class="{sajt["klass"]} {trigger}" '
            f'style="{KNOPKA_PRAVKI}{sajt["stil"]}">{nadpis}</a>')


def snippet(sajt):
    """Загрузчик формы Битрикс24 плюс обработчик кнопок.

    Форму вставляем в саму статью: на разделах без товаров у сайта своих форм
    на странице нет, и кнопка иначе уводила бы на страницу заявки. Загрузчик
    привязывает форму к скрытой ссылке, а кнопки в тексте нажимают её -
    попап открывается на любой странице.

    Запасные пути, если загрузчик не отработал: любая другая форма Битрикс24,
    которая нашлась на странице, и только потом переход на страницу заявки.
    """
    if not sajt["forma"]:
        return ""
    trigger = sajt.get("trigger", TRIGGER)
    nadpis = sajt.get("nadpis", NADPIS)
    flag = "acKpTriggerReady" if trigger == "ac-kp-trigger" else "kpTriggerReady"
    vid, nomer, kod = sajt["forma"].split("/")
    yakor = trigger + "-yakor"

    zagruzchik = (
        '<script data-b24-form="{forma}" data-skip-moving="true">\n'
        "(function(w,d,u){{\n"
        "var s=d.createElement('script');s.async=true;s.src=u+'?'+(Date.now()/180000|0);\n"
        "var h=d.getElementsByTagName('script')[0];h.parentNode.insertBefore(s,h);\n"
        "}})(window,document,'https://bitrix-po22.ru/upload/crm/form/loader_{nomer}_{kod}.js');\n"
        "</script>\n"
        # именно span, а не ссылка: Битрикс24 привязывает форму к элементу
        # сразу за своим script, а клик по ссылке с адресом уводил бы страницу
        # раньше, чем откроется попап
        '<span class="{yakor}" style="display:none" aria-hidden="true"></span>'
    ).format(forma=sajt["forma"], nomer=nomer, kod=kod, yakor=yakor)

    obrabotchik = """<script>
(function () {
	if (window.FLAG) { return; }
	window.FLAG = true;

	var TRIGGER  = "TRIGGER_KLASS";
	var B24_FORM = "B24_FORMA";
	var FALLBACK = "ADRES_ZAYAVKI";
	var WAIT_MS  = 6000;
	var STEP_MS  = 150;

	/* Битрикс24 вешает обработчик на элемент сразу за тегом script своей формы
	   и помечает этот script атрибутом data-b24-loaded. Сначала ищем нашу
	   форму (её загрузчик стоит в конце статьи), потом любую другую на странице. */
	function posle(selektor) {
		var scripts = document.querySelectorAll(selektor);
		for (var i = scripts.length - 1; i >= 0; i--) {
			var el = scripts[i].nextElementSibling;
			if (!el || el.tagName === "SCRIPT") { continue; }
			return (el.querySelector && el.querySelector(".b24-form-click-btn")) || el;
		}
		return null;
	}

	function cel() {
		return posle('script[data-b24-form="' + B24_FORM + '"][data-b24-loaded]')
			|| posle('script[data-b24-form^="click/"][data-b24-loaded]');
	}

	function izTriggera(node) {
		while (node && node !== document) {
			if (node.classList && node.classList.contains(TRIGGER)) { return node; }
			node = node.parentNode;
		}
		return null;
	}

	function otkryt(waited, link) {
		var el = cel();
		if (el) {
			/* кнопки сайта часто <a href="#"> - не даём странице прыгнуть наверх */
			var y = window.pageYOffset;
			el.click();
			setTimeout(function () { if (Math.abs(window.pageYOffset - y) > 4) { window.scrollTo(0, y); } }, 0);
			return;
		}
		if (waited >= WAIT_MS) {          /* форма так и не поднялась */
			window.location.href = (link && link.getAttribute("href")) || FALLBACK;
			return;
		}
		setTimeout(function () { otkryt(waited + STEP_MS, link); }, STEP_MS);
	}

	document.addEventListener("click", function (e) {
		var link = izTriggera(e.target);
		if (!link) { return; }
		e.preventDefault();
		otkryt(0, link);
	}, false);
})();
</script>"""
    obrabotchik = (obrabotchik.replace("FLAG", flag)
                   .replace("TRIGGER_KLASS", trigger)
                   .replace("B24_FORMA", sajt["forma"])
                   .replace("ADRES_ZAYAVKI", sajt["zakaz"]))

    shapka = ('<!-- Кнопки "%s" открывают форму Битрикс24 %s прямо на странице.\n'
              "     Загрузчик формы и обработчик кнопок - ниже, трогать не нужно. -->"
              % (nadpis, sajt["forma"]))
    return shapka + "\n" + zagruzchik + "\n" + obrabotchik


def bez_tegov(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def yakor(tekst, zanyatye):
    """Якорь для заголовка, у которого его нет в исходнике."""
    lat = "".join(TRANSLIT.get(c, c) for c in tekst.lower())
    lat = re.sub(r"[^a-z0-9]+", "-", lat).strip("-")[:60].rstrip("-")
    ident, n = lat or "razdel", 2
    while ident in zanyatye:
        ident, n = f"{lat}-{n}", n + 1
    return ident


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
    """В исходниках два призыва иногда слиты в один абзац - разводим обратно."""
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
    c = cveta(sajt)
    out = []
    for chast, _ in zip(razvesti_prizyvy(tekst, len(nadpisi)), nadpisi):
        zag, pod = zagolovok_i_podpis(chast)
        blok = (f'<div style="margin:22px 0 30px;padding:18px 20px;'
                f'border-left:4px solid {c["polosa"]};background:{c["zalivka"]};">'
                f'<p style="margin:0;font-size:18px;"><strong>{zag}</strong></p>')
        if pod:
            blok += f'<p style="margin:4px 0 0;color:#69757f;font-size:14px;">{pod}</p>'
        blok += f'<p style="margin:14px 0 0;">{knopka(sajt)}</p></div>'
        out.append(blok)
    return "\n".join(out)


def soderzhanie(razdely, sajt):
    """Оглавление. Кнопка справа в шапке блока - она держит первый экран."""
    c = cveta(sajt)
    punkty = "\n".join(
        f'<li style="margin:0 0 7px;break-inside:avoid;"><a href="#{ident}">{nazvanie}</a></li>'
        for ident, nazvanie in razdely)
    return (
        f'<div style="margin:24px 0 30px;padding:18px 20px;border:1px solid {c["ramka"]};'
        f'background:{c["zalivka"] if sajt.get("akcent") else ZALIVKA};">'
        '<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;'
        'gap:14px;margin:0 0 12px;">'
        '<p style="margin:0;"><strong>Содержание страницы</strong></p>'
        f'{knopka(sajt)}</div>'
        '<ol style="margin:0;padding-left:22px;columns:280px 2;column-gap:36px;">\n'
        f'{punkty}\n</ol></div>')


def tablica(vnutri, sajt):
    c = cveta(sajt)
    th = (f'padding:11px 12px;border:1px solid {c["ramka_t"]};background:{c["zalivka_t"]};'
          'text-align:left;vertical-align:top;white-space:normal;')
    td = f'padding:11px 12px;border:1px solid {c["ramka_t"]};text-align:left;vertical-align:top;'
    t = re.sub(r"<table[^>]*>",
               '<table style="width:100%;min-width:720px;border-collapse:collapse;margin:0;">', vnutri)
    t = re.sub(r"<caption[^>]*>",
               '<caption style="caption-side:top;text-align:left;padding:0 0 10px;'
               'font-weight:600;">', t)
    t = re.sub(r"<th[^>]*>", f'<th style="{th}">', t)
    t = re.sub(r"<td[^>]*>", f'<td style="{td}">', t)
    return (f'<div class="tablica-prokrutka" style="width:100%;overflow-x:auto;'
            f'-webkit-overflow-scrolling:touch;margin:22px 0 30px;border:1px solid {c["ramka_t"]};">'
            f'{t.strip()}</div>')


def akkordeon(vopros, otvety):
    return ('<details style="border-bottom:1px solid #e1e5e8;padding:0;">\n'
            '<summary style="cursor:pointer;padding:17px 0;font-size:18px;'
            f'font-weight:600;line-height:1.4;">{vopros}</summary>\n'
            f'<div style="padding:0 0 18px;">{"".join(otvety)}</div>\n</details>')


BLOK = re.compile(
    r'<div class="tablica-prokrutka">(?P<tabl>.*?)</div>'
    r'|<h2(?P<h2attr>[^>]*)>(?P<h2>.*?)</h2>'
    r'|<h3(?P<h3attr>[^>]*)>(?P<h3>.*?)</h3>'
    r'|<p(?P<attr>[^>]*)>(?P<p>.*?)</p>', re.S)

# абзац вида «<strong>Вопрос?</strong><br>ответ» - тоже вопрос FAQ
VOPROS_V_ABZACE = re.compile(r'^\s*<strong>(?P<v>.+?)</strong>\s*<br\s*/?>\s*(?P<o>.*)$', re.S)


def perevesti(ishodnik, sajt):
    koren = re.search(r'<div class="statya-ruspro"[^>]*>(.*)</div>', ishodnik, re.S)
    assert koren, "не найден div.statya-ruspro"
    telo = koren.group(1)
    telo = re.sub(r"<(?=\d)", "&lt;", telo)          # «<50%» в тексте - это не тег

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
    h3_vse = re.findall(r'<h3[^>]*>(.*?)</h3>', telo, re.S)
    # FAQ без своего заголовка: либо три и больше вопросов подряд, либо
    # единственный h3, который сам называется «Вопросы...»
    h3_faq_zagolovok = (len(h3_vse) == 1 and re.search(r'вопрос', bez_tegov(h3_vse[0]), re.I))
    h3_kak_voprosy = (not est_faq) and len(h3_vse) >= 3
    if not est_faq and h3_faq_zagolovok:
        razdely.append(("chastye-voprosy", bez_tegov(h3_vse[0])))
    elif h3_kak_voprosy:
        razdely.append(("chastye-voprosy", "Частые вопросы"))

    shapka = sajt.get("shapka", 90)
    h2_stil = f"scroll-margin-top:{shapka}px;margin-top:42px;"
    bloki = list(BLOK.finditer(telo))
    out, faq, prizyv, i = [], False, None, 0
    while i < len(bloki):
        m = bloki[i]
        tekst = m.group("p")
        klass = re.search(r'class="([^"]*)"', m.group("attr") or "") if tekst is not None else None
        klass = klass.group(1) if klass else ""

        if m.group("tabl") is not None:
            out.append(tablica(m.group("tabl"), sajt))
        elif m.group("h2") is not None:
            if faq:
                out.append("</div>")
                faq = False
            ident = yakorya.get(m.start(), "")
            out.append(f'<h2 id="{ident}" style="{h2_stil}">{m.group("h2")}</h2>')
            if ident == "chastye-voprosy":
                out.append('<div style="margin:18px 0 30px;">')
                faq = True
        elif m.group("h3") is not None:
            zag = m.group("h3").strip()
            if h3_faq_zagolovok:                     # «Вопросы перед заявкой» - это заголовок FAQ
                out.append(f'<h2 id="chastye-voprosy" style="{h2_stil}">{zag}</h2>')
                out.append('<div style="margin:18px 0 30px;">')
                faq = True
            elif faq or h3_kak_voprosy:              # сам h3 - вопрос
                if not faq:
                    out.append(f'<h2 id="chastye-voprosy" style="{h2_stil}">Частые вопросы</h2>')
                    out.append('<div style="margin:18px 0 30px;">')
                    faq = True
                otvety, j = [], i + 1
                while j < len(bloki) and bloki[j].group("p") is not None:
                    t = bloki[j].group("p")
                    if "Дата обновления" in t or bez_tegov(t).startswith("Сведения"):
                        break
                    otvety.append(f'<p style="margin:0;">{t.strip()}</p>')
                    j += 1
                out.append(akkordeon(zag, otvety))
                i = j - 1
            else:                                    # обычный подзаголовок
                out.append(f'<h3 style="margin-top:34px;font-size:19px;">{zag}</h3>')
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
            vopros = VOPROS_V_ABZACE.match(tekst) if faq else None
            if vopros:                               # «<strong>Вопрос?</strong><br>ответ»
                out.append(akkordeon(vopros.group("v").strip(),
                                     [f'<p style="margin:0;">{vopros.group("o").strip()}</p>']))
            else:
                out.append(f"<p>{tekst.strip()}</p>")
                if not est_toc:                      # оглавления в исходнике нет
                    out.append(soderzhanie(razdely, sajt))
                    est_toc = True
        i += 1

    if faq:
        out.append("</div>")
    # text-align:left - у части сайтов контейнер раздела центрует текст,
    # и статья на 40 тысяч знаков ложится по центру
    statya = ('<div class="statya-ruspro" style="line-height:1.65;overflow-wrap:break-word;'
              'text-align:left;">\n' + "\n".join(out) + "\n</div>")
    hvost = snippet(sajt)
    return statya + ("\n\n" + hvost if hvost else "") + "\n"


def main():
    korn = os.path.dirname(os.path.abspath(__file__))
    cel_korn = os.environ.get("VERSTKA_CEL", korn)
    for put in sys.argv[1:]:
        domen = os.path.basename(os.path.dirname(os.path.abspath(put)))
        sajt = SAJTY.get(domen)
        if not sajt:
            print(f"пропуск {put}: домен {domen} не в реестре")
            continue
        gotovo = perevesti(io.open(put, encoding="utf-8").read(), sajt)
        papka = os.path.join(cel_korn, domen)
        os.makedirs(papka, exist_ok=True)
        imya = re.sub(r'^[a-z0-9-]+--', '', os.path.basename(put))
        io.open(os.path.join(papka, imya), "w", encoding="utf-8", newline="\r\n").write(gotovo)
        print(f'{domen}/{imya:44} {len(gotovo.encode("utf-8")):6} байт'
              f'{"  + форма " + sajt["forma"] if sajt["forma"] else ""}')


if __name__ == "__main__":
    main()
