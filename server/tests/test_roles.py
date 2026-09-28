"""Role changes and owner invites (auth.role_change_error)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from auth import role_change_error


@pytest.mark.parametrize("caller,target,new,owners,ok", [
    ("owner", "member", "owner", 1, True),     # owner makes someone an owner
    ("owner", "owner", "admin", 2, True),      # demote one of two owners
    ("owner", "owner", "member", 1, False),    # never the last owner
    ("admin", "member", "admin", 1, True),     # admins manage admins/members
    ("admin", "member", "owner", 1, False),    # ...but can't create owners
    ("admin", "owner", "member", 2, False),    # ...or touch owners
    ("member", "member", "admin", 1, False),   # members can't change roles
    ("owner", "member", "superuser", 1, False),
])
def test_role_change_rules(caller, target, new, owners, ok):
    assert (role_change_error(caller, target, new, owners) is None) is ok
