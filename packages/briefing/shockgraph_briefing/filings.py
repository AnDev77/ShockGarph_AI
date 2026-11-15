"""Read only allowlisted SEC submissions and primary filing documents."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Annotated, Literal

import httpx
from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator

CAMT_CIK = "0001109138"
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{CAMT_CIK}.json"
ARCHIVES = f"https://www.sec.gov/Archives/edgar/data/{int(CAMT_CIK)}"
ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")
DOCUMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.html?", re.IGNORECASE)
MAX_RESPONSE_BYTES = 4_000_000
CAMT_FORMS = frozenset({"6-K", "6-K/A", "20-F", "20-F/A"})


class FilingError(ValueError):
    """A SEC response or provenance check failed."""


@dataclass(frozen=True)
class FilingRef:
    accession: str
    form: str
    accepted_at: datetime
    document: str

    @property
    def url(self) -> str:
        return filing_url(self.accession, self.document)


def filing_url(accession: str, document: str) -> str:
    if not ACCESSION.fullmatch(accession) or not DOCUMENT.fullmatch(document):
        raise FilingError("Invalid SEC accession or document name")
    return f"{ARCHIVES}/{accession.replace('-', '')}/{document}"


class FilingCapture(BaseModel):
    symbol: Literal["CAMT"] = "CAMT"
    accession: Annotated[str, StringConstraints(pattern=r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")]
    document: str
    form: Literal["6-K", "6-K/A", "20-F", "20-F/A"]
    accepted_at: AwareDatetime
    fetched_at: AwareDatetime
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    blocks: list[Annotated[str, StringConstraints(min_length=20, max_length=1600)]] = Field(
        min_length=1, max_length=1000
    )

    @model_validator(mode="after")
    def validate_provenance(self) -> FilingCapture:
        filing_url(self.accession, self.document)
        if self.accepted_at > self.fetched_at:
            raise ValueError("The document cannot be accepted after the capture")
        return self

    @property
    def url(self) -> str:
        return filing_url(self.accession, self.document)


class _BodyParser(HTMLParser):
    _ignored = frozenset({"head", "script", "style", "noscript", "template", "svg", "ix:hidden"})
    _containers = frozenset(
        {
            "br",
            "p",
            "div",
            "li",
            "tr",
            "td",
            "th",
            "h1",
            "h2",
            "h3",
            "h4",
            "hr",
            "section",
        }
    )
    _void = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.hidden:
            if tag not in self._void:
                self.hidden.append(tag)
            return
        attributes = dict(attrs)
        style = re.sub(r"\s+", "", (attributes.get("style") or "").lower())
        if (
            tag in self._ignored
            or "hidden" in attributes
            or (attributes.get("aria-hidden") or "").lower() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        ):
            if tag not in self._void:
                self.hidden.append(tag)
        elif tag in self._containers:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.hidden:
            for i in range(len(self.hidden) - 1, -1, -1):
                if self.hidden[i] == tag:
                    del self.hidden[i:]
                    break
        elif tag in self._containers:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(re.sub(r"\s+", " ", data))


def filing_blocks(raw: bytes, *, encoding: str = "utf-8") -> list[str]:
    parser = _BodyParser()
    parser.feed(raw.decode(encoding, errors="replace"))
    parser.close()
    blocks: list[str] = []
    for line in "".join(parser.parts).splitlines():
        words = " ".join(line.split())
        while len(words) > 1600:
            split = words.rfind(" ", 800, 1600)
            end = split if split > 0 else 1600
            blocks.append(words[:end])
            words = words[end:].strip()
        if len(words) >= 20:
            blocks.append(words)
    if not blocks or len(blocks) > 1000:
        raise FilingError("Filing has no usable body or exceeds the block limit")
    return list(dict.fromkeys(blocks))


class _RecentRows(BaseModel):
    accessionNumber: list[str]
    form: list[str]
    acceptanceDateTime: list[str]
    primaryDocument: list[str]


class _Filings(BaseModel):
    recent: _RecentRows


class _Submissions(BaseModel):
    cik: int
    tickers: list[str]
    filings: _Filings


def select_camt_filing(payload: object, *, as_of: datetime) -> FilingRef | None:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise FilingError("Selection requires a timezone")
    issuer = _Submissions.model_validate(payload)
    if issuer.cik != int(CAMT_CIK) or "CAMT" not in issuer.tickers:
        raise FilingError("SEC issuer does not match CAMT")
    recent = issuer.filings.recent
    candidates: list[FilingRef] = []
    for accession, form, accepted, doc in zip(
        recent.accessionNumber,
        recent.form,
        recent.acceptanceDateTime,
        recent.primaryDocument,
        strict=True,
    ):
        if form not in CAMT_FORMS:
            continue
        date = datetime.fromisoformat(accepted)
        if date.tzinfo is None or date.utcoffset() is None:
            raise FilingError("SEC acceptance timestamp has no timezone")
        if as_of - timedelta(days=30) <= date <= as_of:
            filing_url(accession, doc)
            candidates.append(FilingRef(accession, form, date, doc))
    return max(candidates, key=lambda row: (row.accepted_at, row.accession), default=None)


def _download(
    client: httpx.Client, url: str, *, media: tuple[str, ...], user_agent: str
) -> tuple[bytes, str]:
    with client.stream(
        "GET",
        url,
        headers={"User-Agent": user_agent, "Accept": ", ".join(media)},
        follow_redirects=False,
    ) as response:
        response.raise_for_status()
        mime = response.headers.get("content-type", "").partition(";")[0].strip().lower()
        if mime not in media:
            raise FilingError("Unexpected SEC content type")
        chunks = bytearray()
        for chunk in response.iter_bytes(chunk_size=32_768):
            chunks.extend(chunk)
            if len(chunks) > MAX_RESPONSE_BYTES:
                raise FilingError("SEC response exceeds size limit")
        return bytes(chunks), response.encoding or "utf-8"


def collect_camt(
    client: httpx.Client, *, user_agent: str, as_of: datetime | None = None
) -> FilingCapture | None:
    if not user_agent.strip() or "\n" in user_agent or "\r" in user_agent:
        raise FilingError("Configure an identifiable SEC User-Agent")
    start = as_of or datetime.now(UTC)
    metadata, _ = _download(
        client,
        SUBMISSIONS_URL,
        media=("application/json",),
        user_agent=user_agent,
    )
    ref = select_camt_filing(json.loads(metadata), as_of=start)
    if ref is None:
        return None
    raw, encoding = _download(
        client,
        ref.url,
        media=("text/html", "application/xhtml+xml"),
        user_agent=user_agent,
    )
    return FilingCapture.model_validate(
        {
            "accession": ref.accession,
            "document": ref.document,
            "form": ref.form,
            "accepted_at": ref.accepted_at,
            "fetched_at": datetime.now(UTC),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "blocks": filing_blocks(raw, encoding=encoding),
        }
    )
