"""Auth + Business (docs/PHASE_3_4_PLAN.md §1) — PRD Milestone 1's own "Auth" item,
never built even in Phase 0-1. Off by default (`DEXTER_REQUIRE_AUTH=false`): every
request attributes to an auto-created "default" user + business, the exact
bootstrap-on-first-use pattern Prometheus uses for its first workspace, so the
single-user setup already running today keeps working unchanged.

No Clerk/Auth0 (the PRD's own suggestion) — this backend's stated philosophy is
"starts cleanly with zero external services," and a login screen that hard-depends on
a third-party vendor before the app runs at all breaks that. Passwords are hashed with
stdlib PBKDF2-SHA256 (no new native dependency); sessions are opaque bearer tokens,
hashed at rest — same shape as Prometheus's own MCP token pattern.

Without a database, auth can't persist at all — `current_context()` falls back to the
same fixed default ids with no DB round trip, so the whole app keeps degrading the
way every other module here does.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr

from config import settings
from db.connection import get_pool

log = logging.getLogger("dexter.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEFAULT_USER_ID = "user_default"
DEFAULT_BUSINESS_ID = "biz_default"
DEFAULT_EMAIL = "commander@local"

PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split("$", 1)
    except ValueError:
        return False
    candidate = _hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, stored)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class CurrentContext:
    user_id: str
    email: str
    name: str
    business_id: str
    business_name: str
    role: str  # 'owner' | 'admin' | 'member'


async def ensure_default_context() -> tuple[str, str]:
    """Idempotently creates the fallback user/business used whenever auth is off, or
    when the DB isn't reachable (in which case this is a no-op — the fixed ids are
    returned regardless, since nothing would persist anyway)."""
    pool = await get_pool()
    if pool is None:
        return DEFAULT_USER_ID, DEFAULT_BUSINESS_ID
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO businesses (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (DEFAULT_BUSINESS_ID, "My Business"),
        )
        await conn.execute(
            "INSERT INTO users (id, email, password_hash, name) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (DEFAULT_USER_ID, DEFAULT_EMAIL, "", "Commander"),
        )
        await conn.execute(
            """INSERT INTO business_members (business_id, user_id, role) VALUES (%s, %s, 'owner')
               ON CONFLICT (business_id, user_id) DO NOTHING""",
            (DEFAULT_BUSINESS_ID, DEFAULT_USER_ID),
        )
    return DEFAULT_USER_ID, DEFAULT_BUSINESS_ID


async def _resolve_session(token: str) -> CurrentContext | None:
    pool = await get_pool()
    if pool is None:
        return None
    token_hash = _hash_token(token)
    async with pool.connection() as conn:
        # Prefer the session's own current_business_id (set at login, changeable via
        # switch-business) — but only if that membership still holds (e.g. wasn't
        # removed since). Falls back to the user's first-joined business otherwise,
        # covering sessions from before current_business_id existed and the edge case
        # of losing access to the business a session was pinned to.
        cur = await conn.execute(
            """SELECT u.id, u.email, u.name, b.id, b.name, bm.role
               FROM sessions s
               JOIN users u ON u.id = s.user_id
               JOIN business_members bm ON bm.user_id = u.id AND bm.business_id = s.current_business_id
               JOIN businesses b ON b.id = bm.business_id
               WHERE s.token_hash = %s AND s.expires_at > now()""",
            (token_hash,),
        )
        row = await cur.fetchone()
        if not row:
            cur = await conn.execute(
                """SELECT u.id, u.email, u.name, b.id, b.name, bm.role
                   FROM sessions s
                   JOIN users u ON u.id = s.user_id
                   LEFT JOIN business_members bm ON bm.user_id = u.id
                   LEFT JOIN businesses b ON b.id = bm.business_id
                   WHERE s.token_hash = %s AND s.expires_at > now()
                   ORDER BY bm.joined_at ASC LIMIT 1""",
                (token_hash,),
            )
            row = await cur.fetchone()
    if not row or row[3] is None:
        return None
    return CurrentContext(user_id=row[0], email=row[1], name=row[2] or "", business_id=row[3], business_name=row[4], role=row[5] or "member")


async def current_context(authorization: str | None = Header(default=None)) -> CurrentContext:
    """The FastAPI dependency every business-scoped route takes. Not auth-gated when
    `DEXTER_REQUIRE_AUTH` is off — see module docstring."""
    if not settings.require_auth:
        user_id, business_id = await ensure_default_context()
        return CurrentContext(user_id=user_id, email=DEFAULT_EMAIL, name="Commander", business_id=business_id, business_name="My Business", role="owner")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer <token>")
    ctx = await _resolve_session(authorization[7:].strip())
    if ctx is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session, or account has no business")
    return ctx


async def context_from_token(token: str | None) -> CurrentContext:
    """Same resolution as `current_context`, for WebSockets — browsers can't set custom
    headers on a WS handshake, so the token travels as a query param instead."""
    if not settings.require_auth:
        user_id, business_id = await ensure_default_context()
        return CurrentContext(user_id=user_id, email=DEFAULT_EMAIL, name="Commander", business_id=business_id, business_name="My Business", role="owner")
    if not token:
        raise HTTPException(status_code=401, detail="Missing ?token=")
    ctx = await _resolve_session(token)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return ctx


# ---------------------------------------------------------------- models

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    business_name: str = "My Business"
    invite_code: str = ""  # required only to claim a pending invite


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class AuthOut(BaseModel):
    token: str
    user: UserOut
    business_id: str
    business_name: str
    role: str


class MeOut(BaseModel):
    require_auth: bool
    user: UserOut
    business_id: str
    business_name: str
    role: str


async def _create_session(user_id: str, business_id: str) -> str:
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("Database not configured — auth requires PostgreSQL")
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at, current_business_id) VALUES (%s, %s, %s, %s)",
            (_hash_token(token), user_id, expires_at, business_id),
        )
    return token


@router.post("/register", response_model=AuthOut, status_code=201)
async def register(body: RegisterIn):
    """A brand-new email creates its own business (owner). An email an owner/admin
    already `invite`d (see below — a placeholder row with an unusable password_hash)
    instead *claims* that pending invite: sets the real password, joins the business(es)
    they were already added to, and does NOT create a second business — mirrors
    Prometheus's own claimPendingInvite pattern."""
    pool = await get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not configured — install PostgreSQL to use accounts")

    async with pool.connection() as conn:
        cur = await conn.execute("SELECT id, password_hash FROM users WHERE email = %s", (body.email.lower(),))
        existing = await cur.fetchone()

        if existing and existing[1]:
            raise HTTPException(status_code=409, detail=f"{body.email} is already registered")

        if existing:
            # Claiming a pending invite: same user_id, set the password, join whatever
            # business(es) they were already invited to — never create a new one. Needs
            # the invite code the inviter was shown: knowing an invited email must not be
            # enough to take over the account (and its business memberships).
            user_id = existing[0]
            cur = await conn.execute("SELECT invite_code_hash FROM users WHERE id = %s", (user_id,))
            code_hash = (await cur.fetchone())[0]
            if not body.invite_code or not code_hash or not hmac.compare_digest(_hash_token(body.invite_code.strip()), code_hash):
                raise HTTPException(
                    status_code=403,
                    detail=f"{body.email} has a pending invite — enter the invite code you were sent to claim it",
                )
            await conn.execute(
                "UPDATE users SET password_hash = %s, name = COALESCE(NULLIF(name, ''), %s), invite_code_hash = NULL WHERE id = %s",
                (_hash_password(body.password), body.name or body.email.split("@")[0], user_id),
            )
            cur = await conn.execute(
                """SELECT b.id, b.name, bm.role FROM business_members bm JOIN businesses b ON b.id = bm.business_id
                   WHERE bm.user_id = %s ORDER BY bm.joined_at ASC LIMIT 1""",
                (user_id,),
            )
            biz = await cur.fetchone()
            if not biz:  # shouldn't happen — invite() always adds a membership — but don't strand the account
                biz_id = f"biz_{uuid.uuid4().hex[:8]}"
                await conn.execute("INSERT INTO businesses (id, name) VALUES (%s, %s)", (biz_id, body.business_name.strip() or "My Business"))
                await conn.execute("INSERT INTO business_members (business_id, user_id, role) VALUES (%s, %s, 'owner')", (biz_id, user_id))
                biz = (biz_id, body.business_name.strip() or "My Business", "owner")
        else:
            user_id = f"user_{uuid.uuid4().hex[:8]}"
            business_id = f"biz_{uuid.uuid4().hex[:8]}"
            await conn.execute(
                "INSERT INTO users (id, email, password_hash, name) VALUES (%s, %s, %s, %s)",
                (user_id, body.email.lower(), _hash_password(body.password), body.name or body.email.split("@")[0]),
            )
            await conn.execute(
                "INSERT INTO businesses (id, name) VALUES (%s, %s)",
                (business_id, body.business_name.strip() or "My Business"),
            )
            await conn.execute(
                "INSERT INTO business_members (business_id, user_id, role) VALUES (%s, %s, 'owner')",
                (business_id, user_id),
            )
            biz = (business_id, body.business_name.strip() or "My Business", "owner")

    token = await _create_session(user_id, biz[0])
    return AuthOut(
        token=token, user=UserOut(id=user_id, email=body.email.lower(), name=body.name),
        business_id=biz[0], business_name=biz[1], role=biz[2],
    )


