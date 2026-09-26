"""Archive v1 (Phase 6 in docs/BUILD_PLAN.md) — a personal-intelligence vault on the documents
P5 already ingests: notebooks group documents; `ask` answers only from a notebook's sources and
cites them by number; `briefing` writes a two-voice Dexter/Anthony script over those sources and
synthesizes it with the two Piper voices when voice is installed.

Retrieval is BM25 over ~900-char passages cut on the fly from the stored document text, so it
works with no embedding model; when one is available (`rank_hybrid`) the candidates are re-ranked
by blending BM25 with embedding similarity, which finds passages that answer in other words.
"""
from __future__ import annotations

import base64
import io
import logging
import math
import re
import uuid
import wave
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import CurrentContext, current_context
from db.connection import get_pool

log = logging.getLogger("dexter.archive")

router = APIRouter(prefix="/api/archive", tags=["archive"])

PASSAGE_CHARS = 900
TOP_K = 6
_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("the a an and or of to in on for is are was were be with as by at it this that from not but".split())


# ---------------------------------------------------------------- pure helpers (tested)

def passages(doc_id: str, title: str, text: str, size: int = PASSAGE_CHARS) -> list[dict]:
    """Split on paragraph breaks, packing paragraphs up to ~size chars per passage."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[dict] = []
    buf = ""
    for p in paras:
        while len(p) > size:  # one huge paragraph: hard-wrap it
            if buf:
                out.append(buf)
                buf = ""
            out.append(p[:size])
            p = p[size:]
        if buf and len(buf) + len(p) + 2 > size:
            out.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        out.append(buf)
    return [{"doc_id": doc_id, "title": title, "index": i, "text": t} for i, t in enumerate(out)]


def _terms(s: str) -> list[str]:
    return [w for w in _WORD.findall(s.lower()) if w not in _STOP and len(w) > 1]


def rank_passages(question: str, pool: list[dict], k: int = TOP_K) -> list[dict]:
    """BM25 over the notebook's passages."""
    q = set(_terms(question))
    if not q or not pool:
        return []
    docs = [Counter(_terms(p["text"])) for p in pool]
    n = len(docs)
    avg = sum(sum(d.values()) for d in docs) / n or 1.0
    df = {t: sum(1 for d in docs if t in d) for t in q}
    scored = []
    for p, d in zip(pool, docs):
        length = sum(d.values()) or 1
        score = 0.0
        for t in q:
            if not d.get(t):
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            tf = d[t]
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg))
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:k]]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def blend(bm25_ranked: list[dict], sims: dict[int, float], k: int = TOP_K, weight: float = 0.5) -> list[dict]:
    """Blend BM25 rank (1 for the top hit, falling linearly) with cosine similarity (0..1).
    Passages keyed by id(); ones with no lexical hit enter on similarity alone."""
    n = len(bm25_ranked)
    lex = {id(p): 1 - i / max(n, 1) for i, p in enumerate(bm25_ranked)}
    by_id = {id(p): p for p in bm25_ranked}
    scores = {}
    for pid in set(lex) | set(sims):
        scores[pid] = (1 - weight) * lex.get(pid, 0.0) + weight * max(0.0, sims.get(pid, 0.0))
    return [by_id[pid] for pid, _ in sorted(scores.items(), key=lambda x: -x[1]) if pid in by_id][:k]


async def rank_hybrid(question: str, pool: list[dict], embed_fn, k: int = TOP_K) -> list[dict]:
    """BM25, re-ranked with embeddings when an embedding model answers. Small notebooks embed
    every passage (so a zero-lexical-overlap passage can still surface); large ones re-rank only
    the lexical top candidates to bound the cost."""
    lexical = rank_passages(question, pool, k=max(k * 4, 24))
    if embed_fn is None:
        return lexical[:k]
    try:
        qv = await embed_fn(question)
    except Exception:
        qv = []
    if not qv:
        return lexical[:k]
    candidates = pool if len(pool) <= 60 else lexical
    ranked = list(lexical) + [p for p in candidates if all(p is not q for q in lexical)]
    sims: dict[int, float] = {}
    for p in candidates:
        try:
            v = await embed_fn(p["text"])
        except Exception:
            v = []
        if v:
            sims[id(p)] = _cosine(qv, v)
    if not sims:
        return lexical[:k]
    return blend(ranked, sims, k)


