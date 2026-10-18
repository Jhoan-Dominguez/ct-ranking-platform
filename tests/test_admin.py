"""Métricas del panel de administrador."""

import pytest

from app.services import admin


def test_admin_students_frame_flags_risk(session, make_user):
    from app.services import academics

    user = make_user()
    subj = academics.add_subject(session, user.id, name="Física", semester=1)
    academics.add_item(session, user.id, subj.id, name="Parcial", grade=2.0)
    df = admin.students_frame(session)
    row = df[df["id"] == user.id].iloc[0]
    assert row["promedio_general"] == pytest.approx(2.0)
    assert bool(row["en_riesgo"]) is True
    assert admin.global_metrics(session).users == 1
