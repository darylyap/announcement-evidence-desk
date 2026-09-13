import hashlib
import io
import math
import re
from collections import Counter

from pypdf import PdfReader


def normalized(text):
    return " ".join(text.split())


def extract_pdf(data: bytes) -> list[dict]:
    if not data.startswith(b"%PDF-"):
        raise ValueError("Upload a PDF file, or paste its text instead.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported. Upload an unlocked copy.")
        if len(reader.pages) > 40:
            raise ValueError("Limit each PDF to 40 pages. Select the relevant sections.")
        pages = [
            {"page": i + 1, "text": p.extract_text() or ""} for i, p in enumerate(reader.pages)
        ]
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("Could not read this PDF. Try an unlocked, text-based PDF.") from e
    if len(normalized(" ".join(p["text"] for p in pages))) < 80:
        raise ValueError(
            "No usable text found. Scanned PDFs need OCR first; paste the extracted text."
        )
    if sum(len(p["text"]) for p in pages) > 100000:
        raise ValueError("Too much text. Limit each document to 100,000 characters.")
    return pages


def chunks(documents):
    result = []
    for d in documents:
        for page in d["pages"]:
            text = normalized(page["text"])
            start = 0
            while start < len(text):
                end = min(start + 1100, len(text))
                if end < len(text):
                    boundary = text.rfind(" ", start + 700, end)
                    if boundary > start:
                        end = boundary
                fragment = text[start:end]
                result.append(
                    {
                        "chunk_id": f"{d['id']}:p{page['page']}:{start}",
                        "document_id": d["id"],
                        "title": d["title"],
                        "page": page["page"],
                        "text": fragment,
                        "source_url": d["source_url"],
                        "published_date": d["published_date"],
                    }
                )
                if end == len(text):
                    break
                start = end - 150
    return result


STOP = set(
    "the a an is was were are to of in and for on by with as at from this that it its has have had".split()
)


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


def retrieve(query, corpus, k=3):
    """BM25 over full passages. Selection does not assert semantic support."""
    if not corpus:
        return []
    counts = [Counter(tokens(c["text"])) for c in corpus]
    lengths = [sum(c.values()) for c in counts]
    avg = sum(lengths) / len(lengths) or 1
    scores = [0.0] * len(corpus)
    for term in set(tokens(query)):
        df = sum(term in c for c in counts)
        idf = math.log(1 + (len(counts) - df + 0.5) / (df + 0.5))
        for i, cnt in enumerate(counts):
            tf = cnt[term]
            if tf:
                scores[i] += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * lengths[i] / avg))
    return [
        {**corpus[i], "retrieval_score": round(scores[i], 4)}
        for i in sorted(range(len(scores)), key=lambda i: (-scores[i], corpus[i]["chunk_id"]))[:k]
        if scores[i] > 0
    ]


def digest(pages):
    return hashlib.sha256("\n".join(p["text"] for p in pages).encode()).hexdigest()
