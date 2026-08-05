# -*- coding: utf-8 -*-
"""Единый выбор адресата письма: одно правило вместо двух расходящихся. С пробой.

ЗАЧЕМ. В `enrich_contacts.py` выбор адресата делают ДВА разных правила, и они молча
расходятся:

  * `_best_by_role` (стр. ~405) — словарь `_ROLE_RANK` с ТОЧНЫМ совпадением строки роли.
    Он пишет `companies.best_email`, то есть решает, кому уйдёт письмо.
  * `best_email_v2` (стр. ~5257) — ПОДСТРОКИ плюс запреты и веса за именной адрес, MX,
    источник.

ЗАМЕР НА ЖИВОЙ БАЗЕ (enrich.db, 20 398 адресов, 4 565 компаний с best_email):

    роль НЕ попадает в семь точных ключей v1              5 141
      из них ТЕХНИЧЕСКАЯ или ЗАКУПОЧНАЯ                     397  <- проигрывают info@
      из них роль пустая                                  4 397
      из них кадры/пресса (ранг 9 тут кстати)                343
    на компаниях с 2+ адресами v1 и v2 выбрали РАЗНОЕ       967 из 3 170
    best_email — «непокупающий» отдел                        98 (+11 ложных, см. ниже)
    АДРЕС У НЕСКОЛЬКИХ ПРЕДПРИЯТИЙ                          113 адресов, 271 предприятие
    есть технический адрес, а письмо пойдёт на общий         182

397 технических ролей — это гл.механик, гл.энергетик, нач.производства, закупки,
техдиректор, АСУ/КИПиА, нач.цеха. Ровно круг 1-2, ради которого всё затевалось. У v1
они получают ранг 9, то есть ХУЖЕ «общего» info@. Заслон, поставленный раньше
разрешения, отменяет разрешение молча.

У v2 своя болезнь, обратная: подстрока `hr` находится внутри «sear-CHR-u», `smi` внутри
«SMIrnova» и «jaSMIn», `buh` внутри «BUHdorsk». 11 живых best_email забракованы так.
Это тот же класс, что «к/с», совпавшее с окончанием слова «фаКС».

ЧТО ЗДЕСЬ СОБРАНО — приборы, которые сегодня уже отработали на моём канале:

  1. РОЛЬ ПО ПОДСТРОКЕ, НО С ГРАНИЦЕЙ. Лечит обе болезни разом: «закупки» и
     «гл. инженер» узнаются (v1 их терял), а «smirnova» не считается прессой
     (v2 её терял).
  2. АДРЕС У НЕСКОЛЬКИХ ПРЕДПРИЯТИЙ — НЕ АДРЕС ПРЕДПРИЯТИЯ. Сегодня это правило
     поймало больше всех в моём канале. `tarakanova@aoosk.ru` стоит у шести ИНН,
     `catmen@rusal.com` у пяти: это управляющая компания или холдинг, а не завод.
  3. СВОЙ ДОМЕН — ПРОВЕНАНС. В сегодняшней прогулке по 45 карточкам с проваливанием
     в первоисточник совпадение было 14 из 14 там, где источник — сайт самого
     предприятия. Адрес на чужом домене этого не даёт.
  4. РАЗДЕЛЯТЬ, А НЕ ОТСЕИВАТЬ. Запрещённый адрес не выбрасывается: он остаётся с
     явно названным видом («кадры», «бухгалтерия»), просто не может стать адресатом.
  5. ПРОВЕНАНС НАКАПЛИВАЕТСЯ. Функция возвращает не только адрес, но и ПОЧЕМУ он
     выбран, — строкой, которую видно оператору.

Проба (`--proba`) проверяет РАЗЛИЧЕНИЕ, а не непустоту: те же входы разными правилами
дают разное, а бессмыслица даёт ноль.
"""
import collections
import json
import re
import sys

