# -*- coding: utf-8 -*-
r"""Публичная страница лида по ссылке: переписка и контакты без НАШИХ адресов.

Страница отдаётся БЕЗ входа в панель — по ссылке с случайным токеном. Поэтому
здесь два правила, которые нельзя нарушать:

  1. наружу не уходит ничего, чего нет в самом лиде: ни списка других лидов,
     ни настроек, ни идентификаторов ящиков;
  2. всё, что печатается, экранируется. Тексты писем пришли от посторонних
     людей, и HTML в них — не наш HTML.
"""
import html
import re

_ЧЕЛОВЕЧЕСКИ = {
    'sent': 'мы написали', 'reply_sent': 'мы ответили',
    'reply': 'ответ компании', 'reply_auto': 'автоответ компании',
    'bounce': 'письмо не дошло', 'dsn': 'отчёт о доставке',
    'complaint': 'жалоба',
}
_СТИЛЬ = """
body{font:15px/1.55 system-ui,Segoe UI,Roboto,Arial;margin:0;background:#f6f7f9;color:#1c2126}
.w{max-width:52em;margin:0 auto;padding:24px 16px 60px}
h1{font-size:22px;margin:0 0 2px}
.inn{color:#6a737d;font-size:13px;margin-bottom:18px}
.k{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:14px 16px;margin:0 0 14px}
.k h2{font-size:14px;text-transform:uppercase;letter-spacing:.04em;color:#6a737d;margin:0 0 10px}
.m{border-left:3px solid #d7dbe0;padding:2px 0 2px 12px;margin:0 0 14px}
.m.in{border-color:#0a7d33;background:#f4fbf6}
.m.out{border-color:#2855c8}
.m .kt{font-size:12px;color:#6a737d;margin-bottom:3px}
.m .tm{white-space:pre-wrap;word-break:break-word;margin:0}
.sub{font-weight:600;margin:2px 0 4px}
table{border-collapse:collapse;width:100%}
td{padding:3px 8px 3px 0;vertical-align:top;font-size:14px}
td.n{color:#6a737d;white-space:nowrap;width:11em}
a{color:#2855c8}
.no{color:#6a737d;font-style:italic}
.src{display:block;color:#8a9099;font-size:12px;margin-top:1px}
.foot{color:#8a9099;font-size:12px;margin-top:26px;text-align:center}
"""


def _э(t) -> str:
    return html.escape(str(t if t is not None else ''), quote=True)


def _когда(ts) -> str:
    t = str(ts or '')
    if len(t) >= 16 and t[4] == '-':
        return '%s.%s.%s %s' % (t[8:10], t[5:7], t[0:4], t[11:16])
    return _э(t)


def _ссылка(u) -> str:
    u = str(u or '').strip()
    if not u.startswith(('http://', 'https://')):
        return ''
    коротко = re.sub(r'^https?://(www\.)?', '', u)[:44]
    return ' <a href="%s" target="_blank" rel="noopener nofollow">%s</a>' % (
        _э(u), _э(коротко))


def _источник(что, url) -> str:
    """Подпись «откуда знаем» — мелким шрифтом рядом со значением."""
    если = _э(что or '')
    if not если:
        return ''
    сс = _ссылка(url)
    return '<span class="src">%s%s</span>' % (если, сс)