class InviteIn(BaseModel):
    email: EmailStr
    role: str = "member"  # 'admin' | 'member'
    name: str = ""


class InviteOut(BaseModel):
    email: str
    already_a_member: bool
    # One-time code the invitee enters at registration. Only set when the email has no
    # real account yet (an existing account just signs in). Returned once, stored hashed.
    invite_code: str | None = None


@router.post("/invite", response_model=InviteOut, status_code=201)
async def invite_member(body: InviteIn, ctx: CurrentContext = Depends(current_context)):
    """Owner/admin adds an email to their business. If that email hasn't signed up
    anywhere yet, this creates a placeholder account (unusable password_hash — nobody
    can log in as it) plus a one-time invite code, which `register` requires to claim
    it — re-inviting a still-pending email rotates the code. If the email
    already has a real account elsewhere, this just adds them as an additional member
    of THIS business too — `business_members` is many-to-many by design."""
    if ctx.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only an owner or admin can invite members")
    if body.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail='role must be "admin" or "member"')
    pool = await get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not configured — install PostgreSQL to use accounts")

    email = body.email.lower()
    async with pool.connection() as conn:
        invite_code = None
        cur = await conn.execute("SELECT id, password_hash FROM users WHERE email = %s", (email,))
        row = await cur.fetchone()
        if row:
            user_id = row[0]
            if not row[1]:  # still a pending placeholder — rotate its code
                invite_code = secrets.token_urlsafe(12)
                await conn.execute(
                    "UPDATE users SET invite_code_hash = %s WHERE id = %s", (_hash_token(invite_code), user_id),
                )
        else:
            user_id = f"user_{uuid.uuid4().hex[:8]}"
            invite_code = secrets.token_urlsafe(12)
            await conn.execute(
                "INSERT INTO users (id, email, password_hash, name, invite_code_hash) VALUES (%s, %s, '', %s, %s)",
                (user_id, email, body.name or email.split("@")[0], _hash_token(invite_code)),
            )

        cur = await conn.execute(
            "SELECT 1 FROM business_members WHERE business_id = %s AND user_id = %s",
            (ctx.business_id, user_id),
        )
        if await cur.fetchone():
            return InviteOut(email=email, already_a_member=True, invite_code=invite_code)

        await conn.execute(
            "INSERT INTO business_members (business_id, user_id, role) VALUES (%s, %s, %s)",
            (ctx.business_id, user_id, body.role),
        )
    return InviteOut(email=email, already_a_member=False, invite_code=invite_code)


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn):
    pool = await get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not configured — install PostgreSQL to use accounts")

    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, password_hash, name FROM users WHERE email = %s", (body.email.lower(),),
        )
        row = await cur.fetchone()
        if not row or not _verify_password(body.password, row[1]):
            raise HTTPException(status_code=401, detail="Incorrect email or password")
        user_id, _, name = row

        cur = await conn.execute(
            """SELECT b.id, b.name, bm.role FROM business_members bm JOIN businesses b ON b.id = bm.business_id
               WHERE bm.user_id = %s ORDER BY bm.joined_at ASC LIMIT 1""",
            (user_id,),
        )
        biz = await cur.fetchone()
    if not biz:
        raise HTTPException(status_code=403, detail="This account has no business — contact whoever invited you")

    token = await _create_session(user_id, biz[0])
    return AuthOut(
        token=token, user=UserOut(id=user_id, email=body.email.lower(), name=name or ""),
        business_id=biz[0], business_name=biz[1], role=biz[2],
    )