# --- Роли: ключ -> вес. Чем больше, тем лучше адресат холодного письма.
# Порядок владельца: снабжение/закупки > гл.инженер > директор > продажи > приёмная.
# Технические службы (механик, энергетик, производство, АСУ) стоят рядом с инженером:
# это тот же круг 1-2, и в замере их 397 — они не должны проигрывать «общему».
VES_ROLI = (
    ('закупк', 100), ('снабж', 98), ('тендер', 95),
    ('гл.инженер', 90), ('главный инженер', 90), ('гл. инженер', 90),
    ('техдир', 88), ('технический директор', 88),
    ('гл.энергетик', 86), ('главный энергетик', 86),
    ('гл.механик', 86), ('главный механик', 86),
    ('гл.технолог', 84), ('главный технолог', 84), ('технолог', 80),
    ('нач.производств', 82), ('начальник производств', 82), ('производ', 78),
    ('асу', 76), ('кипиа', 76), ('кип', 76),
    ('нач.цеха', 74), ('начальник цеха', 74),
    ('техконтакт', 70), ('инженер', 68),
    ('директор', 60), ('руковод', 55),
    ('менеджер', 40), ('продаж', 35), ('прием', 25), ('приём', 25),
    ('общий', 10),
)

# Отделы, которые НЕ покупают наше оборудование. Не выбрасываем — не даём стать
# адресатом (правило «разделять, а не отсеивать»).
NE_ADRESAT_ROL = ('кадр', 'персонал', 'подбор', 'ваканс', 'пресс', 'юрис', 'бухгалт',
                  'реклам', 'маркет', 'сми', 'hr')
# Те же отделы, но по САМОМУ адресу: роль часто пустая, а local-part говорит правду.
NE_ADRESAT_LOCAL = ('press', 'pressa', 'smi', 'hr', 'kadr', 'vacan', 'job', 'rabota',
                    'rekla', 'marketing', 'legal', 'urist', 'jurist', 'buh', 'buhgalter',
                    'account', 'noreply', 'no-reply', 'abuse', 'postmaster', 'spam')
OBSHCHIY = ('info', 'mail', 'office', 'zakaz', 'order', 'secretar', 'priemnaya',
            'inbox', 'post', 'contact', 'reception', 'admin', 'support', 'help',
            'shop', 'market', 'sale', 'sales')
FREEMAIL = ('mail.ru', 'bk.ru', 'inbox.ru', 'list.ru', 'yandex.ru', 'ya.ru',
            'gmail.com', 'rambler.ru', 'internet.ru', 'icloud.com', 'outlook.com',
            'hotmail.com', 'mail.com')


def chasti_adresa(email):
    """Local-part, разрезанный на осмысленные части: точка, дефис, подчёркивание, цифры."""
    lp = str(email or '').split('@')[0].lower()
    return [c for c in re.split(r'[^a-zа-яё]+', lp) if c]


def domen(x):
    d = str(x or '').strip().lower()
    d = re.sub(r'^https?://', '', d).split('/')[0]
    d = re.sub(r'^www\.', '', d)
    return d.split('@')[-1] if '@' in str(x or '') else d


def klyuch_v_chasti(chast, klyuch):
    """Ключ признаётся, если он ОТДЕЛЬНАЯ часть адреса, а не буквы внутри слова.

    Без этого `hr` находится в «sear-CHR-u», `smi` в «SMIrnova», `buh` в «BUHdorsk» —
    одиннадцать живых адресов забракованы так. Разрешаю ключ как целую часть или как
    её начало/конец, но только если часть не длиннее ключа на 4 буквы: «buhgalteriya»
    это бухгалтерия, «buhta» — нет.
    """
    if chast == klyuch:
        return True
    if (chast.startswith(klyuch) or chast.endswith(klyuch)) and \
            len(chast) <= len(klyuch) + 4:
        return True
    return False


def ne_adresat(email, rol):
    """Не адресат коммерческого письма? Возвращает причину словом или пусто."""
    r = str(rol or '').lower()
    for k in NE_ADRESAT_ROL:
        if k in r:
            return 'роль «%s»' % k
    for c in chasti_adresa(email):
        for k in NE_ADRESAT_LOCAL:
            if klyuch_v_chasti(c, k):
                return 'адрес «%s»' % k
    return ''


def ves_roli(rol):
    r = str(rol or '').strip().lower()
    if not r:
        return 0, ''
    for k, v in VES_ROLI:
        if k in r:
            return v, k
    return 0, ''


