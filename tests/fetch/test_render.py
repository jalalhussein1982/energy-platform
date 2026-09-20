"""Placeholder rendering: only delivery_day and scheduled_for exist; nothing is left unrendered."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from energy_platform.fetch.render import FetchContext, RenderError, render, render_with


def ctx() -> FetchContext:
    return FetchContext.for_run(datetime(2026, 9, 17, 22, 30, tzinfo=UTC))


def test_delivery_day_defaults_to_the_prague_civil_date() -> None:
    # 22:30 UTC on the 17th is 00:30 on the 18th in Prague (CEST)
    assert ctx().delivery_day == date(2026, 9, 18)


def test_explicit_delivery_day_wins() -> None:
    c = FetchContext.for_run(
        datetime(2026, 9, 17, 22, 30, tzinfo=UTC), delivery_day=date(2026, 9, 1)
    )
    assert c.delivery_day == date(2026, 9, 1)


def test_naive_scheduled_for_rejected() -> None:
    with pytest.raises(ValueError, match="aware"):
        FetchContext(scheduled_for=datetime(2026, 9, 17), delivery_day=date(2026, 9, 17))  # noqa: DTZ001


def test_date_format_spec_and_t2_url_template() -> None:
    t = (
        "https://www.ote-cr.cz/pubweb/attachments/27/{delivery_day:%Y}/month{delivery_day:%m}"
        "/day{delivery_day:%d}/IM_15MIN_{delivery_day:%d}_{delivery_day:%m}_{delivery_day:%Y}_EN.xlsx"
    )
    assert render(t, ctx()) == (
        "https://www.ote-cr.cz/pubweb/attachments/27/2026/month09/day18/IM_15MIN_18_09_2026_EN.xlsx"
    )


def test_scheduled_for_renders_iso() -> None:
    assert render("{scheduled_for}", ctx()) == "2026-09-17 22:30:00+00:00"
    assert render("{scheduled_for:%Y-%m-%dT%H:%M}", ctx()) == "2026-09-17T22:30"


def test_unknown_placeholder_is_an_error_not_a_literal() -> None:
    with pytest.raises(RenderError, match="unknown placeholder"):
        render("{token}", ctx())


def test_second_stage_fills_soap_params_only() -> None:
    assert render_with("<a>{start_date}</a>", {"start_date": "2026-09-18"}) == "<a>2026-09-18</a>"
    with pytest.raises(RenderError):
        render_with("<a>{end_date}</a>", {"start_date": "2026-09-18"})