@router.post("/logout", status_code=204)
async def logout(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        return
    pool = await get_pool()
    if pool is None:
        return
    async with pool.connection() as conn:
        await conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_hash_token(authorization[7:].strip()),))


@router.get("/me", response_model=MeOut)
async def me(ctx: CurrentContext = Depends(current_context)):
    return MeOut(
        require_auth=settings.require_auth,
        user=UserOut(id=ctx.user_id, email=ctx.email, name=ctx.name),
        business_id=ctx.business_id, business_name=ctx.business_name, role=ctx.role,
    )


class MemberOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    joined_at: str


@router.get("/members", response_model=list[MemberOut])
async def list_members(ctx: CurrentContext = Depends(current_context)):
    """Feeds the Team screen — real business_members instead of the TEAM mock."""
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT u.id, u.email, u.name, bm.role, bm.joined_at
               FROM business_members bm JOIN users u ON u.id = bm.user_id
               WHERE bm.business_id = %s ORDER BY bm.joined_at ASC""",
            (ctx.business_id,),
        )
        rows = await cur.fetchall()
    return [MemberOut(id=r[0], email=r[1], name=r[2] or "", role=r[3], joined_at=r[4].isoformat()) for r in rows]


# ---------------------------------------------------------------- multi-business switching

class BusinessOut(BaseModel):
    id: str
    name: str
    role: str
    current: bool


@router.get("/businesses", response_model=list[BusinessOut])
async def list_my_businesses(ctx: CurrentContext = Depends(current_context)):
    """Every business the signed-in user belongs to — feeds the switcher. A user with
    just one (the common case) never sees a switcher at all; that's a frontend call,
    not something this endpoint decides."""
    pool = await get_pool()
    if pool is None:
        return [BusinessOut(id=ctx.business_id, name=ctx.business_name, role=ctx.role, current=True)]
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT b.id, b.name, bm.role FROM business_members bm JOIN businesses b ON b.id = bm.business_id
               WHERE bm.user_id = %s ORDER BY bm.joined_at ASC""",
            (ctx.user_id,),
        )
        rows = await cur.fetchall()
    return [BusinessOut(id=r[0], name=r[1], role=r[2], current=(r[0] == ctx.business_id)) for r in rows]


