import io
import ipaddress
import socket
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree
from zipfile import ZipFile

import httpx
from bs4 import BeautifulSoup

from . import config
from .documents import extract_pdf, normalized

ALLOWED_DOMAINS = ("sgx.com", "dbs.com", "singtel.com", "ocbc.com", "uobgroup.com")


def validate_link(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("Use a public HTTPS link without login details.")
    if not any(host == domain or host.endswith("." + domain) for domain in ALLOWED_DOMAINS):
        raise ValueError(
            "Link imports support SGX, DBS, Singtel, OCBC and UOB official sites. Download other sources and upload the file."
        )
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("This link does not resolve to a public source.")
    return url


def parse_file(raw, filename, mime=""):
    if len(raw) > config.MAX_UPLOAD:
        raise ValueError("Maximum file size is 4 MB.")
    suffix = Path(filename).suffix.lower()
    if raw.startswith(b"%PDF-"):
        return extract_pdf(raw), "pdf", "application/pdf"
    if suffix == ".docx":
        try:
            with ZipFile(io.BytesIO(raw)) as z:
                if sum(i.file_size for i in z.infolist()) > 10_000_000:
                    raise ValueError("DOCX expands beyond the supported size.")
                root = ElementTree.fromstring(z.read("word/document.xml"))
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            text = "\n".join("".join(p.itertext()) for p in root.iter(ns + "p"))
        except Exception as exc:
            raise ValueError(
                "Cannot read this DOCX. Upload an unlocked document or paste its text."
            ) from exc
        kind, mime = (
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    elif suffix in (".txt", ".md"):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text files must use UTF-8 encoding.") from exc
        kind, mime = "text", "text/plain"
    elif "text/html" in mime:
        soup = BeautifulSoup(raw, "html.parser")
        for element in soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "noscript",
                "input",
                "button",
                "select",
                "textarea",
            ]
        ):
            element.decompose()
        body = soup.find("article") or soup.find("main") or soup.body or soup
        text = body.get_text(" ", strip=True)
        kind = "html"
    else:
        raise ValueError(
            "Supported files: PDF, DOCX, TXT and MD. Legacy DOC, images and scanned PDFs are not supported."
        )
    if not 80 <= len(normalized(text)) <= 100000:
        raise ValueError(
            "Source needs 80–100,000 readable characters. Use a relevant excerpt if it is too long."
        )
    return [{"page": 1, "text": text}], kind, mime


def fetch_link(url):
    start = time.monotonic()
    with httpx.Client(
        timeout=15,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "AnnouncementEvidenceDesk/1.0 (public document retrieval)"},
    ) as client:
        for _ in range(4):
            validate_link(url)
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                data = bytearray()
                for piece in response.iter_bytes():
                    data.extend(piece)
                    if len(data) > config.MAX_UPLOAD:
                        raise ValueError(
                            "Source exceeds 4 MB. Download and select a smaller document."
                        )
                    if time.monotonic() - start > 25:
                        raise ValueError(
                            "Source took too long to download. Upload it directly instead."
                        )
                mime = response.headers.get("content-type", "").split(";")[0]
                raw = bytes(data)
                filename = Path(urlsplit(url).path).name or "source.html"
                pages, kind, mime = parse_file(raw, filename, mime)
                title = filename
                attachments = []
                if kind == "html":
                    soup = BeautifulSoup(raw, "html.parser")
                    if soup.title:
                        title = soup.title.get_text(" ", strip=True)
                    for a in soup.find_all("a", href=True):
                        link = urljoin(url, a["href"])
                        if any(
                            x in link.lower() for x in (".pdf", "fileopen", "/static-files/")
                        ) and link not in [x["url"] for x in attachments]:
                            attachments.append(
                                {
                                    "title": a.get_text(" ", strip=True) or "Linked document",
                                    "url": link,
                                }
                            )
                return dict(
                    raw=raw,
                    filename=filename[:200],
                    pages=pages,
                    kind=kind,
                    mime=mime,
                    source_url=url,
                    title=title[:300],
                    attachments=attachments[:12],
                )
    raise ValueError("Too many redirects. Open the source and upload the document directly.")
