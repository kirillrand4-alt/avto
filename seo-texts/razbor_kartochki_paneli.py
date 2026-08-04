# -*- coding: utf-8 -*-
"""Разобрать HTML карточки панели обзвона в поля — чтобы сравнивать её с нашими данными.

Нужен для задания владельца «зайти в админку, посмотреть 15 карточек и найти: чего нет в
панели, что написано с ошибкой, где первоисточник говорит другое, и мусор». Глазами это
делается, но не считается; здесь карточка превращается в набор полей, и расхождение с нашим
CSV становится числом, а не впечатлением.

Разбор нарочно грубый (регулярки по разметке, без внешних библиотек): панель — наша, разметка
стабильная, а зависимость ради пяти полей дороже пользы.
"""
import re

PROBEL = re.compile(r'\s+')


def _t(s):
    return PROBEL.sub(' ', re.sub(r'<[^>]+>', ' ', s or '')).strip()


def _mezhdu(h, nach, kon):
    i = h.find(nach)
    if i < 0:
        return ''
    j = h.find(kon, i + len(nach))
    return h[i + len(nach):j if j > 0 else len(h)]


def razobrat(html):
    h = PROBEL.sub(' ', html or '')
    k = {}
    m = re.search(r'<h1>(.*?)</h1>', h)
    k['nazvanie'] = _t(m.group(1)) if m else ''
    m = re.search(r'<h1>.*?</h1>\s*<p>(.*?)</p>', h)
    k['adres'] = _t(m.group(1)) if m else ''
    for pole in ('ИНН', 'Регион', 'Приоритет', 'Фактов', 'Состояние'):
        m = re.search(r'<b>' + pole + r'</b>\s*([^<]*)', h)
        k[pole.lower()] = _t(m.group(1)) if m else ''
    m = re.search(r'tag-verdikt[^>]*>(.*?)</span>', h)
    k['sud'] = _t(m.group(1)) if m else ''
    # реквизиты: <dt>Ключ</dt><dd>значение</dd>
    k['rekvizity'] = {}
    for dt, dd in re.findall(r'<dt>(.*?)</dt>\s*<dd>(.*?)</dd>', h):
        kl, zn = _t(dt), _t(dd)
        if kl and kl not in k['rekvizity']:
            k['rekvizity'][kl] = zn
    # контакты
    k['kontakty'] = []
    for kus in re.findall(r'<article class="contact-card".*?</article>', h):
        m = re.search(r'class="contact-value"[^>]*>(.*?)</a>', kus)
        if not m:
            continue
        ist = re.search(r'<span>Источник:</span>\s*(?:<a[^>]*>)?(.*?)(?:</a>|</span>)', kus)
        k['kontakty'].append({
            'znachenie': _t(m.group(1)),
            'chelovek': _t((re.search(r'class="contact-name"[^>]*>(.*?)<', kus) or [None, ''])[1])
                        if re.search(r'class="contact-name"', kus) else '',
            'badges': _t((re.search(r'<span class="badges">(.*?)</span>', kus) or [None, ''])[1]),
            'istochnik': _t(ist.group(1)) if ist else '',
        })
    # «Люди предприятия» — ОТДЕЛЬНЫЙ блок карточки, не часть «Контактов». Сначала я его
    # проглядел и записал «людей у карточки нет», хотя их восемь: имя лежит в <b>, должность
    # в соседнем <span>, а искал я класс contact-person, которого в разметке нет.
    k['lyudi'] = []
    for kus in re.findall(r'<article class="person-card[^"]*".*?</article>', h):
        m = re.search(r'<b>(.*?)</b>\s*<span>(.*?)</span>', kus)
        ist = re.search(r'<span>Источник:</span>\s*(?:<a[^>]*>)?(.*?)(?:</a>|</span>)', kus)
        ssyl = re.search(r'<a href="([^"]+)"', kus)
        k['lyudi'].append({'chelovek': _t(m.group(1)) if m else _t(kus)[:60],
                           'dolzhnost': _t(m.group(2)) if m else '',
                           'tehnicheskiy': 'is-tech' in kus,
                           'istochnik': _t(ist.group(1)) if ist else '',
                           'ssylka': ssyl.group(1) if ssyl else ''})
    # факты
    k['fakty'] = []
    for kus in re.findall(r'<article class="fact-card".*?</article>', h):
        f = {}
        for dt, dd in re.findall(r'<dt>(.*?)</dt>\s*<dd>(.*?)</dd>', kus):
            f[_t(dt)] = _t(dd)
        m = re.search(r'<blockquote>(.*?)</blockquote>', kus)
        if m:
            f['Цитата'] = _t(m.group(1))
        m = re.search(r'class="source-button" href="([^"]+)"', kus)
        f['ссылка'] = m.group(1) if m else ''
        m = re.search(r'name="value" value="(\d+)"', kus)
        f['id'] = m.group(1) if m else ''
        m = re.search(r'class="tag tag-status">(.*?)</span>', kus)
        f['статус'] = _t(m.group(1)) if m else ''
        ist = re.search(r'<span>Источник:</span>\s*<a[^>]*>(.*?)</a>', kus)
        f['источник'] = _t(ist.group(1)) if ist else ''
        k['fakty'].append(f)
    # источники проверки компании
    k['istochniki_kompanii'] = [_t(x) for x in
                                re.findall(r'<li><b>(.*?)</li>',
                                           _mezhdu(h, 'Источники проверки компании', '</details>'))]
    m = re.search(r'Почему звонить сейчас</h2>\s*<p>(.*?)</p>', h)
    k['pochemu_zvonit'] = _t(m.group(1)) if m else ''
    k['ubrano'] = _t((re.search(r'<b>Убрано вами: (\d+)</b>', h) or [None, ''])[1])
    k['musor_fraza'] = 'Мусорных позиций у этой компании нет' in h
    return k
