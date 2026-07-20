"""Инварианты golden-отчёта ревью-конвейера (REVIEW-CHAIN.md §Тест-сет).

Отчёт `autoresponder-golden-report.json` — артефакт ЖИВОГО прогона 14 писем
дрйрана через конвейер (tools/run_golden_review.py, провайдерские линзы).
Здесь без сети: проверяем, что закоммиченный отчёт удовлетворяет обязательным
попаданиям спеки. Если отчёт перегенерирован и попадания регрессировали —
тест обязан покраснеть (recall реальных ошибок упал).
"""

import json
import pathlib

import pytest

REPORT = pathlib.Path(__file__).resolve().parents[1] / "autoresponder-golden-report.json"


@pytest.fixture(scope="module")
def report() -> dict:
    assert REPORT.exists(), (
        "нет autoresponder-golden-report.json — прогони "
        "python3 sender/tools/run_golden_review.py"
    )
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_all_letters_processed(report):
    assert report["summary"]["letters"] == 14
    assert report["summary"]["errors"] == []
    assert len(report["letters"]) == 14


def test_n9_hot_bargaining_escalated(report):
    """№9 — незакрытый горячий торг («дайте 10% и подпишем сегодня»).

    Спека: конвейер ОБЯЗАН отдать человеку (эскалация-гейт, без перегенераций).
    """
    assert report["summary"]["n9_escalated"] is True
    row = next(r for r in report["letters"] if r["n"] == 9)
    assert row["decision"] == "ESCALATE"


def test_n3_n5_invented_facts_critical(report):
    """№3 (Enger BS-7.5D/BAOSI) и №5 (2,45 млн; ISO 8573) — цифры не из базы.

    Спека: CRITICAL именно от факт-чекера (сверка с answer-kb), не общий FIX.
    """
    assert report["summary"]["n3_fact_critical"] is True
    assert report["summary"]["n5_fact_critical"] is True
    for n in (3, 5):
        row = next(r for r in report["letters"] if r["n"] == n)
        assert row["verdicts"]["fact_check"]["verdict"] == "CRITICAL", row["n"]


def test_n12_caught(report):
    """№12 — конвейер не пропускает письмо как есть.

    Цифра «5580+ проектов» ЕСТЬ в answer-kb (company.experience), поэтому
    честный факт-чекер её подтверждает — ловится письмо механикой (длинное
    тире -> qa) и/или совещательными линзами: решение НЕ SEND.
    """
    assert report["summary"]["n12_caught"] is True
    row = next(r for r in report["letters"] if r["n"] == 12)
    assert row["decision"] != "SEND"


def test_no_first_pass_send_without_clean_verdicts(report):
    """SEND первого прохода допустим только при полностью чистых вердиктах."""
    for row in report["letters"]:
        if row["decision"] == "SEND":
            assert not row["qa_problems"], row["n"]
            assert all(
                v["verdict"] != "CRITICAL" for v in row["verdicts"].values()
            ), row["n"]
