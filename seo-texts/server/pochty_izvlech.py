# -*- coding: utf-8 -*-
"""Почты, которые шаблон обхода (kc_pochty.почты) не видит: защита Joomla (var addy… и <joomla-hidden-mail> base64),
Cloudflare (data-cfemail), пары data-user/data-domain и base64 в data-email, ROT13, склейка в JS ('a' + '@' + 'b.ru',
String.fromCharCode), текстовая обфускация («info /собачка/ site.ru», «info @ site.ru», перевёрнутые адреса),
кириллические домены (snab@горняк03.рф) и punycode.

11.10, ревизия (№07, №09): Joomla у 6 из 9 Joomla-сайтов, «защищён от спам-ботов» в записях 230 компаний (68 без почт);
.рф-почты не извлекаются вовсе (≥46 у 37 ИНН); ROT13 — 54 у 17; data-user+data-domain (tulamilk.ru provision@/quality@).
Декодеры — из разборов ревизоров 07/09, сведены в один модуль.

`найти(html)` -> [(почта, как, позиция_в_html)]
"""
import base64
import codecs
import html as H
import re

АДРЕС = re.compile(r'^[a-z0-9][a-z0-9._%+\-]{0,63}@(?:[a-z0-9\-]+\.)+(?:[a-z]{2,24}|xn--[a-z0-9\-]+)$')
АДРЕС_КИР = re.compile(r'(?<![\w.+-])([a-z0-9][a-z0-9._%+\-]{0,63}@(?:[a-z0-9а-яё\-]+\.)*[a-z0-9а-яё\-]*[а-яё][a-z0-9а-яё\-]*'
                       r'\.(?:рф|рус|бел|москва|онлайн|сайт|ru|com|su|by))(?![\w-])', re.I)


def годный(e):
    """Проверка и нормализация; кириллический домен -> punycode для проверки, сам адрес — как на сайте."""
    e = (e or '').strip().strip('.,;:<>()"\'').lower()
    if '@' not in e:
        return ''
    лок, дом = e.rsplit('@', 1)
    try:
        дом_a = дом.encode('idna').decode('ascii')
    except UnicodeError:
        return ''
    return e if АДРЕС.match(лок + '@' + дом_a) else ''


def _joomla(h):
    out = []
    Q = r"(?:'[^']*'\s*\+\s*)*'[^']*'"
    for m in re.finditer(r'(?s)var\s+(addy[0-9a-f]+)\s*=\s*(' + Q + r')\s*;\s*\1\s*=\s*\1\s*\+\s*(' + Q + r')\s*;', h):
        out.append((H.unescape(''.join(re.findall(r"'([^']*)'", m.group(2) + '+' + m.group(3)))), m.start()))
    for m in re.finditer(r"(?s)var\s+(addy(?:_text)?[0-9a-f]+)\s*=\s*((?:'[^']*'\s*\+\s*)*'[^']*')\s*;", h):
        s = H.unescape(''.join(re.findall(r"'([^']*)'", m.group(2))))
        if '@' in s and '.' in s.split('@')[-1]:
            out.append((s, m.start()))
    for m in re.finditer(r'(?is)<joomla-hidden-mail[^>]*>', h):
        f, l = re.search(r'first="([^"]+)"', m.group(0)), re.search(r'last="([^"]+)"', m.group(0))
        try:
            out.append((base64.b64decode(f.group(1)).decode() + '@' + base64.b64decode(l.group(1)).decode(), m.start()))
        except Exception:  # noqa: BLE001
            pass
    return out


def _cloudflare(h):
    out = []
    for m in re.finditer(r'data-cfemail\s*=\s*["\']([0-9a-fA-F]{6,})["\']', h):
        x = m.group(1)
        try:
            k = int(x[:2], 16)
            out.append((''.join(chr(int(x[i:i + 2], 16) ^ k) for i in range(2, len(x), 2)), m.start()))
        except ValueError:
            pass
    return out


def _data(h):
    out = []
    for m in re.finditer(r'(?is)<[a-z0-9]+[^>]*\bdata-(?:user|name|login|mail-?name|left|account|local)\s*=\s*["\']([^"\']+)["\'][^>]*>', h):
        d = re.search(r'(?i)\bdata-(?:domain|host|server|right|zone|dom)\s*=\s*["\']([^"\']+)["\']', m.group(0))
        if d:
            out.append((m.group(1).strip() + '@' + d.group(1).strip(), m.start()))
    for m in re.finditer(r'(?i)\bdata-(?:email|mail|e-mail|address|contact)\s*=\s*["\']([A-Za-z0-9+/=]{8,})["\']', h):
        if '@' in m.group(1):
            continue
        try:
            dv = base64.b64decode(m.group(1) + '=' * (-len(m.group(1)) % 4)).decode('utf-8', 'ignore')
            if '@' in dv:
                out.append((dv, m.start()))
        except Exception:  # noqa: BLE001
            pass
    return out


