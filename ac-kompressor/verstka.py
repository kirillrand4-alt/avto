#!/usr/bin/env python3
# coding: utf-8
"""Перевод статей ac-kompressor.ru из классовой вёрстки в инлайновую.

Исходники (архив «дорогие плановые») размечены классами cta, cta-knopka,
na-stranice - их рисует stili-dlya-sayta.css, которого на сайте нет.
Живая страница /catalog/kompressornye-stantsii/ свёрстана инлайновыми
стилями и ничего от сайта не требует. Скрипт приводит статьи к ней:

  p.na-stranice          -> блок «Содержание страницы»: рамка, нумерованный
                            список в две колонки, кнопка «Получить КП» справа
                            (она и держит кнопку на первом экране)
  p.cta + p.cta-knopka   -> плашка призыва: полоса слева, заголовок, подпись,
                            кнопка. Блок с двумя кнопками разводится на два
  h2                     -> с якорем и отступом под липкую шапку сайта
  div.tablica-prokrutka  -> прокрутка и рамки таблицы инлайном
  h3 после «Частые вопросы» -> details/summary (аккордеон)
  хвост                  -> оговорка и дата обновления серым

В конец статьи дописывается kp-trigger.html: по кнопке открывается попап
Битрикс24, привязанный к кнопке в подвале сайта.

Константы ниже - для ac-kompressor.ru. Для другого сайта поменять цвет,
адрес заявки и сниппет: у каждого сайта своя форма Битрикс24.
"""

import io
import os
import re
import sys

CVET = "#0096d6"                                        # акцент темы ac-kompressor
ZAKAZ = "https://ac-kompressor.ru/company/zakaz/"       # куда ведёт кнопка без JS
NADPIS_KNOPKI = "Получить КП"                           # как на живой странице

KNOPKA_STIL = (
    "display:inline-block !important;box-sizing:border-box;min-width:168px;"
    "padding:15px 28px;background:#fff !important;border:1px solid #e5e5e5;"
    f"color:{CVET} !important;font-size:15px;line-height:20px;font-weight:700;"
    "text-align:center;text-decoration:none !important;cursor:pointer;"
    "vertical-align:middle;"
)
H2_STIL = "scroll-margin-top:110px;margin-top:42px;"
TABL_STIL = ("width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;"
             "margin:22px 0 30px;border:1px solid #dfe5ea;")
TH_STIL = ("padding:11px 12px;border:1px solid #dfe5ea;background:#eef3f6;"
           "text-align:left;vertical-align:top;white-space:normal;")
TD_STIL = "padding:11px 12px;border:1px solid #dfe5ea;text-align:left;vertical-align:top;"
SERYY = "margin-top:28px;color:#6b747c;font-size:14px;"

GLAGOLY = r"(?:Получить|Рассчитать|Подобрать|Прислать|Отправить|Уточнить|Оставить|Заказать|Запросить)"


def knopka(nadpis=NADPIS_KNOPKI, otstup=False):
    stil = KNOPKA_STIL + ("margin:0 12px 10px 0;" if otstup else "")
    return f'<a href="{ZAKAZ}" class="ac-kp-trigger" style="{stil}">{nadpis}</a>'


