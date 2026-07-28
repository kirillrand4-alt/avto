# -*- coding: utf-8 -*-
"""best-of-N с судьёй (директива владельца 28.07 про бюджет на письмо) и
временная шторка очереди на перегенерацию (confirm.hide_before)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sender.ai_letter import AiLetterGen  # noqa: E402
from sender.store import Store  # noqa: E402

_BODY = ('Добрый день!\n\nСмотрел ваше производство - на линии наверняка '
         'работает пневмоинструмент, и вопрос стабильного давления там '
         'обычно решают заранее, вместе с планом участка. Я подбираю '
         'компрессорное оборудование в Компрессор Центре и помогаю выбрать '
         'машину под реальный расход воздуха. Подскажите, как вы сейчас '
         'закрываете этот вопрос на площадке?\n\n'
         'Если неактуально - извините за письмо, больше не побеспокою.\n\n'
         'С уважением,')
_REC = [{'company_name': 'Завод', 'okved': '25.62', 'contact_name': '',
         'mode': 'GENERIC', 'extra': {}}]


def _mk_caller(журнал):
    """Фейк-провайдер: генерации нумеруются (вариант в теме), судья берёт №1."""
    def caller(prompt: str) -> str:
        if '"choices"' in prompt:
            журнал.append('judge')
            return '{"choices":[{"idx":0,"pick":1}]}'
        n = sum(1 for x in журнал if x == 'gen')
        журнал.append('gen')
        subj = 'Вопрос по азоту' if n == 0 else 'Вопрос по воздуху'
        return ('{"letters":[{"idx":0,"subject":"' + subj + '","body":' +
                __import__('json').dumps(_BODY, ensure_ascii=False) + '}]}')
    return caller


def test_best_of_judge_picks_winner():
    журнал = []
    gen = AiLetterGen(_mk_caller(журнал), facts={}, rounds=0, best_of=2)
    res = gen.generate([dict(r) for r in _REC])
    assert журнал.count('gen') == 2 and журнал.count('judge') == 1
    assert res.ok[0]['subject'] == 'Вопрос по воздуху'   # выбор судьи (pick=1)


def test_best_of_1_no_judge():
    журнал = []
    gen = AiLetterGen(_mk_caller(журнал), facts={}, rounds=0, best_of=1)
    res = gen.generate([dict(r) for r in _REC])
    assert журнал == ['gen'] and res.ok[0]['subject'] == 'Вопрос по азоту'


def test_judge_failure_keeps_first_variant():
    журнал = []

    def caller(prompt: str) -> str:
        if '"choices"' in prompt:
            журнал.append('judge')
            raise RuntimeError('судья упал')
        return _mk_caller(журнал)(prompt)

    gen = AiLetterGen(caller, facts={}, rounds=0, best_of=2, json_tries=1)
    res = gen.generate([dict(r) for r in _REC])
    assert res.ok[0]['subject'] == 'Вопрос по азоту'     # остался вариант №0


def test_confirm_list_updated_after_curtain():
    db = os.path.join(tempfile.mkdtemp(), 's.db')
    st = Store(db)
    st.init_schema()
    r1 = st.confirm_submit(inn='1', email='a@b.ru', subject='s1', body='b1',
                           campaign_id=None)
    r2 = st.confirm_submit(inn='2', email='c@d.ru', subject='s2', body='b2',
                           campaign_id=None)
    rp = st.confirm_submit(inn='3', email='e@f.ru', subject='re', body='br',
                           campaign_id=None, kind='reply')
    # r1 и reply «старые», r2 — свежее шторки
    with st.transaction() as conn:
        conn.execute("UPDATE confirm_reviews SET updated_at='2026-07-27T00:00:00' "
                     "WHERE id IN (?,?)", (r1[0], rp[0]))
        conn.execute("UPDATE confirm_reviews SET updated_at='2026-07-29T00:00:00' "
                     "WHERE id=?", (r2[0],))
    ids = {r['id'] for r in st.confirm_list(status='pending',
                                            updated_after='2026-07-28T12:00:00')}
    assert r2[0] in ids           # перегенерированное видно
    assert r1[0] not in ids       # непересобранное скрыто
    assert rp[0] in ids           # ответы клиентам шторка не прячет
    # без шторки видно всё
    assert len(st.confirm_list(status='pending')) == 3