def _rot13(h):
    return [(codecs.encode(m.group(1), 'rot13'), m.start()) for m in re.finditer(
        r'(?i)(?<![\w.@-])([a-z0-9._-]+@[a-z0-9.-]+\.(?:eh|pbz|arg|bet|ol|fh|xm|vasb|ovm|cbe|zr))(?![\w-])', h)]


def _js(h):
    out = []
    for m in re.finditer(r"""(?s)(['"])([a-z0-9._-]{1,40})\1\s*\+\s*(['"])@\3\s*\+\s*(['"])([a-z0-9.-]+\.[a-z]{2,10})\4""", h):
        out.append((m.group(2) + '@' + m.group(5), m.start()))
    for m in re.finditer(r'String\.fromCharCode\(([\d,\s]+)\)', h):
        try:
            s = ''.join(chr(int(x)) for x in m.group(1).split(',') if x.strip())
            if '@' in s:
                out.append((s, m.start()))
        except ValueError:
            pass
    return out


def видимый(h):
    h = re.sub(r'(?is)<!--.*?-->', ' ', h)
    h = re.sub(r'(?is)<(script|style|noscript|template)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'[ \t\xa0]+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', h)))


_ПЕРЕД_АДРЕСОМ = re.compile(r'(?:^|[:;,(<\[|\n]|e-?mail|почта|почты|адрес|mail)\s*$', re.I)


def _текст(вид):
    out = []
    for m in re.finditer(r'(?i)\b([a-z0-9][a-z0-9._-]{0,40})\s*(?:[/\[\(\{<]\s*[^/\]\)\}>@]{0,30}(?:собак|собачк|at\b|эт\b)'
                         r'[^/\]\)\}>@]{0,30}\s*[/\]\)\}>]|\s(?:собака|собачка|at)\s|\s@\s|\s@|@\s)\s*([a-z0-9-]+(?:\s*(?:\.|'
                         r'\[\s*dot\s*\]|\(\s*dot\s*\)|\(\s*точка\s*\)|\s+dot\s+|\s+точка\s+)\s*[a-z0-9-]+)*\s*(?:\.|\[\s*dot\s*\]|'
                         r'\(\s*dot\s*\)|\(\s*точка\s*\)|\s+dot\s+|\s+точка\s+)\s*(?:ru|com|net|org|by|su|kz|рф|info|pro|biz))\b', вид):
        # 11.10, проба: «i nf om @ plvk .ru» -> om@…, «Vitruk _ Oleg @ outlook . com» -> oleg@…, «.livejournal.com @mail.ru»
        # (виджет входа). Пробел у «@» — только после «e-mail:», «почта», двоеточия, запятой, начала строки; [at]/(собака) — всегда
        if '@' in m.group(0) and not _ПЕРЕД_АДРЕСОМ.search(вид[max(0, m.start() - 14):m.start()]):
            continue
        дом = re.sub(r'\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\(\s*точка\s*\)|\s+dot\s+|\s+точка\s+)\s*', '.', m.group(2))
        out.append((m.group(1) + '@' + re.sub(r'\s+', '', дом), -1))
    for m in re.finditer(r'(?i)\b(ur|moc|ten|gro|yb)\.[a-z0-9-]+@[a-z0-9._-]+\b', вид):
        out.append((m.group(0)[::-1], -1))
    for m in АДРЕС_КИР.finditer(вид):
        out.append((m.group(1), -1))
    return out


def найти(html):
    """-> [(почта, как, позиция в html или -1)] — без повторов."""
    if not html:
        return []
    out, видел = [], set()
    вид = видимый(html)
    for как, пары in (('joomla', _joomla(html)), ('cloudflare', _cloudflare(html)), ('data-атрибуты', _data(html)),
                      ('rot13', _rot13(html)), ('js-склейка', _js(html)), ('текст/кириллица', _текст(вид))):
        for e, поз in пары:
            e = годный(e)
            if e and e not in видел:
                видел.add(e)
                out.append((e, как, поз))
    return out
