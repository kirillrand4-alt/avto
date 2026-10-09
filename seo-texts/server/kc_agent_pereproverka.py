# -*- coding: utf-8 -*-
r"""Повторная проверка итогов агентов-исследователей (08.10). В kc_agent_glubokiy.проверить сайт завода
подтверждался ядром названия в кавычках — на вложенных кавычках («СЫРОДЕЛЬНЫЙ КОМБИНАТ "ИЧАЛКОВСКИЙ"»)
ядро ломалось, верный сайт не подтверждался и его номера уходили в «снято». Холдинг подтверждался
только дословной цитатой агента.

Здесь — по страницам, которые агент реально открывал (из журнала), заново скачанным:
  * сайт завода подтверждён: ИНН компании или отличительное слово названия (kc_audit2.слова) на страницах
    его домена (открытые агентом + главная + контакты);
  * холдинг подтверждён: цитата агента есть на странице ИЛИ на странице домена холдинга есть
    отличительное слово названия компании (холдинг пишет о своём заводе);
  * номер — снова только если он есть на заново скачанной странице подтверждённого домена или на карточке
    закупки с ИНН.
Выход: <набор>-glubokiy2.jsonl (+ дроп). Сборщик берёт его вместо glubokiy.
"""
import io
import json
import os
import re
import shutil
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
НАБОР = os.environ.get('KC_NABOR', 'poisk')
import meyer_nalichie as MN  # noqa: E402
import meyer_proverka as MP  # noqa: E402
import kc_pochty as KP  # noqa: E402  (почты агента)
import kc_audit2 as A2  # noqa: E402  (слова — отличительные слова названия)
import kc_sayty as KS  # noqa: E402  (ядра)

ВХ = os.path.join(DIR, НАБОР + '-glubokiy.jsonl')
ВЫХОД = os.path.join(DIR, НАБОР + '-glubokiy2.jsonl')
ЗАКУПКИ = re.compile(r'zakupki\.gov|roseltorg|b2b-center|etpgpb|fabrikant|rts-tender|sberbank-ast|tektorg', re.I)
_лок = threading.Lock()


def норм_тел(н):
    ц = re.sub(r'\D', '', н or '')
    if len(ц) == 11 and ц[0] in '78':
        ц = '7' + ц[1:]
    elif len(ц) == 10:
        ц = '7' + ц
    return ц if len(ц) == 11 else ''