class SwitchBusinessIn(BaseModel):
    business_id: str


@router.post("/switch-business", response_model=MeOut)
async def switch_business(body: SwitchBusinessIn, authorization: str | None = Header(default=None)):
    """Repoints the CALLING session (not the account) at a different business the user
    is already a member of. Off (DEXTER_REQUIRE_AUTH=false) has exactly one business, so
    this 400s in that mode rather than pretending to switch."""
    if not settings.require_auth:
        raise HTTPException(status_code=400, detail="Auth is off — there is only one business")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer <token>")
    pool = await get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    token_hash = _hash_token(authorization[7:].strip())
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT user_id FROM sessions WHERE token_hash = %s AND expires_at > now()", (token_hash,))
        session_row = await cur.fetchone()
        if not session_row:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        cur = await conn.execute(
            """SELECT b.id, b.name, bm.role FROM business_members bm JOIN businesses b ON b.id = bm.business_id
               WHERE bm.user_id = %s AND bm.business_id = %s""",
            (session_row[0], body.business_id),
        )
        biz = await cur.fetchone()
        if not biz:
            raise HTTPException(status_code=403, detail="You're not a member of that business")

        await conn.execute("UPDATE sessions SET current_business_id = %s WHERE token_hash = %s", (body.business_id, token_hash))
        cur = await conn.execute("SELECT email, name FROM users WHERE id = %s", (session_row[0],))
        user_row = await cur.fetchone()

    return MeOut(
        require_auth=True, user=UserOut(id=session_row[0], email=user_row[0], name=user_row[1] or ""),
        business_id=biz[0], business_name=biz[1], role=biz[2],
    )
