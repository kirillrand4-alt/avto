# -*- coding: utf-8 -*-
"""Почты со страниц сайта (план Meyer п. 3.2, владелец 08.10: «собираем не только номера, но и почты»).

  * `mailto:` из HTML и адреса из видимого текста;
  * снятие защиты от ботов: [at] / (at) / (собака) / « at » + « dot » / (точка);
  * адреса из скриптов и стилей не берутся (текст уже без них), заглушки вёрстки и картинки — мимо.
`почты(html, текст)` -> [{'почта', 'поз' (позиция в тексте или -1), 'контекст'}].
`вид(почта, домен_сайта)` -> своя | публичная | чужой домен | ловушка (для «Снято»).
"""
import html as H
import re

ПОЧТА = re.compile(r'(?<![\w.+-])([a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,24})(?![\w-])', re.I)
ЗАЩИТА = [
    (re.compile(r'\s*[\[\(\{]\s*(?:at|собака|эт)\s*[\]\)\}]\s*', re.I), '@'),
    (re.compile(r'\s*[\[\(\{]\s*(?:dot|точка)\s*[\]\)\}]\s*', re.I), '.'),
    (re.compile(r'(?<=[a-z0-9])\s+(?:at|собака)\s+(?=[a-z0-9-]+\s*(?:\.|dot|точка))', re.I), '@'),
    (re.compile(r'(?<=[a-z0-9])\s+(?:dot|точка)\s+(?=[a-z]{2,6}\b)', re.I), '.'),
]
ЛОВУШКИ = re.compile(r'^(noreply|no-reply|donotreply|example|name|user|test|email|mail|yourname|ваш)@|@(example|domain|'
                     r'site|mysite|email)\.|\.(png|jpe?g|gif|webp|svg|css|js)$|@sentry|@2x\.|wixpress|@u00', re.I)
ПУБЛИЧНЫЕ = {'yandex.ru', 'ya.ru', 'yandex.by', 'yandex.com', 'mail.ru', 'bk.ru', 'list.ru', 'inbox.ru', 'internet.ru',
             'gmail.com', 'rambler.ru', 'lenta.ru', 'autorambler.ru', 'ro.ru', 'hotmail.com', 'outlook.com',
             'icloud.com', 'yahoo.com', 'tut.by', 'mail.by', 'list.by'}
СТУДИИ = re.compile(r'^(support|admin|webmaster|hosting|dev|design|seo|studio)@', re.I)


def _раскрыть(т):
    for rx, на in ЗАЩИТА:
        т = rx.sub(на, т)
    return т


def почты(html, текст):
    out, видел = [], set()
    раскр = _раскрыть(текст)
    for м in ПОЧТА.finditer(раскр):
        п = м.group(1).lower().rstrip('.')
        if п in видел or ЛОВУШКИ.search(п):
            continue
        видел.add(п)
        # позиция в исходном тексте (для подписи перед адресом); при раскрытии защиты — приблизительно
        поз = текст.lower().find(п.split('@')[0])
        поз = поз if поз >= 0 else м.start()
        out.append({'почта': п, 'поз': поз, 'контекст': re.sub(r'\s+', ' ', текст[max(0, поз - 200):поз + 80])})
    for м in re.finditer(r'(?i)href\s*=\s*["\']mailto:([^"\'?]+)', html or ''):
        п = H.unescape(м.group(1)).strip().lower()
        if not ПОЧТА.fullmatch(п) or п in видел or ЛОВУШКИ.search(п):
            continue
        видел.add(п)
        кусок = re.sub(r'<[^>]+>', ' ', html[max(0, м.start() - 1200):м.end() + 300])
        out.append({'почта': п, 'поз': -1, 'контекст': re.sub(r'\s+', ' ', H.unescape(кусок))[-300:]})
    return out


def домен(u):
    u = re.sub(r'^https?://', '', (u or '').lower()).split('/')[0]
    return u[4:] if u.startswith('www.') else u


def вид(почта, домен_сайта):
    д = почта.split('@')[-1].lower()
    дс = домен(домен_сайта)
    if ЛОВУШКИ.search(почта):
        return 'ловушка'
    if дс and (д == дс or д.endswith('.' + дс) or дс.endswith('.' + д) or д.split('.')[0] == дс.split('.')[0]):
        return 'своя'
    if д in ПУБЛИЧНЫЕ:
        return 'публичная'
    if СТУДИИ.search(почта):
        return 'ловушка'
    return 'чужой домен'
