"""Задача 52: дневная квота AI-генерации — расписание, счётчик за день, лимит.

Проверяем инварианты карточки «Дневная квота генерации»:
  * расписание — карта дата -> число, переживает перечитывание (panel_settings);
  * 0 снимает день, мусорная дата/запредельное число -> ValidationError;
  * счётчик за день читается из ai_letter_log, ok и брак раздельно;
  * лог пишется в UTC, а день считается по Москве (письмо в 23:30 МСК не
    должно уехать в завтрашний счётчик и «вернуть» выбранную квоту);
  * прогон догенерирует ТОЛЬКО недостающее, повторный запуск в тот же день не
    удваивает (идемпотентность по факту, а не по нажатиям);
  * брак съедает квоту (это расход провайдерского API);
  * пустая квота = ничего не делаем, генератор даже не создаётся.

Сети нет: генератор подменён фейком через gen_factory.
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.ai_quota import AiQuota, QUOTA_KEY  # noqa: E402
from sender.dtos import CampaignIn, RecipientIn  # noqa: E402
from sender.errors import ValidationError  # noqa: E402
from sender.store import Store  # noqa: E402

TODAY = "2026-07-25"
TOMORROW = "2026-07-26"


class _Cfg:
    """Минимальный конфиг: только dotted get()."""

    def __init__(self, **kv):
        self._kv = kv

    def get(self, key, default=None):
        return self._kv.get(key, default)


class _FakeResult:
    def __init__(self):
        self.ok = {}
        self.rejected = {}


class _FakeGen:
    """Фейк генератора: сеть не трогаем, поведение задаётся планом.

    plan='ok'   — все письма проходят;
    plan='brak' — все летят в брак (гейт не пустил);
    plan='boom' — провайдер лёг на батче.
    """

    def __init__(self, plan="ok"):
        self.plan = plan
        self.batches = []

    def generate(self, reqs):
        self.batches.append(list(reqs))
        if self.plan == "boom":
            raise RuntimeError("провайдер лёг")
        res = _FakeResult()
        for i, r in enumerate(reqs):
            if self.plan == "brak":
                res.rejected[i] = ["гейт: длинное тире"]
            else:
                res.ok[i] = {"subject": f"вопрос по воздуху {i}",
                             "body": "Добрый день!\n\nС уважением,",
                             "rounds": []}
        return res


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "quota.db"))
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def campaign(store):
    cid = store.create_campaign(CampaignIn(
        name="новостные", legal_entity="ООО «Руспром»", legal_inn="2221239841",
        config={"segment": "новостные"}))
    for i in range(10):
        store.upsert_recipient(RecipientIn(
            email=f"lead{i}@zavod{i}.ru", domain=f"zavod{i}.ru",
            inn=f"770100000{i}", company_name=f"ООО «Завод {i}»",
            okved="25.62", segment="новостные", contact_name="Иван"))
    return cid


def make_quota(store, gen=None, today=TODAY):
    return AiQuota(store, db_path=store._db_path,
                   gen_factory=(lambda: gen) if gen is not None else None,
                   batch=4, today_fn=lambda: today)


def log_row(store, campaign_id, *, status="ok", created_at, recipient_id=None,
            email="x@y.ru"):
    """Строка в ai_letter_log ровно в том формате, что пишет ai_letter.log_results."""
    con = sqlite3.connect(store._db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS ai_letter_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER, recipient_id INTEGER,
        email TEXT, status TEXT, subject TEXT, body TEXT, rounds_json TEXT,
        created_at TEXT)""")
    con.execute("INSERT INTO ai_letter_log(campaign_id, recipient_id, email, status,"
                " subject, body, rounds_json, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (campaign_id, recipient_id, email, status, "тема", "тело", "[]",
                 created_at))
    con.commit()
    con.close()


# ------------------------------------------------------------- расписание --

def test_schedule_roundtrip(store, campaign):
    q = make_quota(store)
    assert q.schedule(campaign) == {}
    q.set_schedule(campaign, {TODAY: 3, TOMORROW: 3, "2026-07-27": 5})
    # перечитываем НОВЫМ объектом: настройка durable в panel_settings
    assert make_quota(store).schedule(campaign) == {
        TODAY: 3, TOMORROW: 3, "2026-07-27": 5}


def test_schedule_patch_merges_and_zero_removes(store, campaign):
    q = make_quota(store)
    q.set_schedule(campaign, {TODAY: 3, TOMORROW: 3})
    q.set_schedule(campaign, {TOMORROW: 5})           # патч, не замена
    assert q.schedule(campaign) == {TODAY: 3, TOMORROW: 5}
    q.set_schedule(campaign, {TODAY: 0})              # 0 = день снят
    assert q.schedule(campaign) == {TOMORROW: 5}


