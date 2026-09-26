"""File / URL ingest (docs/BACKEND_TASKS.md P5) — first hook of the Phase 6 Archive.

Upload a PDF/text file or hand it a URL; the text gets extracted, embedded (when an
embedding provider is available — see memory/embeddings.py), and stored in `documents`
for semantic search. `chat.py` folds the top matches into a turn's context alongside
conversation recall, so ingested material actually becomes usable memory, not just a
write-only store.

Scoped per business (docs/PHASE_3_4_PLAN.md §1) — otherwise one business's ingested
files would leak into another's chat recall and file list.

URL fetch is a plain httpx GET + HTML-tag strip, not `tools/browser.py`'s Playwright
path — that keeps ingestion working without an extra install (Playwright is optional
elsewhere in this backend too); it won't render JS-heavy pages, which is an accepted
trade-off for "always available."
"""
from __future__ import annotations

import io
import re
import uuid
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel

from db.connection import get_pool
from auth import CurrentContext, current_context

log = logging.getLogger("dexter.files")

router = APIRouter(prefix="/api/files", tags=["files"])

DB_UNAVAILABLE = "Database not configured — install PostgreSQL (see Settings) to ingest files."
MAX_BYTES = 15 * 1024 * 1024
MAX_CHARS = 40_000  # keeps a single document from blowing out later context windows
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".log"}


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise HTTPException(status_code=501, detail="PDF support not installed — `pip install pypdf`")
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class DocumentStore:
    async def save(self, source: str, title: str, origin: str, content: str, embed_fn, business_id: str) -> dict:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError(DB_UNAVAILABLE)
        clipped = content[:MAX_CHARS]
        doc_id = str(uuid.uuid4())
        vec = await embed_fn(clipped[:4000])  # embed a representative slice, not the whole doc
        async with pool.connection() as conn:
            if vec:
                await conn.execute(
                    """INSERT INTO documents (id, source, title, origin, content, char_count, embedding, business_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)""",
                    (doc_id, source, title, origin, clipped, len(clipped), str(vec), business_id),
                )
            else:
                await conn.execute(
                    """INSERT INTO documents (id, source, title, origin, content, char_count, business_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (doc_id, source, title, origin, clipped, len(clipped), business_id),
                )
        return await self.get(doc_id, business_id)

    async def get(self, doc_id: str, business_id: str) -> dict | None:
        pool = await get_pool()
        if pool is None:
            return None
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, source, title, origin, char_count, created_at FROM documents WHERE id = %s AND business_id = %s",
                (doc_id, business_id),
            )
            row = await cur.fetchone()
        return _row(row) if row else None

    async def list(self, business_id: str, limit: int = 50) -> list[dict]:
        pool = await get_pool()
        if pool is None:
            return []
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, source, title, origin, char_count, created_at FROM documents WHERE business_id = %s ORDER BY created_at DESC LIMIT %s",
                (business_id, limit),
            )
            rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def delete(self, doc_id: str, business_id: str) -> bool:
        pool = await get_pool()
        if pool is None:
            raise RuntimeError(DB_UNAVAILABLE)
        async with pool.connection() as conn:
            cur = await conn.execute("DELETE FROM documents WHERE id = %s AND business_id = %s", (doc_id, business_id))
            return cur.rowcount > 0

    async def search(self, query: str, embed_fn, business_id: str, limit: int = 3) -> list[dict]:
        vec = await embed_fn(query)
        if not vec:
            return []
        pool = await get_pool()
        if pool is None:
            return []
        async with pool.connection() as conn:
            cur = await conn.execute(
                """SELECT id, title, content, 1 - (embedding <=> %s::vector) AS similarity
                   FROM documents WHERE embedding IS NOT NULL AND business_id = %s
                   ORDER BY embedding <=> %s::vector LIMIT %s""",
                (str(vec), business_id, str(vec), limit),
            )
            rows = await cur.fetchall()
        return [{"id": str(r[0]), "title": r[1], "content": r[2], "similarity": float(r[3])} for r in rows]


def _row(r) -> dict:
    return {
        "id": str(r[0]), "source": r[1], "title": r[2], "origin": r[3],
        "char_count": r[4], "created_at": r[5],
    }


document_store = DocumentStore()


@router.post("/upload", status_code=201)
async def upload_file(request: Request, file: UploadFile, ctx: CurrentContext = Depends(current_context)):
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File over the {MAX_BYTES // (1024 * 1024)} MB limit")

    name = file.filename or "upload"
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext == ".pdf":
        text = _extract_pdf(data)
    elif ext in TEXT_EXTENSIONS or not ext:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=415, detail=f"Could not decode \"{name}\" as text")
    else:
        raise HTTPException(status_code=415, detail=f"Unsupported file type \"{ext}\" — pdf, txt, md, csv")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail=f"No extractable text in \"{name}\" (scanned/image-only?)")

    try:
        doc = await document_store.save("upload", name, name, text, request.app.state.embed_fn, ctx.business_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return doc


THIN_PAGE_CHARS = 400  # less text than this from raw HTML usually means a JS-rendered page


async def _render_with_browser(url: str) -> str | None:
    """Render a JS-heavy page with Playwright when it's installed; None when it isn't or fails."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=20000, wait_until="networkidle")
                return (await page.locator("body").inner_text(timeout=5000)).strip()
            finally:
                await browser.close()
    except Exception as e:
        log.info("Browser render failed for %s: %s", url, e)
        return None


class UrlBody(BaseModel):
    url: str


@router.post("/url", status_code=201)
async def ingest_url(request: Request, body: UrlBody, ctx: CurrentContext = Depends(current_context)):
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(body.url, headers={"User-Agent": "Dexter/0.1 (+file ingest)"})
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=422, detail=f"Could not fetch {body.url}: {e}")

    content_type = resp.headers.get("content-type", "")
    text = _strip_html(resp.text) if "html" in content_type else resp.text.strip()
    if not text and "html" not in content_type:
        raise HTTPException(status_code=422, detail=f"No extractable text at {body.url}")

    title_match = re.search(r"(?is)<title>(.*?)</title>", resp.text) if "html" in content_type else None
    title = title_match.group(1).strip() if title_match else body.url

    if "html" in content_type and len(text) < THIN_PAGE_CHARS:
        rendered = await _render_with_browser(body.url)
        if rendered and len(rendered) > len(text):
            text = rendered
    if not text:
        raise HTTPException(status_code=422, detail=f"No extractable text at {body.url}")

    try:
        doc = await document_store.save("url", title, body.url, text, request.app.state.embed_fn, ctx.business_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return doc


@router.get("")
async def list_files(ctx: CurrentContext = Depends(current_context)):
    return await document_store.list(ctx.business_id)


@router.delete("/{doc_id}", status_code=204)
async def delete_file(doc_id: str, ctx: CurrentContext = Depends(current_context)):
    try:
        deleted = await document_store.delete(doc_id, ctx.business_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