def obshchiy_adres(email):
    return any(klyuch_v_chasti(c, k) for c in chasti_adresa(email) for k in OBSHCHIY)


def imennoy_adres(email):
    """Именной адрес: в local-part есть часть длиннее 3 букв, не из общего словаря."""
    for c in chasti_adresa(email):
        if len(c) > 3 and not any(klyuch_v_chasti(c, k) for k in OBSHCHIY):
            return True
    return False


def vybrat_adresata(kontakty, sayt='', adres_u_neskolkih=(), model_pick=''):
    """Кому слать. Возвращает (адрес, почему-строкой, разложение по всем адресам).

    kontakty: список словарей {email, role, person, mx_ok, source}.
    sayt: домен предприятия (для правила «свой домен»).
    adres_u_neskolkih: множество адресов, замеченных у 2+ ИНН.
    model_pick: ответ модели — только разрешение ничьей при равном весе.
    """
    svoy = domen(sayt)
    razbor = []
    for k in (kontakty or []):
        if not isinstance(k, dict):
            continue
        e = str(k.get('email') or '').strip().lower()
        if not e or '@' not in e:
            continue
        rol = k.get('role') or ''
        prichina = ne_adresat(e, rol)
        ves, po_klyuchu = ves_roli(rol)
        pochemu = []
        if prichina:
            razbor.append({'email': e, 'ves': -1000, 'vid': 'не адресат: ' + prichina,
                           'pochemu': prichina})
            continue
        s = ves
        if e in (adres_u_neskolkih or ()):
            # ПРАВИЛО ПЕРЕНОСИТСЯ С ТЕЛЕФОНОВ НЕ БУКВАЛЬНО, и сухой прогон это показал.
            # На номерах «у нескольких предприятий» = линия посредника, и запрет верен.
            # На почте иначе: у холдинга ОДИН закупщик обслуживает несколько юрлиц —
            # `zakupki@tatprof.ru` стоит у двух ИНН, `catmen@rusal.com` у пяти, и это
            # правильный адресат, а не посредник. Первый заход убивал такие адреса
            # весом -500, и письмо уезжало на бесплатную почту вместо закупщика.
            # Отличаю по домену: свой домен — общий закупщик группы (не наказываю),
            # чужой — действительно посредник или справочник (наказываю, но не убиваю,
            # чтобы не остаться совсем без адреса).
            if domen(e) and svoy and domen(e) == svoy:
                pochemu.append('общий адрес группы (свой домен)')
            else:
                s -= 60
                pochemu.append('адрес у нескольких предприятий, домен чужой')
        if po_klyuchu:
            pochemu.append('роль «%s»' % po_klyuchu)
        d = domen(e)
        if svoy and d == svoy:
            s += 40
            pochemu.append('домен предприятия')
        elif svoy and d and d not in svoy and svoy not in d:
            s -= 20
            pochemu.append('ЧУЖОЙ домен')
        if d in FREEMAIL:
            s -= 15
            pochemu.append('бесплатная почта')
        if str(k.get('person') or '').strip():
            s += 30
            pochemu.append('назван человек')
        if imennoy_adres(e) and not obshchiy_adres(e):
            s += 25
            pochemu.append('именной адрес')
        if k.get('mx_ok') in (1, '1', True):
            s += 10
            pochemu.append('живой MX')
        if str(k.get('source') or '').startswith('zakupki'):
            s += 15
            pochemu.append('контакт из карточки закупки')
        if e == str(model_pick or '').strip().lower():
            s += 1          # только разрешение ничьей
            pochemu.append('выбор модели (ничья)')
        razbor.append({'email': e, 'ves': s, 'vid': 'кандидат',
                       'pochemu': ', '.join(pochemu) or 'без признаков'})
    if not razbor:
        return '', 'адресов нет', []
    razbor.sort(key=lambda z: -z['ves'])
    luchshiy = razbor[0]
    if luchshiy['ves'] <= -500:
        return '', 'все адреса непригодны: ' + luchshiy['vid'], razbor
    return luchshiy['email'], luchshiy['pochemu'], razbor


