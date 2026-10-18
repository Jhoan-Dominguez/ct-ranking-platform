"""Perfiles de usuario."""

import pytest

from app.services import users


def test_profile_alias_unique_and_semester_bounds(session, make_user):
    a, b = make_user(), make_user()
    users.update_profile(session, a, alias="Lau")
    with pytest.raises(users.ProfileError, match="alias"):
        users.update_profile(session, b, alias="lau")
    with pytest.raises(users.ProfileError, match="semestre"):
        users.update_profile(session, a, current_semester=12, total_semesters=10)
