# -*- coding: utf-8 -*-
r"""Проверка сайта, найденного поиском по названию компании (10.10, полный прогон Meyer). EC.find_site_via_xmlriver
берёт карточку Яндекса или первый органический результат — на волне 1 из 721 найденного: check.tochka.com у 10
компаний, tenderguru.ru у 7, licexpert.ru у 5, соцсети, реестры, новости, «ООО Эксперт» -> клиника МРТ, «ООО Олимп» ->
фитнес; из 166 обойдённых ИНН компании был на 26. Сайт принимается, если:
  * домен не агрегатор/реестр/соцсеть/новости (СТОП) и не найден для другой компании (повтор домена);
  * на главной — ИНН компании или отличительное слово названия (ядра), либо домен похож на название (транслит).
-> (принят, причина)."""
import re

import kc_sayty as KS
import meyer_nalichie as MN
import meyer_proverka as MP

СТОП = re.compile(r'tochka\.com|tenderguru|licexpert|sensus\.kz|plastinfo|agroserver|dataslon|sudact|kommersant|'
                  r'innproverka|rusprofile|checko|list-org|zachestnyibiznes|audit-it|sbis\.ru|kontur|spark-|tarif|'
                  r'декларац|perekrestok|wikipedia|youtube|hh\.ru|avito|2gis|zoon|yell\.ru|orgpage|spravker|blizko|'
                  r'kartaslov|vk\.com|ok\.ru|t\.me|instagram|facebook|ria\.ru|rbc\.ru|tass\.ru|interfax|bel\.ru|'
                  r'egrul|nalog|gosuslugi|\.gov\.ru|tender|zakupki|b2b-center|fabrikant|rts-tender|sberbank|tbank|'
                  r'tinkoff|alfabank|vtb\.ru|pulscen|tiu\.ru|satom|flagma|regtorg|moscow-faq|vsetaksi|ivanovo\.ru', re.I)
ТР = dict(zip('абвгдеёзийклмнопрстуфыэ', ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p',
                                          'r', 's', 't', 'u', 'f', 'y', 'e']))
ТР.update({'ж': 'zh', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ь': '', 'ю': 'yu', 'я': 'ya'})


def транслит(т):
    return ''.join(ТР.get(б, б) for б in (т or '').lower())


def _плоско(т):
    return re.sub(r'[^a-z0-9]', '', т.replace('kh', 'h').replace('ks', 'x').replace('ts', 'c').replace('j', 'y'))


def домен_похож(имя, сайт):
    д = _плоско(MN.домен(сайт).split('.')[0] if not MN.домен(сайт).startswith('xn--') else MN.домен(сайт))
    if MN.домен(сайт).endswith('.рф') or re.search(r'[а-яё]', MN.домен(сайт)):
        д = _плоско(транслит(MN.домен(сайт).split('.')[0]))
    for я in KS.ядра(имя):
        for сл in re.findall(r'[а-яёa-z0-9]{4,}', я):
            с = _плоско(транслит(сл))
            if len(с) >= 4 and (с[:6] in д or (len(д) >= 5 and д[:6] in с)):
                return True
    return False


def проверить(имя, инн, сайт, повтор=False):
    дом = MN.домен(сайт)
    if not дом:
        return False, 'пустой адрес'
    if СТОП.search(дом):
        return False, 'агрегатор/реестр/соцсеть: ' + дом
    if повтор:
        return False, 'домен найден и для другой компании: ' + дом
    ст, html, заг = MN.скачать(сайт if сайт.startswith('http') else 'https://' + сайт)
    похож = домен_похож(имя, сайт)
    if ст != 'ok':
        return (True, 'главная не открылась, домен похож на название') if похож else (False, 'главная не открылась, домен не похож на название')
    т = (MP.в_текст(html) + ' ' + (заг or '')).lower().replace('«', '"').replace('»', '"').replace('ё', 'е')
    if инн and инн in re.sub(r'\D', ' ', т).split():
        return True, 'ИНН компании на главной'
    for я in KS.ядра(имя):
        if я.replace('ё', 'е') in т:
            return True, 'название «%s» на главной' % я
    if похож:
        return True, 'домен похож на название'
    return False, 'на главной ни ИНН, ни названия; домен не похож'
