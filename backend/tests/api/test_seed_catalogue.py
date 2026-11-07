"""Seeding the action catalogue: five actions, each approved once, however often it runs."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from navigator.db import models as m
from navigator.db.session import session_scope
from navigator.seed import load_catalogue

pytestmark = pytest.mark.api

CATALOGUE = Path(__file__).resolve().parents[3] / "config" / "actions" / "catalogue.json"


def test_catalogue_loads_once_however_often_it_runs() -> None:
    load_catalogue(CATALOGUE)
    load_catalogue(CATALOGUE)
    with session_scope() as session:
        actions = session.scalar(select(func.count()).select_from(m.ActionDefinition))
        decisions = session.scalars(select(m.Decision)).all()
        proposed_by = session.scalars(select(m.ActionDefinition.proposed_by)).all()
    assert actions == 5
    assert len(decisions) == 5
    assert {d.reviewer for d in decisions} == {"Catalogue policy"}
    assert {d.decision for d in decisions} == {"approve"}
    assert set(proposed_by) == {"catalogue"}
