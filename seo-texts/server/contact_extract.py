# -*- coding: utf-8 -*-
"""Детерминированный экстрактор контактов и ролей — ловит ВСЕ вариации написания,
роль ставит по local-part и контексту; «кашу» (email без явной роли) отдаёт fable.

Идея (по разбору 500 сайтов): ~91% email лежат в mailto-ссылках, ~59% получают роль
детерминированно (local-part/метка). Значит основную массу тянем СКРИПТОМ (дёшево),
а дорогую модель зовём только на неоднозначный остаток → экономия в разы.

API:
  extract(html) -> {"emails":[{email,role,role_src,ctx,src}], "phones":[...], "kasha":[email...]}
  resolve_roles_llm(kasha, text, company, model='claude-haiku-4-5') -> {email: role}  (fable/haiku)
"""
import os, re, json

EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
_IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico')
_MAILTO_RE = re.compile(r'mailto:([^"\'?>\s]+)', re.I)
_TEL_RE = re.compile(r'tel:([+\d\s\-()]{7,})', re.I)
_JSONLD_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_DATA_EMAIL = re.compile(r'data-(?:email|mail)\s*=\s*["\']([^"\']+)["\']', re.I)
_PHONE_RE = re.compile(r'(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}')

# деобфускация: собака/at/&#64;/＠ -> @ ; точка/dot -> .  (только скобочные/спелл-формы,
# чтобы не ловить слова 'at'/'dot' в обычном тексте)
_DEOBF = [(re.compile(p, re.I), r) for p, r in (
    (r'&#0?64;|&commat;|＠|\s*[\[({]\s*(?:at|собака|эт|dog)\s*[\])}]\s*|\s+(?:собака|\(собака\))\s+', '@'),
    (r'\s*[\[({]\s*(?:dot|точка|тчк|точк)\s*[\])}]\s*|\s+(?:точка|\(точка\))\s+', '.'),
)]

# local-part -> роль (прямой сигнал). Правила проверяются СВЕРХУ ВНИЗ, побеждает
# первое — поэтому узкие стоят выше широких.
#
# ПРАВКИ 29.08 по замеру на мейеровской базе (отчёт 02-roli-i-imena.md):
#  * `support` убран из гл.инженера: 228 адресов support@ по мейеру красились в
#    главного инженера, хотя это техподдержка сайта или продукта. Ложная роль
#    хуже отсутствующей — она уезжает в сегментацию и в подпись письма;
#  * `opt` убран из снабжения: он стоял в ДВУХ правилах сразу, побеждало первое,
#    и `opt@` уезжал в закупки, хотя на сайте поставщика это оптовый отдел,
#    то есть продажи (61 адрес по мейеру);
#  * добавлены латинские написания, которых словарь не знал: `secretar`,
#    `secretary`, `contact` — при живых `sekret` и `kontakt`;
#  * добавлены частые ящики из хвоста: склад и логистика, магазин и дилеры,
#    ВЭД, вакансии, финансы, руководство. Замер: +598 ролей в неперелитых
#    находках и +938 в уже залитой базе.
LOCAL_ROLE = [
    (r'^(zakup|snab|snabzh|postavk|torg|zayavk|tender|purchase|procure)', 'снабжение/закупки'),
    (r'^(omts|mto|logist|sklad|warehouse|transport|perevoz)([._\-]|$|\d)', 'снабжение/закупки'),
    (r'^(sale|prodazh|prodaji|sbyt|commerc|kommerc|zakaz|order|market|opt)', 'продажи'),
    (r'^(shop|store|magazin|trade|td|b2b|client|klient|dealer|diler|partner|'
     r'export|eksport|ved|op)([._\-]|$|\d)', 'продажи'),
    (r'^(director|dir|ceo|gendir|glava|rukovod|boss|head|chief)', 'директор'),
    (r'^(kd|gd|komdir|predsedatel|prezident|president|upravl|nachalnik)'
     r'([._\-]|$|\d)', 'директор'),
    (r'^(buh|account|finans|oplata|bill|pay)', 'бухгалтерия'),
    (r'^(glavbuh|glbuh|fin|finance|econom|smeta|kassa|invoice)([._\-]|$|\d)',
     'бухгалтерия'),
    (r'^(inzh|engineer|tech|tehn|service|servis|proekt|konstr)', 'гл.инженер'),
    (r'^(hr|kadr|personal|resume|vacan|job)', 'кадры'),
    (r'^(career|careers|rabota|vacancy|vakansi|trud)([._\-]|$|\d)', 'кадры'),
    (r'^(secretar|secretary|kanc|kancel|referent|priemn|priyomn)([._\-]|$|\d)',
     'общий/приёмная'),
    (r'^(contact|feedback|help|hotline|callback|obratn|zvonok|support)'
     r'([._\-]|$|\d)', 'общий/приёмная'),
    (r'^(info|office|ofis|mail|post|priem|reception|sekret|kontakt|general|company|zavod|firma|manager|adm|welcome|hello|zakaz)', 'общий/приёмная'),
]
CTX_ROLE = [
    (r'закуп|снабж|тендер|поставщик|отдел\s+закуп', 'снабжение/закупки'),
    (r'прода|сбыт|коммерч|отдел\s+прод|менеджер\s+по\s+прод|заявк|заказ', 'продажи'),
    (r'директор|руководител|генеральн', 'директор'),
    (r'бухгалт|финанс', 'бухгалтерия'),
    (r'гл\.?\s*инженер|главн\w*\s+инженер|технич|сервис|проектн|конструктор', 'гл.инженер'),
    (r'приёмн|приемн|секрет|ресепш', 'общий/приёмная'),
    (r'кадр|персонал|ваканс', 'кадры'),
]