def _карточка(lead: dict, карта: dict) -> list:
    """Кому звонить + о компании + паспорт сайта. У каждого факта — источник.

    Владелец 21.08 обвёл на странице телефон и спросил «откуда?»: номер стоял
    дважды (из ответа клиента и с сайта) и без единого слова о происхождении.
    Здесь одинаковые номера склеены, а источники перечислены все.
    """
    куски = ['<div class="k"><h2>Кому звонить</h2><table>']
    for п in (карта.get('pochty') or [])[:8]:
        подпись = ' · '.join(x for x in (п.get('rol'), ('проба: %s' % п['proba'])
                                         if п.get('proba') else '') if x)
        куски.append('<tr><td class="n">Почта</td><td>%s %s%s</td></tr>'
                     % (_э(п.get('adres')), _э(подпись),
                        _источник(п.get('istochnik'), п.get('url'))))
    for т in (карта.get('telefony') or [])[:12]:
        источники = ' · '.join(и['chto'] for и in (т.get('istochniki') or []))
        url = next((и['url'] for и in (т.get('istochniki') or []) if и.get('url')), '')
        кто = т.get('kto') or ''
        куски.append('<tr><td class="n">Телефон</td><td>%s%s%s</td></tr>'
                     % (_э(т.get('nomer')), (' — ' + _э(кто)) if кто else '',
                        _источник(источники, url)))
    for ч in (карта.get('lyudi') or [])[:12]:
        строка = ' — '.join(x for x in (ч.get('person'), ч.get('post')
                                        or ч.get('role')) if x)
        if not строка:
            continue
        куски.append('<tr><td class="n">Контакт</td><td>%s%s</td></tr>'
                     % (_э(строка), _источник(ч.get('source'), ч.get('source_url'))))
    if not (карта.get('telefony') or карта.get('lyudi') or карта.get('pochty')):
        куски.append('<tr><td colspan="2" class="no">Телефонов и людей в базе '
                     'нет — звонить придётся через сайт компании.</td></tr>')
    куски.append('</table></div>')

    рекв = карта.get('rekvizity') or []
    if рекв:
        куски.append('<div class="k"><h2>О компании</h2><table>')
        for н, з in рекв:
            зн = _ссылка('http://' + str(з).lstrip('htp:/')) if н == 'Сайт' else _э(з)
            куски.append('<tr><td class="n">%s</td><td>%s</td></tr>' % (_э(н), зн))
        куски.append('</table></div>')

    п = карта.get('pasport') or {}
    поля = п.get('polya') or []
    if поля or п.get('citata') or п.get('novosti'):
        куски.append('<div class="k"><h2>Что нашли на сайте</h2><table>')
        if п.get('god'):
            куски.append('<tr><td class="n">Год основания</td><td>%s</td></tr>'
                         % _э(п['god']))
        for имя, значения in поля:
            куски.append('<tr><td class="n">%s</td><td>%s</td></tr>'
                         % (_э(имя), _э('; '.join(значения[:12]))))
        if п.get('citata'):
            куски.append('<tr><td class="n">Цитата с сайта</td><td>«%s»</td></tr>'
                         % _э(п['citata']))
        for н in (п.get('novosti') or [])[:5]:
            заголовок = ' — '.join(x for x in (н.get('дата'), н.get('заголовок'))
                                   if x)
            куски.append('<tr><td class="n">Новость</td><td>%s%s</td></tr>'
                         % (_э(заголовок), _ссылка(н.get('url'))))
        куски.append('<tr><td class="n">Откуда</td><td>%s</td></tr>'
                     % ('обход сайта%s%s' % (
                         _ссылка(п.get('sayt')),
                         (', ' + _э(п['kogda'])) if п.get('kogda') else '')))
        куски.append('</table></div>')
    return куски


def _карточка_по_старому(lead: dict, kontakty: dict) -> list:
    """Запасной вид, если полная карта не собралась: лучше меньше, чем ничего."""
    люди = kontakty.get('lyudi') or []
    телефоны = kontakty.get('telefony') or []
    куски = ['<div class="k"><h2>Кому звонить</h2><table>']
    if lead.get('email'):
        куски.append('<tr><td class="n">Ответили с адреса</td><td>%s</td></tr>'
                     % _э(lead['email']))
    if lead.get('phone'):
        куски.append('<tr><td class="n">Телефон из ответа</td><td>%s</td></tr>'
                     % _э(lead['phone']))
    for ч in люди[:12]:
        строка = ' — '.join(x for x in (ч.get('person'), ч.get('post')) if x)
        куски.append('<tr><td class="n">Контакт</td><td>%s%s</td></tr>'
                     % (_э(строка), _ссылка(ч.get('istochnik') or ч.get('source_url'))))
    for т in телефоны[:12]:
        н = т.get('phone') if isinstance(т, dict) else т
        куски.append('<tr><td class="n">Телефон</td><td>%s</td></tr>' % _э(н))
    if not (lead.get('phone') or люди or телефоны):
        куски.append('<tr><td colspan="2" class="no">Телефонов и людей в базе '
                     'нет — звонить придётся через сайт компании.</td></tr>')
    куски.append('</table></div>')
    о = kontakty.get('kompaniya') or {}
    строки = [('Регион', о.get('region')), ('Адрес', о.get('address')),
              ('Сайт', о.get('site')), ('ОКВЭД', о.get('okved'))]
    если_есть = [(н, з) for н, з in строки if з]
    if если_есть:
        куски.append('<div class="k"><h2>О компании</h2><table>')
        for н, з in если_есть:
            зн = _ссылка('http://' + str(з).lstrip('htp:/')) if н == 'Сайт' else _э(з)
            куски.append('<tr><td class="n">%s</td><td>%s</td></tr>' % (_э(н), зн))
        куски.append('</table></div>')
    return куски