def test_schedule_is_per_campaign(store, campaign):
    other = store.create_campaign(CampaignIn(
        name="meyer", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    q = make_quota(store)
    q.set_schedule(campaign, {TODAY: 3})
    q.set_schedule(other, {TODAY: 7})
    assert q.schedule(campaign) == {TODAY: 3}
    assert q.schedule(other) == {TODAY: 7}
    raw = store.get_setting(QUOTA_KEY)
    assert set(raw) == {str(campaign), str(other)}


@pytest.mark.parametrize("patch", [
    {"25.07.2026": 3},        # не ISO
    {"2026-13-01": 3},        # несуществующий месяц
    {TODAY: "три"},           # не число
    {TODAY: -1},              # отрицательная квота
    {TODAY: 5000},            # опечатка «5» -> «5000»
])
def test_schedule_rejects_garbage(store, campaign, patch):
    with pytest.raises(ValidationError):
        make_quota(store).set_schedule(campaign, patch)


def test_schedule_prunes_ancient_days(store, campaign):
    q = make_quota(store)
    old = (datetime.fromisoformat(TODAY) - timedelta(days=60)).strftime("%Y-%m-%d")
    q.set_schedule(campaign, {old: 3})
    q.set_schedule(campaign, {TODAY: 3})
    assert q.schedule(campaign) == {TODAY: 3}


# ------------------------------------------------- счётчик за день из лога --

def test_days_counts_ok_and_brak_from_log(store, campaign):
    q = make_quota(store)
    q.set_schedule(campaign, {TODAY: 3, TOMORROW: 5})
    log_row(store, campaign, status="ok", created_at=f"{TODAY}T09:00:00+00:00")
    log_row(store, campaign, status="ok", created_at=f"{TODAY}T09:05:00+00:00")
    log_row(store, campaign, status="brak", created_at=f"{TODAY}T09:06:00+00:00")
    rows = {d.date: d for d in q.days(campaign, horizon=3)}
    assert (rows[TODAY].quota, rows[TODAY].generated, rows[TODAY].rejected) == (3, 2, 1)
    assert rows[TODAY].attempts == 3 and rows[TODAY].remaining == 0
    assert (rows[TOMORROW].quota, rows[TOMORROW].generated) == (5, 0)
    assert rows[TOMORROW].remaining == 5


def test_days_ignores_other_campaign(store, campaign):
    other = store.create_campaign(CampaignIn(
        name="meyer", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    log_row(store, other, status="ok", created_at=f"{TODAY}T09:00:00+00:00")
    rows = {d.date: d for d in make_quota(store).days(campaign, horizon=2)}
    assert rows[TODAY].generated == 0


def test_day_boundary_is_moscow_not_utc(store, campaign):
    """23:30 МСК = 20:30 UTC того же дня, а 00:30 МСК = 21:30 UTC вчерашнего.
    Считаем по МСК: иначе ночная генерация «возвращала» бы выбранную квоту."""
    q = make_quota(store)
    log_row(store, campaign, status="ok", created_at=f"{TODAY}T20:30:00+00:00")
    log_row(store, campaign, status="ok", created_at=f"{TODAY}T21:30:00+00:00")
    rows = {d.date: d for d in q.days(campaign, horizon=3)}
    assert rows[TODAY].generated == 1
    assert rows[TOMORROW].generated == 1


def test_days_shows_far_future_entries(store, campaign):
    q = make_quota(store)
    far = (datetime.fromisoformat(TODAY) + timedelta(days=20)).strftime("%Y-%m-%d")
    q.set_schedule(campaign, {far: 4})
    dates = [d.date for d in q.days(campaign, horizon=7)]
    assert len(dates) == 8 and dates[-1] == far


# ------------------------------------------------------------------ прогон --

def test_empty_quota_does_nothing(store, campaign):
    gen = _FakeGen()
    res = make_quota(store, gen).run_today(campaign)
    assert res.generated == 0 and res.planned == 0
    assert res.reason == "квота на этот день не задана"
    assert gen.batches == []      # генератор даже не дёрнули


def test_run_generates_exactly_quota(store, campaign):
    gen = _FakeGen()
    q = make_quota(store, gen)
    q.set_schedule(campaign, {TODAY: 3})
    res = q.run_today(campaign)
    assert (res.generated, res.rejected, res.planned) == (3, 0, 3)
    rows = {d.date: d for d in q.days(campaign, horizon=1)}
    assert rows[TODAY].generated == 3 and rows[TODAY].remaining == 0
    # письма легли в очередь подтверждений (pending), а не в отправку
    pend = store.confirm_list(status="pending", campaign_id=campaign, limit=50)
    assert len(pend) == 3
    assert all(p["panel"].get("ai") and p["panel"].get("quota_day") == TODAY
               for p in pend)


def test_second_run_same_day_does_not_double(store, campaign):
    gen = _FakeGen()
    q = make_quota(store, gen)
    q.set_schedule(campaign, {TODAY: 3})
    q.run_today(campaign)
    res2 = q.run_today(campaign)
    assert res2.generated == 0 and res2.reason == "дневная квота уже выбрана"
    rows = {d.date: d for d in q.days(campaign, horizon=1)}
    assert rows[TODAY].attempts == 3


def test_run_tops_up_only_missing(store, campaign):
    """Квоту подняли с 3 до 5 — догенерируем ДВА, а не пять заново."""
    gen = _FakeGen()
    q = make_quota(store, gen)
    q.set_schedule(campaign, {TODAY: 3})
    q.run_today(campaign)
    q.set_schedule(campaign, {TODAY: 5})
    res = q.run_today(campaign)
    assert res.before == 3 and res.generated == 2
    rows = {d.date: d for d in q.days(campaign, horizon=1)}
    assert rows[TODAY].attempts == 5 and rows[TODAY].remaining == 0


def test_rejected_letters_consume_quota(store, campaign):
    """Брак — тоже расход провайдерского API: за день больше квоты не пробуем."""
    gen = _FakeGen(plan="brak")
    q = make_quota(store, gen)
    q.set_schedule(campaign, {TODAY: 3})
    res = q.run_today(campaign)
    assert (res.generated, res.rejected) == (0, 3)
    res2 = q.run_today(campaign)
    assert res2.generated == 0 and res2.reason == "дневная квота уже выбрана"
    rows = {d.date: d for d in q.days(campaign, horizon=1)}
    assert rows[TODAY].rejected == 3 and rows[TODAY].remaining == 0


def test_run_skips_recipients_that_already_have_letter(store, campaign):
    gen = _FakeGen()
    q = make_quota(store, gen)
    q.set_schedule(campaign, {TODAY: 2})
    q.run_today(campaign)
    first = {r.id for r in q.candidates(campaign, 10)}
    q.set_schedule(campaign, {TODAY: 4})
    q.run_today(campaign)
    second = {r.id for r in q.candidates(campaign, 10)}
    # каждый прогон вычёркивает своих: 10 -> 8 -> 6, и назад никто не возвращается
    assert len(first) == 8 and len(second) == 6
    assert second < first


def test_run_survives_provider_failure(store, campaign):
    """Батч упал — прогон не падает, ошибка видна в отчёте, лог не врёт."""
    gen = _FakeGen(plan="boom")
    q = make_quota(store, gen)
    q.set_schedule(campaign, {TODAY: 3})
    res = q.run_today(campaign)
    assert res.generated == 0 and res.errors and "провайдер лёг" in res.errors[0]
    rows = {d.date: d for d in q.days(campaign, horizon=1)}
    assert rows[TODAY].attempts == 0 and rows[TODAY].remaining == 3


def test_run_stops_when_no_candidates(store, campaign):
    gen = _FakeGen()
    q = make_quota(store, gen)
    q.set_schedule(campaign, {TODAY: 50})
    res = q.run_today(campaign)
    assert res.generated == 10          # в сегменте всего 10 получателей
    q.set_schedule(campaign, {TODAY: 50})
    res2 = q.run_today(campaign)
    assert res2.generated == 0
    assert res2.reason == "нет получателей без письма в этом сегменте"


def test_candidates_left_drops_after_run(store, campaign):
    gen = _FakeGen()
    q = make_quota(store, gen)
    assert q.candidates_left(campaign) == 10
    q.set_schedule(campaign, {TODAY: 4})
    q.run_today(campaign)
    assert q.candidates_left(campaign) == 6


def test_unknown_campaign_is_validation_error(store):
    q = make_quota(store)
    with pytest.raises(ValidationError):
        q.candidates(999, 5)
    with pytest.raises(ValidationError):
        q.set_schedule(999, {TODAY: 3})
    with pytest.raises(ValidationError):
        q.start_run(999)      # ловим до фонового потока, а не в state.error


# ------------------------------------------------------- состояние прогона --

def test_run_state_is_durable_and_unsticks(store, campaign):
    """Служба перезапустилась посреди прогона — UI не должен вечно показывать
    «идёт»: старую отметку помечаем stale и разрешаем новый запуск."""
    q = make_quota(store)
    stale_start = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(
        timespec="seconds")
    store.set_setting("ai_quota_run", {str(campaign): {
        "running": True, "started_at": stale_start, "date": TODAY}})
    st = make_quota(store).run_state(campaign)
    assert st["running"] is False and st["stale"] is True
