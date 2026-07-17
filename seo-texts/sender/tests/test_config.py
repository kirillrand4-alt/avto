# FILE: sender/tests/test_config.py
"""Юнит-тесты для sender/config.py: happy-path, границы и инварианты §5."""

from datetime import date

import pytest

from sender.config import (
    Config,
    ConfigError,
    GatesCfg,
    LegalCfg,
    MailboxCfg,
    WindowCfg,
)


BASE_YAML = """\
service:
  name: rusprom-sender
  db_path: /tmp/sender.db
  tick_interval_sec: 60
  dry_run: false
  sandbox_smtp: "localhost:8025"

timezone: "Europe/Moscow"

legal:
  entity: "ООО «Руспром»"
  inn: "7700000000"
  unsub_base_url: "https://parsercompressor.online/u"
  unsub_secret_env: UNSUB_SIGNING_SECRET
  refusal_log_max_lag_hours: 24

window:
  days: [1,2,3,4,5]
  start: "09:30"
  end: "18:00"

holidays:
  - "2025-01-01"
  - "2025-05-09"

ramp_curves:
  yandex:  [3, 5, 8, 12, 18, 25, 32, 40, 50]
  mailru:  [3, 5, 8, 12, 18, 25, 32, 40, 50]
  google:  [2, 3, 5, 8, 12, 18, 25, 35, 50]
  outlook: [2, 3, 5, 8, 12, 18, 25, 35, 50]

send_pacing:
  min_interval_sec: 90
  max_interval_sec: 420
  jitter: true

provider_split:
  match_recipient_provider: true
  pools:
    pool_yandex:  [box1@rusprom.ru, box2@rusprom.ru]
    pool_mailru:  [box3@rusprom.ru, box4@rusprom.ru]
    pool_google:  [box5@rusprom.ru]
    pool_fallback: [box1@rusprom.ru]
  routing:
    yandex:  pool_yandex
    mailru:  pool_mailru
    google:  pool_google
    other:   pool_fallback

mailboxes:
  - mailbox_id: box1@rusprom.ru
    provider: yandex
    smtp_host: smtp.yandex.ru
    smtp_port: 465
    imap_host: imap.yandex.ru
    imap_port: 993
    login: box1@rusprom.ru
    password_env: BOX1_PASSWORD
    from_name: "Иван Петров, Руспром"
    signature_ref: sig_ivan
    pool: pool_yandex
    is_warmup_node: false
  - mailbox_id: box2@rusprom.ru
    provider: yandex
    smtp_host: smtp.yandex.ru
    smtp_port: 465
    imap_host: imap.yandex.ru
    imap_port: 993
    login: box2@rusprom.ru
    password_env: BOX2_PASSWORD
    from_name: "Пётр Иванов, Руспром"
    signature_ref: sig_petr
    pool: pool_yandex
    is_warmup_node: false
  - mailbox_id: box3@rusprom.ru
    provider: mailru
    smtp_host: smtp.mail.ru
    smtp_port: 465
    imap_host: imap.mail.ru
    imap_port: 993
    login: box3@rusprom.ru
    password_env: BOX3_PASSWORD
    from_name: "Отдел продаж, Руспром"
    pool: pool_mailru
  - mailbox_id: box4@rusprom.ru
    provider: mailru
    smtp_host: smtp.mail.ru
    smtp_port: 465
    imap_host: imap.mail.ru
    imap_port: 993
    login: box4@rusprom.ru
    password_env: BOX4_PASSWORD
    from_name: "Отдел продаж, Руспром"
    pool: pool_mailru
  - mailbox_id: box5@rusprom.ru
    provider: google
    smtp_host: smtp.gmail.com
    smtp_port: 465
    imap_host: imap.gmail.com
    imap_port: 993
    login: box5@rusprom.ru
    password_env: BOX5_PASSWORD
    from_name: "Иван Петров, Руспром"
    signature_ref: sig_ivan
    pool: pool_google
    is_warmup_node: true

gates:
  domain_bounce_pct: 8.0
  domain_complaint_pct: 0.3
  mailbox_bounce_pct: 6.0
  global_complaint_pct: 0.1
  min_volume: 50

warmup:
  enabled_providers: [google]
  ramp_curve: [2, 3, 5, 8, 12, 18, 25, 35, 50]
  reply_probability: 0.3
  reputation_floor: 0.6

validation:
  check_mx: true
  detect_catch_all: true
  detect_role: true
  detect_disposable: true
  role_prefixes: [info, sales, office, admin, support, mail]

imap:
  poll_interval_sec: 120
  batch: 50
  auto_suppress_on_bounce: true
  auto_suppress_on_complaint: true

personalization:
  fail_on_unfilled: true
  ai_enabled: true
  ai_fields: [equipment_pitch]

suppression:
  competitor_lists:
    - /etc/rusprom/competitors_domains.txt
  default_scope: domain

attribution:
  entity: "ООО «Руспром»"
  entity_inn: "7700000000"
  include_inn_in_first_touch: true
"""