def sobrat(lead: dict, thread: list, kontakty: dict, chistilka) -> str:
    """HTML страницы. chistilka — (без_подписи, без_адресов[, без_цитаты,
    без_нашей_подписи])."""
    без_подписи, без_адресов = chistilka[0], chistilka[1]
    без_цитаты = chistilka[2] if len(chistilka) > 2 else (lambda т: т)
    без_нашей_подписи = chistilka[3] if len(chistilka) > 3 else (lambda т: т)
    имя = lead.get('company_name') or 'Компания без названия'
    куски = ['<!doctype html><html lang="ru"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta name="robots" content="noindex,nofollow">',
             '<title>%s — переписка</title>' % _э(имя),
             '<style>%s</style></head><body><div class="w">' % _СТИЛЬ,
             '<h1>%s</h1>' % _э(имя)]
    if lead.get('inn'):
        куски.append('<div class="inn">ИНН %s</div>' % _э(lead['inn']))

    # 1. Переписка — первым делом: ради неё ссылку и открывают.
    куски.append('<div class="k"><h2>Переписка</h2>')
    if not thread:
        куски.append('<p class="no">Переписки пока нет.</p>')
    for it in thread:
        куда = 'in' if it.get('direction') == 'in' else 'out'
        вид = _ЧЕЛОВЕЧЕСКИ.get(str(it.get('kind') or ''), str(it.get('kind') or ''))
        тело = it.get('body') or ''
        # ЦИТАТА уходит первой, у писем в обе стороны. Она дублирует соседний
        # блок, а в ответе клиента внутри цитаты лежит НАША подпись с именем
        # менеджера — проба 21.08 по лиду «Канат» поймала её на странице.
        тело = без_цитаты(тело)
        # …а если почтовик клиента процитировал нас БЕЗ знаков «>» (веб-почта
        # цитирует вёрсткой), наша подпись остаётся в тексте — её ловим по
        # собственным приметам: «Руспром», «Компрессор Центр», наш ИНН.
        тело = без_нашей_подписи(тело)
        # подпись срезаем только у НАШИХ писем: в ответе клиента его
        # собственное «С уважением» — часть письма, и резать его нельзя:
        # там имя и телефон, ради которых ссылку и открывают
        if куда == 'out':
            тело = без_подписи(тело)
        тело = без_адресов(тело)
        тема = без_адресов(it.get('subject') or '')
        куски.append('<div class="m %s"><div class="kt">%s · %s</div>'
                     % (куда, _э(вид), _когда(it.get('ts'))))
        if тема:
            куски.append('<div class="sub">%s</div>' % _э(тема))
        if it.get('body_missing'):
            куски.append('<p class="no">Текст письма не сохранён.</p>')
        else:
            куски.append('<p class="tm">%s</p>' % _э(тело))
        куски.append('</div>')
    куски.append('</div>')

    карта = kontakty.get('karta') or {}
    if карта:
        куски.extend(_карточка(lead, карта))
    else:
        куски.extend(_карточка_по_старому(lead, kontakty))

    куски.append('<div class="foot">Внутренний документ ООО «Руспром». '
                 'Наши адреса отправки скрыты намеренно — переписку ведёт '
                 'панель.</div></div></body></html>')
    return ''.join(куски)