# ---------------------------------------------------------------- проба
def proba():
    """Проба на РАЗЛИЧЕНИЕ: разные входы дают разное, бессмыслица даёт ноль."""
    V1 = {'снабжение/закупки': 0, 'гл.инженер': 1, 'директор': 2, 'продажи': 3,
          'приёмная': 4, 'бухгалтерия': 5, 'общий': 6}

    def v1(kont):
        rows = [k for k in kont if k.get('email')]
        if not rows:
            return ''
        return sorted(rows, key=lambda e: V1.get(
            (e.get('role') or '').strip().lower(), 9))[0]['email']

    sluchai = [
        ('технический круг 1-2 против общего',
         [{'email': 'info@zavod.ru', 'role': 'общий'},
          {'email': 'ivanov@zavod.ru', 'role': 'гл.механик', 'person': 'Иванов'}],
         'zavod.ru', 'ivanov@zavod.ru'),
        ('закупки без слова «снабжение»',
         [{'email': 'info@zavod.ru', 'role': 'общий'},
          {'email': 'zakupki@zavod.ru', 'role': 'закупки'}],
         'zavod.ru', 'zakupki@zavod.ru'),
        ('гл. инженер с пробелом',
         [{'email': 'mail@zavod.ru', 'role': 'общий'},
          {'email': 'petrov@zavod.ru', 'role': 'Гл. инженер'}],
         'zavod.ru', 'petrov@zavod.ru'),
        ('бухгалтерия НЕ лучше общего',
         [{'email': 'info@zavod.ru', 'role': 'общий'},
          {'email': 'buh@zavod.ru', 'role': 'бухгалтерия'}],
         'zavod.ru', 'info@zavod.ru'),
        ('кадры не адресат даже с именем',
         [{'email': 'info@zavod.ru', 'role': 'общий'},
          {'email': 'hr@zavod.ru', 'role': 'кадры', 'person': 'Сидорова'}],
         'zavod.ru', 'info@zavod.ru'),
        ('фамилия Смирнова — НЕ пресс-служба',
         [{'email': 'info@zavod.ru', 'role': 'общий'},
          {'email': 'smirnova@zavod.ru', 'role': 'снабжение', 'person': 'Смирнова'}],
         'zavod.ru', 'smirnova@zavod.ru'),
        ('адрес у нескольких предприятий не берём',
         [{'email': 'catmen@holding.com', 'role': 'снабжение/закупки'},
          {'email': 'info@zavod.ru', 'role': 'общий'}],
         'zavod.ru', 'info@zavod.ru'),
        ('свой домен важнее чужого при равной роли',
         [{'email': 'zakupki@chuzhoy.ru', 'role': 'закупки'},
          {'email': 'zakupki@zavod.ru', 'role': 'закупки'}],
         'zavod.ru', 'zakupki@zavod.ru'),
        ('адресов нет — пусто, а не выдумка', [], 'zavod.ru', ''),
        ('только кадры — пусто, слать некому',
         [{'email': 'hr@zavod.ru', 'role': 'кадры'}], 'zavod.ru', ''),
    ]
    obshchie = {'catmen@holding.com'}
    plohо = razoshlis = 0
    print('%-42s %-26s %-26s' % ('случай', 'новое правило', 'старое v1'))
    for imya, kont, sayt, nado in sluchai:
        got, pochemu, _ = vybrat_adresata(kont, sayt, obshchie)
        staroe = v1(kont)
        ok = got == nado
        plohо += (not ok)
        razoshlis += (got != staroe)
        print('%-42s %-26s %-26s %s' % (imya[:42], got or '(пусто)',
                                        staroe or '(пусто)', 'ок' if ok else 'ВРАНЬЁ'))
    print('\nвраньё нового правила: %d из %d' % (plohо, len(sluchai)))
    print('разошлось со старым v1: %d из %d (если 0 — чинить было нечего)'
          % (razoshlis, len(sluchai)))
    print('ИТОГ ' + json.dumps({'враньё': plohо, 'расхождений со старым': razoshlis},
                               ensure_ascii=False))
    return plohо


if __name__ == '__main__':
    if '--proba' in sys.argv:
        sys.exit(1 if proba() else 0)
    print(__doc__)