def одна(x, к):
    открытые = []
    for h in x.get('журнал') or []:
        м = re.match(r'ОТКРЫТ (\S+) \[', h)
        if м:
            открытые.append(м.group(1))
    урлы = list(dict.fromkeys(открытые + [н.get('url') for н in (x.get('номера') or []) + (x.get('почты') or []) + (x.get('снято') or [])
                                          if н.get('url')]))
    for сайт in (x.get('сайт_завода'), x.get('сайт_холдинга')):
        if сайт:
            корень = 'https://' + MN.домен(сайт) + '/'
            урлы += [корень, корень + 'contacts', корень + 'kontakty']
    тексты = {}
    for u in dict.fromkeys(урлы):
        ст, html, _ = MN.скачать(u)
        if ст == 'ok':
            тексты[u] = MP.в_текст(html)
    по_домену = {}
    for u, т in тексты.items():
        по_домену.setdefault(MN.домен(u), []).append(т.lower().replace('ё', 'е'))
    слова = A2.слова(к['имя']) | KS.ядра(к['имя'])

    def подтверждение(сайт):
        тт = ' '.join(по_домену.get(MN.домен(сайт), [])) if сайт else ''
        if not тт:
            return ''
        if к['inn'] in тт:
            return 'ИНН компании на сайте'
        найдено = sorted(w for w in слова if w in тт)
        return ('название на сайте: ' + ', '.join(найдено[:3])) if найдено else ''
    рез = dict(x)
    рез['сайт_завода_чей'] = подтверждение(x.get('сайт_завода'))
    сх = x.get('сайт_холдинга') or ''
    холд = bool(x.get('холдинг_подтверждён'))
    if сх and not холд:
        п = подтверждение(сх)
        if п:
            холд = True
            рез['доказательство_холдинга'] = dict(x.get('доказательство_холдинга') or {}, проверка='на сайте холдинга: ' + п)
    рез['холдинг_подтверждён'] = холд
    годные = set()
    if x.get('сайт_завода') and рез['сайт_завода_чей']:
        годные.add(MN.домен(x['сайт_завода']))
    if сх and холд:
        годные.add(MN.домен(сх))
    номера, снято = [], []
    for н in (x.get('номера') or []) + [с for с in x.get('снято') or [] if not с.get('почта')]:
        ц = норм_тел(н.get('номер'))
        u = н.get('url') or ''
        т = тексты.get(u, '')
        причина = ''
        if not ц:
            причина = 'не номер'
        elif not т:
            причина = 'страница не открылась при перепроверке'
        elif not MP.найти(т, ц[-10:]):
            причина = 'номера нет на странице'
        elif ЗАКУПКИ.search(u):
            if к['inn'] not in т:
                причина = 'на карточке закупки нет ИНН компании'
        elif MN.домен(u) not in годные:
            причина = 'страница не на подтверждённом сайте завода/холдинга (%s)' % MN.домен(u)
        н2 = {k: v for k, v in н.items() if k != 'причина'}
        н2['номер'] = ц
        if причина:
            снято.append(dict(н2, причина=причина))
        else:
            номера.append(н2)
    почты = []  # 09.10: почты агента — те же правила, что у номеров (своя или публичная почта на подтверждённом сайте)
    for п in (x.get('почты') or []) + [с for с in x.get('снято') or [] if с.get('почта')]:
        u, адр = п.get('url') or '', (п.get('почта') or '').lower()
        т = тексты.get(u, '').lower()
        причина = ''
        if not KP.ПОЧТА.fullmatch(адр) or KP.ЛОВУШКИ.search(адр):
            причина = 'не почта'
        elif not т:
            причина = 'страница не открылась при перепроверке'
        elif адр not in т and адр not in KP._раскрыть(т):
            причина = 'почты нет на странице'
        elif ЗАКУПКИ.search(u):
            if к['inn'] not in т:
                причина = 'на карточке закупки нет ИНН компании'
        elif MN.домен(u) not in годные:
            причина = 'страница не на подтверждённом сайте завода/холдинга (%s)' % MN.домен(u)
        elif KP.вид(адр, u) not in ('своя', 'публичная'):
            причина = 'почта чужого домена'
        п2 = {k: v for k, v in п.items() if k != 'причина'}
        if причина:
            снято.append(dict(п2, причина=причина))
        else:
            почты.append(п2)
    рез['номера'], рез['почты'], рез['снято'] = номера, почты, снято
    рез['перепроверено'] = True
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(рез, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
    вх = {}
    for s in io.open(ВХ, encoding='utf-8', errors='replace'):
        x = json.loads(s)
        if x.get('итог') == 'ok':
            вх[x['inn']] = x
    if os.path.exists(ВЫХОД):
        os.remove(ВЫХОД)
    with ThreadPoolExecutor(int(os.environ.get('KC_POTOKOV_SHAGA', '12'))) as ex:  # 09.10: на полном прогоне 24
        list(ex.map(lambda x: одна(x, сп[x['inn']]), [x for x in вх.values() if x['inn'] in сп]))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', НАБОР + '-glubokiy2.jsonl'))
    рез = [json.loads(s) for s in io.open(ВЫХОД, encoding='utf-8')]
    print('===ИТОГ===')
    print(json.dumps({'компаний': len(рез), 'сайт_завода_подтверждён': sum(1 for r in рез if r.get('сайт_завода_чей')),
                      'холдинг_подтверждён': sum(1 for r in рез if r.get('холдинг_подтверждён')),
                      'номеров_принято': sum(len(r['номера']) for r in рез), 'компаний_с_номером': sum(1 for r in рез if r['номера']),
                      'снято': sum(len(r['снято']) for r in рез)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