def _env():
    return {
        "BOX1_PASSWORD": "p1",
        "BOX2_PASSWORD": "p2",
        "BOX3_PASSWORD": "p3",
        "BOX4_PASSWORD": "p4",
        "BOX5_PASSWORD": "p5",
        "UNSUB_SIGNING_SECRET": "s3cr3t",
    }


def _write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def _load(tmp_path, text=None, env=None):
    text = BASE_YAML if text is None else text
    env = _env() if env is None else env
    return Config.load(_write(tmp_path, text), env=env)


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_load_happy_basic(tmp_path):
    cfg = _load(tmp_path)
    assert cfg.get("service.name") == "rusprom-sender"
    assert cfg.get("service.tick_interval_sec") == 60
    assert cfg.get("service.dry_run") is False
    assert cfg.get("send_pacing.jitter") is True
    assert cfg.get("send_pacing.min_interval_sec") == 90


def test_mailboxes_count_and_fields(tmp_path):
    cfg = _load(tmp_path)
    boxes = cfg.mailboxes()
    assert len(boxes) == 5
    assert all(isinstance(b, MailboxCfg) for b in boxes)
    by_id = {b.mailbox_id: b for b in boxes}
    assert by_id["box1@rusprom.ru"].provider == "yandex"
    assert by_id["box1@rusprom.ru"].smtp_port == 465
    assert by_id["box1@rusprom.ru"].signature == "sig_ivan"
    assert by_id["box1@rusprom.ru"].is_warmup_node is False
    # у box3 нет signature_ref → None
    assert by_id["box3@rusprom.ru"].signature is None
    assert by_id["box5@rusprom.ru"].is_warmup_node is True


def test_provider_pools(tmp_path):
    cfg = _load(tmp_path)
    pools = cfg.provider_pools()
    assert pools["pool_yandex"] == ["box1@rusprom.ru", "box2@rusprom.ru"]
    assert pools["pool_google"] == ["box5@rusprom.ru"]
    # мутация копии не влияет на конфиг
    pools["pool_google"].append("x")
    assert cfg.provider_pools()["pool_google"] == ["box5@rusprom.ru"]


def test_ramp_curve(tmp_path):
    cfg = _load(tmp_path)
    assert cfg.ramp_curve("yandex") == [3, 5, 8, 12, 18, 25, 32, 40, 50]
    assert cfg.ramp_curve("google")[0] == 2


def test_ramp_curve_unknown_provider(tmp_path):
    cfg = _load(tmp_path)
    with pytest.raises(ConfigError):
        cfg.ramp_curve("hotmail")


def test_sending_window(tmp_path):
    cfg = _load(tmp_path)
    w = cfg.sending_window()
    assert isinstance(w, WindowCfg)
    assert w.tz == "Europe/Moscow"
    assert w.days == (1, 2, 3, 4, 5)
    assert w.start == "09:30"
    assert w.end == "18:00"


def test_holidays(tmp_path):
    cfg = _load(tmp_path)
    hol = cfg.holidays()
    assert date(2025, 1, 1) in hol
    assert date(2025, 5, 9) in hol
    assert len(hol) == 2


def test_gates(tmp_path):
    cfg = _load(tmp_path)
    g = cfg.gates()
    assert isinstance(g, GatesCfg)
    assert g.domain_bounce_pct == 8.0
    assert g.global_complaint_pct == 0.1
    assert g.min_volume == 50


def test_legal(tmp_path):
    cfg = _load(tmp_path)
    l = cfg.legal()
    assert isinstance(l, LegalCfg)
    assert l.entity == "ООО «Руспром»"
    assert l.inn == "7700000000"
    assert l.unsub_base_url.startswith("https://")
    assert l.unsub_secret_env == "UNSUB_SIGNING_SECRET"
    assert l.refusal_log_max_lag_hours == 24


# --------------------------------------------------------------------------- #
# get()
# --------------------------------------------------------------------------- #
def test_get_default_and_missing(tmp_path):
    cfg = _load(tmp_path)
    assert cfg.get("does.not.exist", "fallback") == "fallback"
    with pytest.raises(ConfigError):
        cfg.get("does.not.exist")


def test_get_returns_immutable_view(tmp_path):
    cfg = _load(tmp_path)
    days = cfg.get("window.days")
    assert days == (1, 2, 3, 4, 5)  # list → tuple
    nested = cfg.get("provider_split.pools")
    with pytest.raises(TypeError):
        nested["pool_yandex"] = ["x"]  # MappingProxyType — только чтение


