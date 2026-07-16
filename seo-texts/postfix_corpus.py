# -*- coding: utf-8 -*-
"""Пост-фиксы по всему корпусу gen/result-*.json (идемпотентно):
  1) «ГК Руспром» -> «ООО Руспром» (юрлицо у клиента - ООО, не ГК).
  2) флоат-картинка не должна заезжать на следующий блок: перед первым <h2 (или байлайном)
     после <img вставляем <div style="clear:both;"></div>.
  3) <ul>/<li> в теле -> короткие абзацы <p>: CSS сайта (Aspro) рисует маркеры li длинным
     тире «—», владелец читает это как ИИ-паттерн.
  4) фото-блок -> единая кликабельная карточка <a><img/><span подпись/></a> вне <p>:
     чинит некликабельную подпись (JS сайта перехватывал клик) и вложенность <p><div>.
Запуск: python3 postfix_corpus.py [--dry]"""
import json, glob, os, re, sys

DIR = os.path.dirname(os.path.abspath(__file__))
DRY = '--dry' in sys.argv


def fix_gk(html):
    html = re.sub(r'ГК\s*«\s*Руспром\s*»', 'ООО «Руспром»', html)
    html = re.sub(r'ГК\s*"\s*Руспром\s*"', 'ООО «Руспром»', html)
    html = re.sub(r'\bГК\s+Руспром\b', 'ООО «Руспром»', html)
    return html


def fix_clear(html):
    if '<img' not in html or 'clear:both' in html:
        return html
    img = html.rfind('<img')
    h2 = html.find('<h2', img)
    by = html.find('expert-byline', img)
    pos = None
    if h2 != -1:
        pos = h2
    elif by != -1:
        pos = html.rfind('<p', 0, by)
    if pos is None or pos < 0:
        return html + '\n<div style="clear:both;"></div>'
    return html[:pos] + '<div style="clear:both;"></div>\n' + html[pos:]


def fix_ul(html):
    """<ul><li>..</li></ul> -> последовательность <p>..</p> (аккордеон ul не использует)."""
    if '<ul' not in html:
        return html
    def repl(m):
        items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(0), re.S)
        return '\n'.join(f'<p>{it.strip()}</p>' for it in items)
    return re.sub(r'<ul[^>]*>.*?</ul>', repl, html, flags=re.S)


PHOTO_RE = re.compile(
    r'(?:<p>\s*)?<div style="float:right;[^"]*">\s*'
    r'<img src="([^"]+)" alt="([^"]*)"[^>]*>\s*'
    r'<div[^>]*>(.*?)<a href="([^"]+)">[^<]*</a>\s*</div>\s*</div>', re.S)


def fix_photo_card(html):
    """Фото-блок -> одна кликабельная карточка-ссылка вне <p> (весь блок ведёт на проект)."""
    def repl(m):
        src, alt, cap, url = m.group(1), m.group(2), m.group(3).strip().rstrip('-— '), m.group(4)
        had_p = m.group(0).lstrip().startswith('<p>')      # был внутри <p> - вернём <p> для остатка абзаца
        card = (f'<a href="{url}" style="float:right; width:300px; max-width:45%; '
                f'margin:4px 0 14px 22px; display:block; position:relative; z-index:5; '
                f'text-decoration:none;"><img src="{src}" alt="{alt}" '
                f'style="width:100%; height:auto; border-radius:6px;">'
                f'<span style="display:block; font-size:13px; color:#777; margin-top:6px; '
                f'line-height:1.35;">{cap} - подробнее о проекте</span></a>')
        return card + ('<p>' if had_p else '')
    out = PHOTO_RE.sub(repl, html)
    return out.replace('<p></p>', '')


def main():
    ng = nc = nu = nf = 0
    for f in glob.glob(os.path.join(DIR, 'gen', 'result-*.json')):
        d = json.load(open(f))
        h = d.get('text_html', '')
        if not isinstance(h, str) or not h:
            continue
        h2 = fix_gk(h)
        if h2 != h:
            ng += 1
        h3 = fix_ul(h2)
        if h3 != h2:
            nu += 1
        h4 = fix_photo_card(h3)
        if h4 != h3:
            nf += 1
        h5 = fix_clear(h4)
        if h5 != h4:
            nc += 1
        if h5 != h and not DRY:
            d['text_html'] = h5
            json.dump(d, open(f, 'w'), ensure_ascii=False, indent=1)
    print(f'{"[DRY] " if DRY else ""}ГК->ООО: {ng} | ul->p: {nu} | фото-карточка: {nf} | clear: {nc}')


if __name__ == '__main__':
    main()