def build_ask_prompt(question: str, sources: list[dict]) -> str:
    numbered = "\n\n".join(f"[{i + 1}] ({s['title']})\n{s['text']}" for i, s in enumerate(sources))
    return (
        "Answer the question using ONLY the numbered sources below. Cite every claim with its source "
        "number in square brackets, like [2]. If the sources don't contain the answer, say so plainly.\n\n"
        f"Sources:\n{numbered}\n\nQuestion: {question}"
    )


def cited_numbers(answer: str, n_sources: int) -> list[int]:
    seen: list[int] = []
    for m in re.finditer(r"\[(\d+(?:\s*,\s*\d+)*)\]", answer):
        for part in m.group(1).split(","):
            i = int(part)
            if 1 <= i <= n_sources and i not in seen:
                seen.append(i)
    return seen


def build_briefing_prompt(topic: str, sources: list[dict]) -> str:
    numbered = "\n\n".join(f"[{i + 1}] ({s['title']})\n{s['text']}" for i, s in enumerate(sources))
    return (
        "Write a short two-voice audio briefing (8-14 lines) about the sources below. Two hosts: DEXTER "
        "(warm, big-picture strategist) and ANTHONY (terse operator, risks and next actions). Alternate "
        "speakers. Use only facts from the sources. Output one line per turn, each starting with "
        "'DEXTER:' or 'ANTHONY:', nothing else.\n\n"
        f"Focus: {topic or 'the most important points'}\n\nSources:\n{numbered}"
    )


def parse_script(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        m = re.match(r"\s*\**(DEXTER|ANTHONY)\**\s*:\s*(.+)", line, re.IGNORECASE)
        if m and m.group(2).strip():
            out.append({"speaker": m.group(1).upper(), "text": m.group(2).strip()})
    return out


# ---------------------------------------------------------------- storage

async def _pool_or_503():
    pool = await get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not configured — the Archive needs PostgreSQL")
    return pool


async def _notebook_sources(pool, notebook_id: str, business_id: str) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT 1 FROM notebooks WHERE id = %s AND business_id = %s", (notebook_id, business_id))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Notebook not found")
        cur = await conn.execute(
            "SELECT id, title, content FROM documents WHERE notebook_id = %s AND business_id = %s ORDER BY created_at",
            (notebook_id, business_id),
        )
        rows = await cur.fetchall()
    out: list[dict] = []
    for doc_id, title, content in rows:
        out.extend(passages(str(doc_id), title, content or ""))
    return out


class NotebookIn(BaseModel):
    title: str


class AddDocIn(BaseModel):
    document_id: str


class AskIn(BaseModel):
    question: str


class BriefingIn(BaseModel):
    topic: str = ""
    audio: bool = True