# --------------------------------------------------------------------------- #
# YAML-парсер: типы/структуры
# --------------------------------------------------------------------------- #
def test_scalar_types_parsed(tmp_path):
    cfg = _load(tmp_path)
    assert cfg.get("validation.check_mx") is True
    assert cfg.get("gates.domain_complaint_pct") == 0.3
    assert cfg.get("imap.batch") == 50
    assert cfg.get("validation.role_prefixes") == (
        "info", "sales", "office", "admin", "support", "mail",
    )
    # список путей (скаляр со слэшами, без кавычек)
    assert cfg.get("suppression.competitor_lists") == (
        "/etc/rusprom/competitors_domains.txt",
    )
    # значение с двоеточием внутри кавычек не рвётся
    assert cfg.get("service.sandbox_smtp") == "localhost:8025"


# --------------------------------------------------------------------------- #
# Иммутабельность
# --------------------------------------------------------------------------- #
def test_config_is_immutable(tmp_path):
    cfg = _load(tmp_path)
    with pytest.raises(ConfigError):
        cfg.some_attr = 123
    with pytest.raises(ConfigError):
        del cfg._data


def test_mailboxcfg_is_frozen(tmp_path):
    cfg = _load(tmp_path)
    box = cfg.mailboxes()[0]
    with pytest.raises(Exception):
        box.provider = "google"


# --------------------------------------------------------------------------- #
# Безопасные дефолты
# --------------------------------------------------------------------------- #
def test_safe_default_dry_run_true_when_absent(tmp_path):
    text = BASE_YAML.replace("  dry_run: false\n", "")
    cfg = _load(tmp_path, text)
    assert cfg.get("service.dry_run") is True


def test_safe_default_fail_on_unfilled(tmp_path):
    text = BASE_YAML.replace("personalization:\n  fail_on_unfilled: true\n",
                             "personalization:\n")
    cfg = _load(tmp_path, text)
    assert cfg.get("personalization.fail_on_unfilled") is True


# --------------------------------------------------------------------------- #
# Инварианты / негативные случаи
# --------------------------------------------------------------------------- #
def test_missing_mailbox_secret_env(tmp_path):
    env = _env()
    del env["BOX1_PASSWORD"]
    with pytest.raises(ConfigError):
        _load(tmp_path, env=env)


def test_missing_unsub_secret_env(tmp_path):
    env = _env()
    del env["UNSUB_SIGNING_SECRET"]
    with pytest.raises(ConfigError):
        _load(tmp_path, env=env)


def test_ramp_curve_non_decreasing_enforced(tmp_path):
    text = BASE_YAML.replace(
        "yandex:  [3, 5, 8, 12, 18, 25, 32, 40, 50]",
        "yandex:  [50, 40, 8, 12, 18, 25, 32, 40, 50]",
    )
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_ramp_curve_rejects_non_positive(tmp_path):
    text = BASE_YAML.replace(
        "google:  [2, 3, 5, 8, 12, 18, 25, 35, 50]",
        "google:  [0, 3, 5, 8, 12, 18, 25, 35, 50]",
    )
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_window_start_after_end(tmp_path):
    text = BASE_YAML.replace('start: "09:30"', 'start: "18:00"')
    text = text.replace('end: "18:00"', 'end: "09:30"')
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_window_invalid_iso_day(tmp_path):
    text = BASE_YAML.replace("days: [1,2,3,4,5]", "days: [1,2,8]")
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_pool_references_undefined_mailbox(tmp_path):
    text = BASE_YAML.replace(
        "pool_google:  [box5@rusprom.ru]",
        "pool_google:  [box5@rusprom.ru, boxZ@rusprom.ru]",
    )
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_routing_references_undefined_pool(tmp_path):
    text = BASE_YAML.replace("google:  pool_google", "google:  pool_missing")
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_invalid_mailbox_provider(tmp_path):
    text = BASE_YAML.replace("provider: yandex", "provider: hotmail", 1)
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_missing_ramp_curve_for_provider(tmp_path):
    # убираем кривую mailru, но box3/box4 остаются mailru → ошибка
    text = BASE_YAML.replace("  mailru:  [3, 5, 8, 12, 18, 25, 32, 40, 50]\n", "")
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_invalid_legal_inn(tmp_path):
    text = BASE_YAML.replace('inn: "7700000000"', 'inn: "123"', 1)
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_invalid_unsub_base_url(tmp_path):
    text = BASE_YAML.replace(
        'unsub_base_url: "https://parsercompressor.online/u"',
        'unsub_base_url: "ftp://parsercompressor.online/u"',
    )
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_gates_pct_out_of_range(tmp_path):
    text = BASE_YAML.replace("domain_bounce_pct: 8.0", "domain_bounce_pct: 150.0")
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_duplicate_mailbox_id(tmp_path):
    text = BASE_YAML.replace("mailbox_id: box2@rusprom.ru", "mailbox_id: box1@rusprom.ru", 1)
    with pytest.raises(ConfigError):
        _load(tmp_path, text)


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(tmp_path / "nope.yaml", env=_env())