def bez_tegov(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def zagolovok_i_podpis(tekst):
    """Длинный призыв разводится на заголовок плашки и серую подпись под ним."""
    t = re.sub(r"</?strong>", "", tekst).strip()
    dvoetochie = t.find(":")
    if 0 < dvoetochie < 90:
        zag, pod = t[:dvoetochie], t[dvoetochie + 1:]
    else:
        tochka = re.search(r"\.\s+", t)
        if tochka and tochka.start() < 90:
            zag, pod = t[:tochka.start()], t[tochka.end():]
        elif " - " in t:          # «что прислать - что сделаем»: до тире заголовок
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


def plashka(tekst, nadpisi):
    """Плашка призыва: заголовок, подпись, кнопка. Одна на каждую кнопку."""
    out = []
    for chast, nadpis in zip(razvesti_prizyvy(tekst, len(nadpisi)), nadpisi):
        zag, pod = zagolovok_i_podpis(chast)
        blok = (f'<div style="margin:22px 0 30px;padding:18px 20px;'
                f'border-left:4px solid {CVET};background:#f6f8fa;">'
                f'<p style="margin:0;font-size:18px;"><strong>{zag}</strong></p>')
        if pod:
            blok += f'<p style="margin:4px 0 0;color:#69757f;font-size:14px;">{pod}</p>'
        blok += f'<p style="margin:14px 0 0;">{knopka()}</p></div>'
        out.append(blok)
    if len(out) < len(nadpisi):          # призыв не развёлся - кнопки в один блок
        knopki = " ".join(knopka(otstup=True) for _ in nadpisi)
        out[-1] = out[-1].replace(f'<p style="margin:14px 0 0;">{knopka()}</p>',
                                  f'<p style="margin:14px 0 0;">{knopki}</p>')
    return "\n".join(out)


def soderzhanie(razdely):
    """Оглавление статьи. Кнопка справа в шапке блока - она держит первый экран."""
    punkty = "\n".join(
        f'<li style="margin:0 0 7px;break-inside:avoid;"><a href="#{ident}">{nazvanie}</a></li>'
        for ident, nazvanie in razdely)
    return (
        '<div style="margin:24px 0 30px;padding:18px 20px;border:1px solid #d9e0e5;background:#f6f8fa;">'
        '<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;'
        'gap:14px;margin:0 0 12px;">'
        '<p style="margin:0;"><strong>Содержание страницы</strong></p>'
        f'{knopka()}</div>'
        '<ol style="margin:0;padding-left:22px;columns:280px 2;column-gap:36px;">\n'
        f'{punkty}\n</ol></div>')


def tablica(vnutri):
    t = re.sub(r"<table[^>]*>",
               '<table style="width:100%;min-width:720px;border-collapse:collapse;margin:0;">',
               vnutri)
    t = re.sub(r"<th[^>]*>", f'<th style="{TH_STIL}">', t)
    t = re.sub(r"<td[^>]*>", f'<td style="{TD_STIL}">', t)
    return f'<div class="tablica-prokrutka" style="{TABL_STIL}">{t.strip()}</div>'


def hvost(tekst):
    return f'<p style="{SERYY}">{tekst}</p>'


BLOK = re.compile(
    r'<div class="tablica-prokrutka">(?P<tabl>.*?)</div>'
    r'|<h2 id="(?P<h2id>[^"]*)"[^>]*>(?P<h2>.*?)</h2>'
    r'|<h3[^>]*>(?P<h3>.*?)</h3>'
    r'|<p(?P<attr>[^>]*)>(?P<p>.*?)</p>', re.S)


def perevesti(ishodnik, snippet):
    koren = re.search(r'<div class="statya-ruspro"[^>]*>(.*)</div>', ishodnik, re.S)
    assert koren, "не найден div.statya-ruspro"
    telo = koren.group(1)

    razdely = [(m.group(1), bez_tegov(m.group(2)))
               for m in re.finditer(r'<h2 id="([^"]+)"[^>]*>(.*?)</h2>', telo, re.S)]

    bloki = list(BLOK.finditer(telo))
    out, faq, prizyv, i = [], False, None, 0
    while i < len(bloki):
        m = bloki[i]
        klass = re.search(r'class="([^"]*)"', m.group("attr") or "") if m.group("p") is not None else None
        klass = klass.group(1) if klass else ""
        tekst = m.group("p")

        if m.group("tabl") is not None:
            out.append(tablica(m.group("tabl")))
        elif m.group("h2id") is not None:
            if faq:                                  # предыдущий аккордеон закрыт выше
                faq = False
            out.append(f'<h2 id="{m.group("h2id")}" style="{H2_STIL}">{m.group("h2")}</h2>')
            if m.group("h2id") == "chastye-voprosy":
                out.append('<div style="margin:18px 0 30px;">')
                faq = True
        elif m.group("h3") is not None:
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
            out.append(soderzhanie(razdely))
        elif klass == "cta":
            prizyv = tekst
        elif klass == "cta-knopka":
            nadpisi = re.findall(r">([^<]+)</a>", tekst)
            out.append(plashka(prizyv if prizyv is not None else "", nadpisi))
            prizyv = None
        elif "Дата обновления" in tekst or bez_tegov(tekst).startswith("Сведения"):
            if faq:
                out.append("</div>")
                faq = False
            data = bez_tegov(tekst)
            if data.startswith("Дата обновления") and not data.endswith("."):
                data += "."
            out.append(hvost(data))
        else:
            out.append(f"<p>{tekst.strip()}</p>")
        i += 1

    if faq:
        out.append("</div>")
    statya = ('<div class="statya-ruspro" style="line-height:1.65;overflow-wrap:break-word;">\n'
              + "\n".join(out) + "\n</div>")
    return statya + "\n\n" + snippet + "\n"


def main():
    snippet = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "kp-trigger.html"),
                      encoding="utf-8").read().strip()
    for put in sys.argv[1:]:
        ishodnik = io.open(put, encoding="utf-8").read()
        gotovo = perevesti(ishodnik, snippet)
        imya = os.path.basename(put).replace("ac-kompressor--", "")
        cel = os.path.join(os.path.dirname(os.path.abspath(__file__)), "statyi", imya)
        io.open(cel, "w", encoding="utf-8", newline="\r\n").write(gotovo)
        print(f"{imya:42} {len(gotovo.encode('utf-8')):6} байт")


if __name__ == "__main__":
    main()