def _deobf(s):
    for rx, rep in _DEOBF:
        s = rx.sub(rep, s)
    return s


def _role_by_local(local):
    l = (local or '').lower()
    for rx, role in LOCAL_ROLE:
        if re.search(rx, l):
            return role
    return None


def _role_by_ctx(ctx):
    c = (ctx or '').lower()
    for rx, role in CTX_ROLE:
        if re.search(rx, c):
            return role
    return None


def extract(html):
    """Извлечь все email/телефоны (все вариации) + детерминированную роль. blob = сырой HTML."""
    blob = html or ''
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', blob, flags=re.S | re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    raw_found = set(e.lower() for e in EMAIL_RE.findall(text))
    src = {}   # email -> метод-источник

    def add(e, method):
        e = e.strip().lower()
        if EMAIL_RE.fullmatch(e) and not e.endswith(_IMG_EXT):
            src.setdefault(e, method)

    for m in _MAILTO_RE.findall(blob):
        add(m.split('?')[0], 'mailto')
    for m in _DATA_EMAIL.findall(blob):
        add(m, 'data-attr')
    for js in _JSONLD_RE.findall(blob):
        for e in EMAIL_RE.findall(js):
            add(e, 'jsonld')
    for e in raw_found:
        add(e, 'text')
    for e in EMAIL_RE.findall(_deobf(text)):
        if e.lower() not in raw_found:
            add(e, 'deobf')

    # телефоны (все вариации)
    phones = set()
    for t in _TEL_RE.findall(blob):
        d = re.sub(r'\D', '', t)
        if 10 <= len(d) <= 12:
            phones.add(d)
    for p in _PHONE_RE.findall(text):
        phones.add(re.sub(r'\D', '', p))
    for js in _JSONLD_RE.findall(blob):
        for t in re.findall(r'"telephone"\s*:\s*"([^"]+)"', js):
            d = re.sub(r'\D', '', t)
            if 10 <= len(d) <= 12:
                phones.add(d)

    low = text.lower()
    emails, kasha = [], []
    for e, method in src.items():
        pos = low.find(e)
        ctx = re.sub(r'\s+', ' ', text[max(0, pos - 80):pos + len(e) + 25]).strip() if pos >= 0 else ''
        local = e.split('@')[0]
        role = _role_by_local(local)
        role_src = 'local-part' if role else None
        if not role:
            role = _role_by_ctx(ctx)
            role_src = 'context' if role else None
        rec = {'email': e, 'role': role, 'role_src': role_src, 'ctx': ctx, 'src': method}
        emails.append(rec)
        if not role:
            kasha.append(e)
    return {'emails': emails, 'phones': sorted(phones), 'kasha': kasha}


def resolve_roles_llm(kasha, text, company, model='claude-haiku-4-5'):
    """Роль для «каши» (email без детерминированной роли) — дешёвой моделью (haiku по умолч.)."""
    if not kasha:
        return {}
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        import gen_provider as G
    except Exception:
        return {}
    prompt = (
        f'Компания «{company.get("name","")}». Для КАЖДОГО из этих email определи роль владельца '
        f'по тексту сайта: снабжение/закупки | продажи | директор | гл.инженер | бухгалтерия | '
        f'кадры | общий/приёмная. Email: {", ".join(kasha)}. Верни СТРОГО JSON '
        f'{{"roles":{{"email":"роль"}}}}. Текст сайта:\n' + (text or '')[:12000])
    for _ in range(3):
        try:
            msg = G._raw_stream([{'role': 'user', 'content': prompt}], model, 1200, thinking=False)
            out = ''.join(b.text for b in msg.content if b.type == 'text')
            m = re.search(r'\{.*\}', out, re.S)
            if m:
                return json.loads(m.group(0)).get('roles', {})
        except Exception:
            import time
            time.sleep(2)
    return {}


if __name__ == '__main__':
    import sys
    html = sys.stdin.read()
    print(json.dumps(extract(html), ensure_ascii=False, indent=1))
