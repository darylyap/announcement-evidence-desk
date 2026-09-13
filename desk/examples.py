import json

from . import config

SOURCES = {s["id"]: s for s in json.loads((config.ROOT / "examples" / "sources.json").read_text())}
EXAMPLES = [
    {
        "id": "dbs-two-claims",
        "source": "dbs",
        "title": "DBS · two claims, mixed findings",
        "article": "DBS Group reported net profit of SGD 11.0 billion for the full year 2025. DBS Group reported total income of SGD 28.9 billion for the full year 2025.",
        "expected": "Supported + contradicted",
        "expected_findings": [
            {"subject": "net profit", "verdict": "supported"},
            {"subject": "total income", "verdict": "contradicted"},
        ],
        "explanation": "Two distinct test claims against one real PDF: the net-profit figure matches; total income is deliberately changed from SGD 22.9 billion to SGD 28.9 billion. Inspect and assess both findings.",
    },
    {
        "id": "dbs-supported",
        "source": "dbs",
        "title": "DBS · matching annual profit",
        "article": "DBS Group reported net profit of SGD 11.0 billion for the full year 2025.",
        "expected": "Supported",
        "explanation": "The 2025 net profit appears in the official press statement.",
    },
    {
        "id": "dbs-contradicted",
        "source": "dbs",
        "title": "DBS · an altered income figure",
        "article": "DBS Group reported total income of SGD 28.9 billion for the full year 2025.",
        "expected": "Contradicted",
        "explanation": "This test deliberately changes the reported total income from SGD 22.9 billion to SGD 28.9 billion.",
    },
    {
        "id": "sgx-supported",
        "source": "sgx",
        "title": "SGX · matching net revenue",
        "article": "Singapore Exchange reported net revenue of S$1,298.2 million for FY2025.",
        "expected": "Supported",
        "explanation": "Compare the amount and the definition of net revenue with the FY2025 release.",
    },
    {
        "id": "sgx-insufficient",
        "source": "sgx",
        "title": "SGX · an unsubstantiated acquisition",
        "article": "Singapore Exchange signed an agreement on 8 August 2025 to acquire Example Analytics Pte Ltd for S$500 million.",
        "expected": "Insufficient evidence",
        "explanation": "The acquisition claim and target company are invented for this test. The supplied results release does not establish the claim; absence is not contradiction.",
    },
]
