from __future__ import annotations

import csv
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import aiohttp


class OutreachOpsError(RuntimeError):
    pass


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s.strip())
    return re.sub(r"-{2,}", "-", s).strip("-") or "file"


def _normalize_domain(url: str) -> str:
    parsed = urlparse((url or "").strip())
    host = (parsed.netloc or parsed.path or "").strip().lower()
    host = host.split("@")[-1]
    host = host.split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    return host


def _pick_company_name(title: str, domain: str) -> str:
    t = (title or "").strip()
    if t:
        t = re.sub(r"\s+[-|:]\s+.*$", "", t).strip()
        if 2 <= len(t) <= 80:
            return t
    if domain:
        parts = domain.split(".")
        if len(parts) >= 2:
            return parts[-2].replace("-", " ").title()
        return domain
    return "Unknown"


def _extract_emails(text: str) -> list[str]:
    if not text:
        return []
    # Basic email regex. We keep it conservative to avoid false positives.
    matches = re.findall(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", text)
    seen: set[str] = set()
    out: list[str] = []
    for m in matches:
        email = m.strip().lower()
        if email in seen:
            continue
        # Exclude obvious placeholders.
        if email.endswith("@example.com"):
            continue
        seen.add(email)
        out.append(email)
    return out


def _find_contact_url(html: str, base_url: str) -> str:
    if not html:
        return ""
    # Prioritize partnership/sponsor pages, then contact/inquiry.
    patterns = [
        r'href=["\']([^"\']*(?:partner|sponsor|partnership)[^"\']*)["\']',
        r'href=["\']([^"\']*(?:contact|inquiry|sales)[^"\']*)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.I)
        if not m:
            continue
        href = (m.group(1) or "").strip()
        if not href or href.startswith("javascript:") or href.startswith("#"):
            continue
        return urljoin(base_url, href)
    return ""


def _pick_best_email(emails: list[str]) -> str:
    if not emails:
        return ""
    priority = ["partnership", "partner", "bizdev", "business", "bd", "alliances", "sales", "info"]
    for key in priority:
        for e in emails:
            if key in e:
                return e
    return emails[0]


@dataclass
class SearchResult:
    title: str
    link: str
    snippet: str


class SearchClient:
    async def search(self, query: str, limit: int) -> list[SearchResult]:
        raise NotImplementedError


class SerpApiSearchClient(SearchClient):
    def __init__(self, api_key: str, *, engine: str = "google", gl: str = "us", hl: str = "en") -> None:
        self.api_key = api_key
        self.engine = engine
        self.gl = gl
        self.hl = hl

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        url = "https://serpapi.com/search.json"
        out: list[SearchResult] = []
        start = 0
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while len(out) < limit:
                batch = min(20, limit - len(out))
                params = {
                    "engine": self.engine,
                    "q": query,
                    "api_key": self.api_key,
                    "num": batch,
                    "start": start,
                    "gl": self.gl,
                    "hl": self.hl,
                }
                async with session.get(url, params=params) as resp:
                    txt = await resp.text()
                    if resp.status >= 300:
                        raise OutreachOpsError(f"SerpAPI request failed ({resp.status}): {txt[:400]}")
                    data = await resp.json()
                organic = data.get("organic_results") or []
                if not organic:
                    break
                for item in organic:
                    out.append(
                        SearchResult(
                            title=str(item.get("title", "")),
                            link=str(item.get("link", "")),
                            snippet=str(item.get("snippet", "")),
                        )
                    )
                start += batch
        return out[:limit]


class BingWebSearchClient(SearchClient):
    def __init__(self, api_key: str, *, endpoint: str = "https://api.bing.microsoft.com/v7.0/search", mkt: str = "en-US") -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.mkt = mkt

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        out: list[SearchResult] = []
        offset = 0
        timeout = aiohttp.ClientTimeout(total=60)
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while len(out) < limit:
                batch = min(50, limit - len(out))
                params = {"q": query, "count": batch, "offset": offset, "mkt": self.mkt, "responseFilter": "WebPages"}
                async with session.get(self.endpoint, params=params, headers=headers) as resp:
                    txt = await resp.text()
                    if resp.status >= 300:
                        raise OutreachOpsError(f"Bing search request failed ({resp.status}): {txt[:400]}")
                    data = await resp.json()
                pages = ((data.get("webPages") or {}).get("value")) or []
                if not pages:
                    break
                for item in pages:
                    out.append(
                        SearchResult(
                            title=str(item.get("name", "")),
                            link=str(item.get("url", "")),
                            snippet=str(item.get("snippet", "")),
                        )
                    )
                offset += batch
        return out[:limit]


@dataclass
class OutreachLead:
    company: str
    domain: str
    website_url: str
    category: str
    contact_email: str = ""
    contact_url: str = ""
    country: str = ""
    city: str = ""
    source_query: str = ""
    source_url: str = ""
    snippet: str = ""
    notes: str = ""
    approved: str = "no"

    def to_row(self) -> dict[str, str]:
        return {
            "company": self.company,
            "domain": self.domain,
            "website_url": self.website_url,
            "category": self.category,
            "contact_email": self.contact_email,
            "contact_url": self.contact_url,
            "country": self.country,
            "city": self.city,
            "source_query": self.source_query,
            "source_url": self.source_url,
            "snippet": self.snippet,
            "notes": self.notes,
            "approved": self.approved,
        }


@dataclass
class OutreachEmailDraft:
    company: str
    domain: str
    to_email: str
    subject: str
    body: str
    approved: str = "no"
    sent_at: str = ""
    last_error: str = ""

    def to_row(self) -> dict[str, str]:
        return {
            "company": self.company,
            "domain": self.domain,
            "to_email": self.to_email,
            "subject": self.subject,
            "body": self.body,
            "approved": self.approved,
            "sent_at": self.sent_at,
            "last_error": self.last_error,
        }


@dataclass
class OutreachOpsConfig:
    state_dir: Path
    website_dir: Path
    sender_name: str
    sender_title: str
    sender_email: str
    calendar_link: str
    sponsorship_page_url: str
    cohort_date_window: str
    cohort_city: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    send_enabled: bool
    search_provider: str
    serpapi_api_key: str
    bing_api_key: str


class OutreachOps:
    def __init__(self, config: OutreachOpsConfig) -> None:
        self.config = config
        self.config.state_dir.mkdir(parents=True, exist_ok=True)

    def config_summary(self) -> str:
        search_ok = False
        provider = (self.config.search_provider or "").strip().lower()
        if provider == "serpapi":
            search_ok = bool(self.config.serpapi_api_key)
        elif provider == "bing":
            search_ok = bool(self.config.bing_api_key)

        smtp_ok = bool(self.config.smtp_host and self.config.smtp_port and self.config.smtp_user and self.config.smtp_password)
        return (
            "Outreach config\n"
            f"state_dir={self.config.state_dir}\n"
            f"website_dir={self.config.website_dir}\n"
            f"sender_email={self.config.sender_email or 'missing'}\n"
            f"sponsorship_page_url={self.config.sponsorship_page_url or 'missing'}\n"
            f"calendar_link={self.config.calendar_link or 'missing'}\n"
            f"cohort_city={self.config.cohort_city or 'missing'}\n"
            f"cohort_date_window={self.config.cohort_date_window or 'missing'}\n"
            f"search_provider={provider or 'missing'} (configured={'yes' if search_ok else 'no'})\n"
            f"smtp_configured={'yes' if smtp_ok else 'no'} send_enabled={'yes' if self.config.send_enabled else 'no'}"
        )

    def _search_client(self) -> SearchClient:
        provider = (self.config.search_provider or "").strip().lower()
        if provider == "serpapi":
            if not self.config.serpapi_api_key:
                raise OutreachOpsError("SERPAPI_API_KEY is missing.")
            return SerpApiSearchClient(self.config.serpapi_api_key)
        if provider == "bing":
            if not self.config.bing_api_key:
                raise OutreachOpsError("BING_SEARCH_API_KEY is missing.")
            return BingWebSearchClient(self.config.bing_api_key)
        raise OutreachOpsError("SEARCH_PROVIDER must be set to `serpapi` or `bing`.")

    async def _fetch_text(self, session: aiohttp.ClientSession, url: str) -> str:
        if not url:
            return ""
        if not url.startswith("http://") and not url.startswith("https://"):
            return ""
        try:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status >= 400:
                    return ""
                # Avoid giant payloads.
                raw = await resp.content.read(600_000)
                return raw.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    async def _enrich_contact(self, leads: list[OutreachLead]) -> list[OutreachLead]:
        timeout = aiohttp.ClientTimeout(total=25)
        connector = aiohttp.TCPConnector(limit=8)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers={"User-Agent": "KirokuOutreachBot/1.0"}) as session:
            for lead in leads:
                if lead.contact_email and lead.contact_url:
                    continue
                root = f"https://{lead.domain}" if lead.domain else lead.website_url
                html = await self._fetch_text(session, root)
                if not html and lead.website_url and lead.website_url != root:
                    html = await self._fetch_text(session, lead.website_url)
                emails = _extract_emails(html)
                lead.contact_email = lead.contact_email or _pick_best_email(emails)
                lead.contact_url = lead.contact_url or _find_contact_url(html, root)
        return leads

    async def generate_housing_leads(self, count: int, *, city: str = "Tokyo", country: str = "Japan") -> Path:
        if count <= 0:
            raise OutreachOpsError("count must be > 0")

        search = self._search_client()

        queries = [
            f"{city} hotel corporate partnership",
            f"{city} serviced apartment corporate rates",
            f"{city} coliving spaces",
            f"{city} business hotel chain",
            f"{city} relocation services",
            f"{country} hotel group partnerships",
            f"{country} short stay apartments for business",
            f"{country} travel management company partnerships",
        ]

        leads: list[OutreachLead] = []
        seen_domains: set[str] = set()

        for q in queries:
            results = await search.search(q, limit=25)
            for r in results:
                domain = _normalize_domain(r.link)
                if not domain or domain in seen_domains:
                    continue
                seen_domains.add(domain)

                company = _pick_company_name(r.title, domain)
                # Prefer domain root for canonical website_url.
                website_url = f"https://{domain}"
                leads.append(
                    OutreachLead(
                        company=company,
                        domain=domain,
                        website_url=website_url,
                        category="housing",
                        country=country,
                        city=city,
                        source_query=q,
                        source_url=r.link,
                        snippet=r.snippet[:240],
                        approved="no",
                    )
                )
                if len(leads) >= count:
                    break
            if len(leads) >= count:
                break

        if not leads:
            raise OutreachOpsError("No leads found from search results.")

        # Best-effort contact enrichment (emails/contact pages).
        await self._enrich_contact(leads)

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = self.config.state_dir / f"leads-housing-{_safe_filename(city)}-{ts}.csv"
        self._write_csv(out_path, [l.to_row() for l in leads])
        return out_path

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            raise OutreachOpsError(f"Failed reading {path}: {exc}") from exc

    def _load_housing_template(self) -> tuple[str, str]:
        # For now, load from the shared outreach pack if present.
        pack = self.config.website_dir / "sponsorship_first_contact_emails.md"
        if not pack.exists():
            raise OutreachOpsError("Missing template file: website/sponsorship_first_contact_emails.md")

        text = self._read_text(pack)
        m = re.search(r"(?ms)^## Template D: Housing Partner.*?^Subject:\\s*(.*?)\\n\\n(.*?)(?=^##\\s)", text)
        if not m:
            raise OutreachOpsError(
                "Housing template not found in sponsorship_first_contact_emails.md. "
                "Expected a section header like `## Template D: Housing Partner`."
            )
        subject = (m.group(1) or "").strip()
        body = (m.group(2) or "").strip()
        return subject, body

    def _substitute(self, text: str, values: dict[str, str]) -> str:
        def repl(match: re.Match[str]) -> str:
            key = (match.group(1) or "").strip()
            return str(values.get(key, "") or "")

        return re.sub(r"\\{\\{\\s*([a-zA-Z0-9_]+)\\s*\\}\\}", repl, text)

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                return [{k: (v or "").strip() for k, v in row.items()} for row in reader]
        except Exception as exc:
            raise OutreachOpsError(f"Failed reading CSV {path}: {exc}") from exc

    def _write_csv(self, path: Path, rows: Iterable[dict[str, str]]) -> None:
        rows_list = list(rows)
        if not rows_list:
            raise OutreachOpsError("Cannot write empty CSV.")
        fieldnames: list[str] = []
        for row in rows_list:
            for k in row.keys():
                if k not in fieldnames:
                    fieldnames.append(k)

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows_list:
                writer.writerow(row)

    def draft_housing_emails(self, leads_csv: Path) -> Path:
        leads = self._read_csv(leads_csv)
        subject_t, body_t = self._load_housing_template()

        drafts: list[OutreachEmailDraft] = []
        for lead in leads:
            to_email = lead.get("contact_email") or ""
            if not to_email:
                continue
            values = {
                "first_name": "there",
                "title": "",
                "company": lead.get("company") or "",
                "track": "Housing",
                "sender_name": self.config.sender_name,
                "sender_title": self.config.sender_title,
                "sender_email": self.config.sender_email,
                "calendar_link": self.config.calendar_link,
                "sponsorship_page_url": self.config.sponsorship_page_url,
                "cohort_date_window": self.config.cohort_date_window,
                "cohort_city": self.config.cohort_city,
            }
            subject = self._substitute(subject_t, values).strip()
            body = self._substitute(body_t, values).strip()
            drafts.append(
                OutreachEmailDraft(
                    company=lead.get("company") or "",
                    domain=lead.get("domain") or "",
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    approved="no",
                )
            )

        if not drafts:
            raise OutreachOpsError("No draftable leads found (missing contact_email).")

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = self.config.state_dir / f"outbox-housing-{ts}.csv"
        self._write_csv(out_path, [d.to_row() for d in drafts])
        return out_path

    def _smtp_send(self, to_email: str, subject: str, body: str) -> None:
        if not self.config.send_enabled:
            raise OutreachOpsError("Sending is disabled (set OUTREACH_SEND_ENABLED=true).")
        if not (self.config.smtp_host and self.config.smtp_port and self.config.smtp_user and self.config.smtp_password):
            raise OutreachOpsError("SMTP is not configured (SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD).")

        msg = EmailMessage()
        msg["From"] = self.config.sender_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Reply-To"] = self.config.sender_email
        msg.set_content(body)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, context=context) as server:
            server.login(self.config.smtp_user, self.config.smtp_password)
            server.send_message(msg)

    def send_outbox(self, outbox_csv: Path, *, limit: int = 10, dry_run: bool = True, approved_only: bool = True) -> tuple[int, int, Path]:
        rows = self._read_csv(outbox_csv)
        updated: list[dict[str, str]] = []
        attempted = 0
        sent = 0

        for row in rows:
            row = dict(row)
            already_sent = bool(row.get("sent_at"))
            approved = (row.get("approved") or "").strip().lower() == "yes"
            if already_sent:
                updated.append(row)
                continue
            if approved_only and not approved:
                updated.append(row)
                continue
            if attempted >= limit:
                updated.append(row)
                continue

            attempted += 1
            try:
                if not dry_run:
                    self._smtp_send(row.get("to_email", ""), row.get("subject", ""), row.get("body", ""))
                row["sent_at"] = _iso_now() if not dry_run else ""
                row["last_error"] = ""
                sent += 0 if dry_run else 1
            except Exception as exc:
                row["last_error"] = str(exc)[:500]

            updated.append(row)

        self._write_csv(outbox_csv, updated)
        return attempted, sent, outbox_csv