@router.get("/notebooks")
async def list_notebooks(ctx: CurrentContext = Depends(current_context)):
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT n.id, n.title, n.created_at, COUNT(d.id)
               FROM notebooks n LEFT JOIN documents d ON d.notebook_id = n.id
               WHERE n.business_id = %s GROUP BY n.id ORDER BY n.created_at DESC""",
            (ctx.business_id,),
        )
        rows = await cur.fetchall()
    return [{"id": r[0], "title": r[1], "created_at": r[2], "document_count": r[3]} for r in rows]


@router.post("/notebooks", status_code=201)
async def create_notebook(body: NotebookIn, ctx: CurrentContext = Depends(current_context)):
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Title required")
    pool = await _pool_or_503()
    nb_id = f"nb_{uuid.uuid4().hex[:10]}"
    async with pool.connection() as conn:
        await conn.execute("INSERT INTO notebooks (id, business_id, title) VALUES (%s, %s, %s)", (nb_id, ctx.business_id, body.title.strip()))
    return {"id": nb_id, "title": body.title.strip(), "document_count": 0}


@router.delete("/notebooks/{notebook_id}", status_code=204)
async def delete_notebook(notebook_id: str, ctx: CurrentContext = Depends(current_context)):
    pool = await _pool_or_503()
    async with pool.connection() as conn:
        await conn.execute("UPDATE documents SET notebook_id = NULL WHERE notebook_id = %s AND business_id = %s", (notebook_id, ctx.business_id))
        await conn.execute("DELETE FROM notebooks WHERE id = %s AND business_id = %s", (notebook_id, ctx.business_id))


@router.post("/notebooks/{notebook_id}/documents", status_code=204)
async def add_document(notebook_id: str, body: AddDocIn, ctx: CurrentContext = Depends(current_context)):
    pool = await _pool_or_503()
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT 1 FROM notebooks WHERE id = %s AND business_id = %s", (notebook_id, ctx.business_id))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Notebook not found")
        cur = await conn.execute(
            "UPDATE documents SET notebook_id = %s WHERE id::text = %s AND business_id = %s RETURNING id",
            (notebook_id, body.document_id, ctx.business_id),
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Document not found")


@router.delete("/notebooks/{notebook_id}/documents/{document_id}", status_code=204)
async def remove_document(notebook_id: str, document_id: str, ctx: CurrentContext = Depends(current_context)):
    pool = await _pool_or_503()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE documents SET notebook_id = NULL WHERE id::text = %s AND notebook_id = %s AND business_id = %s",
            (document_id, notebook_id, ctx.business_id),
        )


@router.get("/notebooks/{notebook_id}/documents")
async def notebook_documents(notebook_id: str, ctx: CurrentContext = Depends(current_context)):
    pool = await _pool_or_503()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, title, origin, char_count FROM documents WHERE notebook_id = %s AND business_id = %s ORDER BY created_at",
            (notebook_id, ctx.business_id),
        )
        rows = await cur.fetchall()
    return [{"id": str(r[0]), "title": r[1], "origin": r[2], "char_count": r[3]} for r in rows]


@router.post("/notebooks/{notebook_id}/ask")
async def ask(notebook_id: str, body: AskIn, request: Request, ctx: CurrentContext = Depends(current_context)):
    pool = await _pool_or_503()
    top = await rank_hybrid(body.question, await _notebook_sources(pool, notebook_id, ctx.business_id), getattr(request.app.state, "embed_fn", None))
    if not top:
        return {"answer": "None of this notebook's sources mention that.", "citations": [], "model": None}
    brain = request.app.state.brain
    active = await brain.describe()
    citations_all = [
        {"n": i + 1, "document_id": s["doc_id"], "title": s["title"], "passage": s["index"], "excerpt": s["text"][:400]}
        for i, s in enumerate(top)
    ]
    if not active["ready"]:
        # No model: return the best passages themselves, clearly labeled — still cited, never invented.
        return {"answer": "No model is configured, so here are the most relevant passages.", "citations": citations_all, "model": None}
    response = await brain.chat([{"role": "user", "content": build_ask_prompt(body.question, top)}], business_id=ctx.business_id, source="archive")
    answer = (response.get("message", {}).get("content") or "").strip()
    used = cited_numbers(answer, len(top))
    return {"answer": answer, "citations": [c for c in citations_all if c["n"] in used], "model": f"{active['provider']}:{active['model']}"}


@router.post("/notebooks/{notebook_id}/briefing")
async def briefing(notebook_id: str, body: BriefingIn, request: Request, ctx: CurrentContext = Depends(current_context)):
    pool = await _pool_or_503()
    sources = await _notebook_sources(pool, notebook_id, ctx.business_id)
    top = await rank_hybrid(body.topic, sources, getattr(request.app.state, "embed_fn", None)) if body.topic.strip() else sources[:TOP_K]
    if not top:
        raise HTTPException(status_code=400, detail="Add documents to this notebook first")
    brain = request.app.state.brain
    if not (await brain.describe())["ready"]:
        raise HTTPException(status_code=503, detail="No model configured — the briefing script needs one")
    response = await brain.chat([{"role": "user", "content": build_briefing_prompt(body.topic, top)}], business_id=ctx.business_id, source="archive")
    script = parse_script(response.get("message", {}).get("content") or "")
    if not script:
        raise HTTPException(status_code=502, detail="The model didn't return a two-voice script")
    audio_b64 = None
    if body.audio:
        audio_b64 = await _synthesize(script)
    return {"script": script, "audio_wav_base64": audio_b64, "voice_available": audio_b64 is not None}


async def _synthesize(script: list[dict]) -> str | None:
    """Dexter lines in the Orchestrator voice, Anthony lines in the Shadow voice → one WAV."""
    from models import Protocol
    from voice.tts import DummyTTS, get_tts

    voices = {"DEXTER": get_tts(Protocol.ORCH), "ANTHONY": get_tts(Protocol.SHADOW)}
    if any(isinstance(v, DummyTTS) for v in voices.values()):
        return None
    rate = voices["DEXTER"].sample_rate
    pcm = bytearray()
    silence = b"\x00\x00" * int(rate * 0.35)
    for turn in script:
        tts = voices[turn["speaker"]]
        if tts.sample_rate != rate:
            continue  # mismatched voice sample rates would need resampling; skip rather than distort
        pcm += await tts.synthesize(turn["text"]) + silence
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(pcm))
    return base64.b64encode(buf.getvalue()).decode()
