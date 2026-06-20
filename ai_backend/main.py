from __future__ import annotations

import argparse
import json
import math
import re
import zlib
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

BASE_DIR = (Path(__file__).resolve().parent.parent / "uploads").resolve()
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]*")
MAX_FALLBACK_TEXT_CHARS = 300_000
MAX_FALLBACK_STRINGS = 8_000
STREAM_SAMPLE_BYTES = 65_536
MIN_TEXT_STREAM_PRINTABLE_RATIO = 0.70

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am",
    "an", "and", "any", "are", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can",
    "could", "did", "do", "does", "doing", "down", "during", "each", "few",
    "for", "from", "further", "had", "has", "have", "having", "he", "her",
    "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "itself", "just", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
    "once", "only", "or", "other", "our", "ours", "ourselves", "out",
    "over", "own", "same", "she", "should", "so", "some", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "you", "your",
    "yours", "yourself", "yourselves",
    "code", "course", "description", "end", "figure", "item", "lab", "name",
    "page", "part", "quantity", "report", "submitted", "table", "type",
    "types", "use", "used", "using",
}

SECTION_HEADINGS = {
    "abstract": "Abstract",
    "objectives": "Objectives",
    "materials and equipment": "Materials and Equipment",
    "materials": "Materials and Equipment",
    "equipment": "Materials and Equipment",
    "theory": "Theory",
    "procedure": "Procedure",
    "results and observations": "Results and Observations",
    "result and observation": "Results and Observations",
    "results": "Results and Observations",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
}

ACADEMIC_TERMS = {
    "algorithm", "analysis", "architecture", "calculation", "classification",
    "configuration", "connectivity", "definition", "demonstrate", "diagram",
    "equation", "evaluation", "experiment", "framework", "implementation",
    "method", "objective", "observation", "procedure", "protocol", "result",
    "standard", "structure", "theory", "troubleshooting", "validation",
}

PRACTICE_TERMS = {
    "command", "configure", "construct", "create", "crimp", "demonstrate",
    "draw", "experiment", "install", "observe", "practice", "solve", "test",
    "verify",
}


def resolve_upload_path(raw_path: str) -> Path:
    filename = Path(str(raw_path).replace("\\", "/")).name

    if not filename or filename in {".", ".."}:
        raise ValueError("Invalid file name")

    candidate = (BASE_DIR / filename).resolve()

    try:
        candidate.relative_to(BASE_DIR)
    except ValueError as exc:
        raise ValueError("Invalid file path") from exc

    if candidate.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported")

    if not candidate.exists():
        raise FileNotFoundError("File not found")

    return candidate


def clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def normalize_document_text(text: str) -> str:
    replacements = {
        r"\bStraight\s+Through\b": "Straight-Through",
        r"\bpin\s+pin\b": "pin-to-pin",
        r"\bend\s+end\b": "end-to-end",
        r"\bPC\s+PC\b": "PC-to-PC",
        r"\bPC\s+Switch\b": "PC-to-Switch",
        r"\bRJ\s+45\b": "RJ-45",
        r"\bT568A\s+T568B\b": "T568A/T568B",
        r"\bAuto\s+MDIX\b": "Auto-MDIX",
        r"\bvs\.\s*": "versus ",
        r"\bhands\s+on\b": "hands-on",
        r"\bLayer\s+3\b": "Layer 3",
        r"\bLayer\s+2\b": "Layer 2",
        r"\bne\s+twork\b": "network",
        r"\bnet\s+work\b": "network",
        r"\bfunctionali\s+ty\b": "functionality",
        r"\bins\s+ert\b": "insert",
        r"\bfr\s+om\b": "from",
        r"\ba\s+t\b": "at",
        r"\bth\s+at\b": "that",
        r"\bsu\s+ccessfully\b": "successfully",
        r"\btwis\s+ted\b": "twisted",
    }

    text = clean_text(text)

    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.I)

    lines = [line.strip(" -\t") for line in text.splitlines()]
    rebuilt: list[str] = []

    for line in lines:
        if not line:
            if rebuilt and rebuilt[-1] != "":
                rebuilt.append("")
            continue

        heading_key = normalize_heading(line)

        if heading_key in SECTION_HEADINGS:
            if rebuilt and rebuilt[-1] != "":
                rebuilt.append("")
            rebuilt.append(SECTION_HEADINGS[heading_key])
            rebuilt.append("")
            continue

        if (
            rebuilt
            and rebuilt[-1]
            and rebuilt[-1] not in SECTION_HEADINGS.values()
            and not re.search(r"[.!?:;)]$", rebuilt[-1])
            and not re.match(r"^(Item|Quantity|Description|Part\s+\d+|Scenario\s+[A-Z])", line, re.I)
        ):
            rebuilt[-1] = rebuilt[-1] + " " + line
        else:
            rebuilt.append(line)

    text = "\n".join(rebuilt)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_heading(value: str) -> str:
    value = re.sub(r"[^A-Za-z& ]+", "", value).replace("&", "and")
    return re.sub(r"\s+", " ", value).strip().lower()


def extract_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"overview": []}
    current = "overview"

    for raw_line in normalize_document_text(text).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        heading_key = normalize_heading(line)

        if heading_key in SECTION_HEADINGS:
            current = SECTION_HEADINGS[heading_key].lower()
            sections.setdefault(current, [])
            continue

        sections.setdefault(current, []).append(line)

    return {
        key: clean_text("\n".join(value))
        for key, value in sections.items()
        if clean_text("\n".join(value))
    }


def first_available_section(sections: dict[str, str], names: Iterable[str]) -> str:
    for name in names:
        value = sections.get(name.lower())

        if value:
            return value

    return ""


def document_title(sections: dict[str, str], fallback_terms: list[str]) -> str:
    overview = sections.get("overview", "")
    compact = re.sub(r"\s+", " ", overview)
    course_match = re.search(r"Course Name:\s*(.*?)\s+Course Code:", compact, re.I)

    if course_match and course_match.group(1).strip():
        return course_match.group(1).strip()

    lines = [line.strip() for line in overview.splitlines() if line.strip()]

    for line in lines:
        if 3 <= len(line.split()) <= 10 and not re.search(r"submitted|course code|id:", line, re.I):
            return line

    if fallback_terms:
        return "Study notes on " + ", ".join(fallback_terms[:3])

    return "Uploaded study PDF"


def best_sentences(text: str, count: int, focus_terms: Iterable[str] | None = None) -> list[str]:
    return [
        trim_words(sentence, 36)
        for sentence in select_sentences(split_sentences(text), max_count=count, focus_terms=focus_terms)
        if sentence
    ]


def section_bullets(sections: dict[str, str], key: str, count: int = 3) -> list[str]:
    return best_sentences(sections.get(key, ""), count)


def build_recall_questions(sections: dict[str, str], terms: list[str]) -> list[str]:
    questions = []

    if sections.get("objectives"):
        questions.append("What are the main objectives, and why does each one matter?")

    if sections.get("procedure"):
        questions.append("Can you explain the procedure from memory in the correct order?")

    if sections.get("results and observations"):
        questions.append("What result proves the task worked, and what evidence supports it?")

    if sections.get("conclusion"):
        questions.append("What final lesson or principle should you remember?")

    for term in terms[:2]:
        questions.append(f"How would you explain {term} in simple words?")

    return questions[:5]


def add_unique_question(
    questions: list[dict[str, str]],
    seen: set[str],
    question: str,
    kind: str,
) -> None:
    normalized = re.sub(r"\s+", " ", question.strip()).lower()

    if not normalized or normalized in seen:
        return

    seen.add(normalized)
    questions.append({"question": question.strip(), "type": kind})


def build_suggested_questions(text: str, page_count: int) -> list[dict[str, str]]:
    text = normalize_document_text(text)
    sections = extract_sections(text)
    terms = top_terms(text, 10)
    questions: list[dict[str, str]] = []
    seen: set[str] = set()

    add_unique_question(questions, seen, "What is this PDF mainly about?", "Overview")

    if sections.get("objectives"):
        add_unique_question(questions, seen, "What are the main objectives and why are they important?", "Objectives")

    if sections.get("theory"):
        add_unique_question(questions, seen, "Explain the main theory or background in simple words.", "Concept")

    if sections.get("procedure"):
        add_unique_question(questions, seen, "Explain the procedure step by step.", "Procedure")

    if sections.get("materials and equipment"):
        add_unique_question(questions, seen, "Which tools, materials, or equipment are required?", "Materials")

    if sections.get("results and observations"):
        add_unique_question(questions, seen, "What are the key results and observations?", "Results")

    if sections.get("discussion"):
        add_unique_question(questions, seen, "Why do the results matter? Give the reasoning.", "Reasoning")

    if sections.get("conclusion"):
        add_unique_question(questions, seen, "What is the conclusion and what should I remember?", "Conclusion")

    add_unique_question(questions, seen, "What should I revise first for an exam, lab viva, or class test?", "Study")
    add_unique_question(questions, seen, "Make a short quiz from this PDF.", "Quiz")

    for term in terms[:5]:
        add_unique_question(questions, seen, f"Explain {term} in simple words.", "Concept")

    if page_count > 2:
        add_unique_question(questions, seen, "Give me a page-by-page study strategy for this PDF.", "Study")

    return questions[:12]


def build_quiz_answer(text: str, pages: list[dict[str, object]]) -> str:
    text = normalize_document_text(text)
    sections = extract_sections(text)
    terms = top_terms(text, 8)
    page_count = page_count_from_pages(pages)
    recall_questions = build_recall_questions(sections, terms)
    suggested = [item["question"] for item in build_suggested_questions(text, page_count)]
    quiz_questions: list[str] = []
    seen: set[str] = set()

    for question in recall_questions + suggested:
        normalized = question.lower()
        if normalized not in seen:
            seen.add(normalized)
            quiz_questions.append(question)

    if not quiz_questions:
        quiz_questions = [
            "What is the main topic of this PDF?",
            "Which idea seems most important for an exam?",
            "What evidence or example supports the main idea?",
            "What should you revise again after reading?",
        ]

    answer_lines = ["Quick quiz:", *[f"{index}. {question}" for index, question in enumerate(quiz_questions[:8], 1)]]
    answer_lines.extend(["", "Answer guide:"])

    guide_sources = [
        ("Objectives", sections.get("objectives", "")),
        ("Theory", sections.get("theory", "")),
        ("Procedure", sections.get("procedure", "")),
        ("Results", sections.get("results and observations", "")),
        ("Conclusion", sections.get("conclusion", "")),
    ]

    for label, content in guide_sources:
        bullets = best_sentences(content, 2, terms)
        if bullets:
            answer_lines.append(f"- {label}: " + " ".join(bullets))

    if len(answer_lines) <= 11:
        fallback = best_sentences(text, 4, terms)
        answer_lines.extend("- " + sentence for sentence in fallback)

    return "\n".join(answer_lines)


def build_reasoning_answer(question: str, pages: list[dict[str, object]], text: str) -> str:
    question_lower = question.lower()
    chunks = rank_chunks(question, make_chunks(pages))
    useful_chunks = [chunk for chunk in chunks[:5] if float(chunk["score"]) > 0.1]

    if not useful_chunks:
        return ""

    focus_terms = tokenize(question)
    evidence_text = " ".join(str(chunk["text"]) for chunk in useful_chunks)
    evidence = select_sentences(split_sentences(evidence_text), max_count=5, focus_terms=focus_terms)

    if not evidence:
        return ""

    if any(term in question_lower for term in ["compare", "difference", "versus", " vs "]):
        heading = "Comparison:"
    elif any(term in question_lower for term in ["why", "reason", "logic", "justify"]):
        heading = "Reasoning:"
    else:
        heading = "Explanation:"

    pages_found = sorted({int(chunk["page"]) for chunk in useful_chunks})
    page_text = ", ".join(str(page) for page in pages_found)
    lines = [heading]
    lines.extend("- " + trim_words(sentence, 36) for sentence in evidence[:5])
    lines.extend(["", "Best takeaway: " + trim_words(" ".join(evidence[:2]), 44)])
    lines.append(f"Source page{'s' if len(pages_found) != 1 else ''}: {page_text}")

    return "\n".join(lines)


def analyze_learning_features(text: str, page_count: int) -> dict[str, object]:
    text = normalize_document_text(text)
    sections = extract_sections(text)
    words = WORD_RE.findall(text)
    word_count = len(words)
    sentences = split_sentences(text)
    sentence_count = max(1, len(sentences))
    tokens = tokenize(text, keep_numbers=False)
    unique_terms = set(tokens)
    academic_hits = len(unique_terms & ACADEMIC_TERMS)
    practice_hits = len(unique_terms & PRACTICE_TERMS)
    number_density = len(re.findall(r"\b\d+(?:\.\d+)?\b", text)) / max(1, word_count)
    symbol_density = len(re.findall(r"[=<>/%]|->|:", text)) / max(1, word_count)
    section_count = max(1, len([key for key in sections if key != "overview"]))
    avg_sentence_length = word_count / sentence_count
    complex_ratio = sum(1 for word in words if len(word) >= 9) / max(1, word_count)
    table_like_lines = len(re.findall(r"\b(Item|Quantity|Description|Table|Figure|Result|Observation)\b", text, re.I))

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_sentence_length": avg_sentence_length,
        "complex_ratio": complex_ratio,
        "unique_ratio": len(unique_terms) / max(1, len(tokens)),
        "academic_hits": academic_hits,
        "practice_hits": practice_hits,
        "number_density": number_density,
        "symbol_density": symbol_density,
        "section_count": section_count,
        "table_like_lines": table_like_lines,
        "page_count": max(1, page_count),
        "sections": sections,
    }


def estimate_study_minutes(features: dict[str, object], difficulty: str) -> int:
    word_count = int(features["word_count"])
    page_count = int(features["page_count"])
    academic_hits = int(features["academic_hits"])
    practice_hits = int(features["practice_hits"])
    number_density = float(features["number_density"])
    symbol_density = float(features["symbol_density"])
    table_like_lines = int(features["table_like_lines"])

    reading_minutes = word_count / {"Easy": 180, "Medium": 145, "Hard": 115}[difficulty]
    notes_minutes = word_count / {"Easy": 420, "Medium": 330, "Hard": 260}[difficulty]
    concept_minutes = (academic_hits * 5) + (practice_hits * 4)
    data_minutes = min(40, (number_density + symbol_density) * word_count * 0.4)
    review_minutes = {"Easy": 20, "Medium": 35, "Hard": 55}[difficulty] + min(35, page_count * 4)
    practice_minutes = min(75, practice_hits * 7 + table_like_lines * 3)
    total_minutes = max(35, reading_minutes + notes_minutes + concept_minutes + data_minutes + review_minutes + practice_minutes)

    return int(math.ceil(total_minutes / 5) * 5)


def decode_pdf_literal(value: bytes) -> str:
    result = bytearray()
    index = 0

    while index < len(value):
        char = value[index]

        if char == 92 and index + 1 < len(value):
            index += 1
            escaped = value[index]
            replacements = {
                ord("n"): ord("\n"),
                ord("r"): ord("\r"),
                ord("t"): ord("\t"),
                ord("b"): ord("\b"),
                ord("f"): ord("\f"),
                ord("("): ord("("),
                ord(")"): ord(")"),
                ord("\\"): ord("\\"),
            }

            if escaped in replacements:
                result.append(replacements[escaped])
            elif 48 <= escaped <= 55:
                octal = bytes([escaped])
                lookahead = index + 1

                while lookahead < len(value) and len(octal) < 3 and 48 <= value[lookahead] <= 55:
                    octal += bytes([value[lookahead]])
                    lookahead += 1

                result.append(int(octal, 8))
                index = lookahead - 1
            else:
                result.append(escaped)
        else:
            result.append(char)

        index += 1

    return decode_pdf_bytes(bytes(result))


def decode_pdf_bytes(value: bytes) -> str:
    if b"\x00" in value[:20]:
        try:
            return value.decode("utf-16-be", errors="ignore")
        except Exception:
            pass

    return value.decode("latin-1", errors="ignore")


def looks_readable(text: str) -> bool:
    if len(text) < 3:
        return False

    printable = sum(1 for char in text if char.isprintable() or char.isspace())
    letters = sum(1 for char in text if char.isalpha())
    controls = sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t")
    total = max(1, len(text))

    if printable / total < 0.9 or controls:
        return False

    if letters / total < 0.35:
        return False

    return True


def shift_minus_three(text: str) -> str:
    result = []

    for char in text:
        code = ord(char)

        if "D" <= char <= "Z":
            result.append(chr(code - 3))
        elif "A" <= char <= "C":
            result.append(chr(code + 23))
        elif "d" <= char <= "z":
            result.append(chr(code - 3))
        elif "a" <= char <= "c":
            result.append(chr(code + 23))
        elif char == "\\":
            result.append("Y")
        elif char == "[":
            result.append("X")
        elif char == "]":
            result.append("Z")
        elif char == "|":
            result.append("y")
        elif char == "{":
            result.append("x")
        elif char == "}":
            result.append("z")
        else:
            result.append(char)

    return "".join(result)


def word_quality(word: str) -> float:
    lowered = re.sub(r"[^a-z]", "", word.lower())

    if len(lowered) < 3:
        return 0.0

    common_words = {
        "the", "and", "for", "with", "this", "that", "from", "network",
        "computer", "course", "submitted", "university", "technology",
        "information", "institute", "student", "teacher", "chapter",
        "figure", "table", "system", "data",
    }
    patterns = ("tion", "ing", "ment", "work", "tech", "info", "vers", "comp")
    vowels = sum(1 for char in lowered if char in "aeiou")
    vowel_ratio = vowels / max(1, len(lowered))
    score = 0.0

    if lowered in common_words:
        score += 4.0

    score += sum(1.3 for pattern in patterns if pattern in lowered)

    if 0.22 <= vowel_ratio <= 0.68:
        score += 1.0

    if re.search(r"(.)\1\1", lowered):
        score -= 1.0

    return score


def repair_shifted_words(text: str) -> str:
    repaired = []

    for token in re.split(r"(\s+)", text):
        if not token.strip() or len(token) < 3:
            repaired.append(token)
            continue

        shifted = shift_minus_three(token)

        if word_quality(shifted) > word_quality(token) + 0.8:
            repaired.append(shifted)
        else:
            repaired.append(token)

    return "".join(repaired)


def decode_pdf_token(token: bytes) -> str:
    token = token.strip()

    if token.startswith(b"(") and token.endswith(b")"):
        return decode_pdf_literal(token[1:-1])

    if token.startswith(b"<") and token.endswith(b">") and not token.startswith(b"<<"):
        raw_hex = re.sub(rb"\s+", b"", token[1:-1])
        if len(raw_hex) % 2:
            raw_hex += b"0"

        try:
            return decode_pdf_bytes(bytes.fromhex(raw_hex.decode("ascii")))
        except Exception:
            return ""

    return ""


def extract_pdf_strings(content: bytes) -> list[str]:
    if not is_likely_text_stream(content):
        return []

    strings = []
    token_re = rb"(?:\((?:\\.|[^\\)])*\)|(?<!<)<[0-9A-Fa-f\s]{4,}>(?!>))"

    for match in re.finditer(rb"\[(.*?)\]\s*TJ", content, flags=re.S):
        parts = []
        for token in re.finditer(token_re, match.group(1), flags=re.S):
            text = clean_text(decode_pdf_token(token.group(0)))
            if looks_readable(text):
                parts.append(text)

        if parts:
            strings.append(" ".join(parts))

        if len(strings) >= MAX_FALLBACK_STRINGS:
            return strings

    for match in re.finditer(rb"(" + token_re + rb")\s*(?:Tj|'|\")", content, flags=re.S):
        text = clean_text(decode_pdf_token(match.group(1)))
        if looks_readable(text):
            strings.append(text)

        if len(strings) >= MAX_FALLBACK_STRINGS:
            return strings

    if not strings and b"BT" in content and b"ET" in content:
        for block in re.finditer(rb"BT(.*?)ET", content, flags=re.S):
            parts = []
            for token in re.finditer(token_re, block.group(1), flags=re.S):
                text = clean_text(decode_pdf_token(token.group(0)))
                if looks_readable(text):
                    parts.append(text)

            if parts:
                strings.append(" ".join(parts))

            if len(strings) >= MAX_FALLBACK_STRINGS:
                return strings

    return strings


def is_likely_zlib_stream(data: bytes) -> bool:
    if len(data) < 2 or data[0] != 0x78:
        return False

    return ((data[0] << 8) + data[1]) % 31 == 0


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0

    sample = data[:STREAM_SAMPLE_BYTES]
    printable = sum(byte in b"\n\r\t" or 32 <= byte <= 126 for byte in sample)
    return printable / max(1, len(sample))


def is_likely_text_stream(content: bytes) -> bool:
    if not any(marker in content for marker in (b"BT", b"Tj", b"TJ")):
        return False

    return printable_ratio(content) >= MIN_TEXT_STREAM_PRINTABLE_RATIO


def decompress_pdf_streams(data: bytes) -> list[bytes]:
    streams = []

    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.S):
        raw = match.group(1).strip(b"\r\n")

        try:
            decoded = zlib.decompress(raw)
        except Exception:
            if is_likely_zlib_stream(raw):
                continue

            decoded = raw

        if is_likely_text_stream(decoded):
            streams.append(decoded)

    return streams


def parse_pdf_objects(data: bytes) -> dict[int, bytes]:
    return {
        int(match.group(1)): match.group(3)
        for match in re.finditer(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", data, re.S)
    }


def decode_pdf_stream_object(body: bytes) -> bytes | None:
    match = re.search(rb"stream\r?\n(.*?)\r?\nendstream", body, re.S)

    if not match:
        return None

    raw = match.group(1).strip(b"\r\n")

    if b"/FlateDecode" in body:
        try:
            return zlib.decompress(raw)
        except Exception:
            return raw

    return raw


def decode_unicode_hex(hex_value: str) -> str:
    try:
        raw = bytes.fromhex(hex_value)
    except ValueError:
        return ""

    if len(raw) > 1 and len(raw) % 2 == 0:
        return raw.decode("utf-16-be", errors="ignore")

    return raw.decode("latin-1", errors="ignore")


def parse_cmap(stream: bytes | None) -> dict[str, str]:
    if not stream:
        return {}

    text = stream.decode("latin-1", errors="ignore")
    mapping: dict[str, str] = {}

    for block in re.finditer(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block.group(1)):
            mapping[src.upper()] = decode_unicode_hex(dst)

    for block in re.finditer(r"beginbfrange(.*?)endbfrange", text, re.S):
        block_text = block.group(1)

        for src_start, src_end, dst_start in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
            block_text,
        ):
            start = int(src_start, 16)
            end = int(src_end, 16)
            destination = int(dst_start, 16)
            width = len(src_start)

            for code in range(start, end + 1):
                mapping[f"{code:0{width}X}"] = chr(destination + (code - start))

        for src_start, src_end, array_text in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]",
            block_text,
            re.S,
        ):
            start = int(src_start, 16)
            width = len(src_start)
            values = re.findall(r"<([0-9A-Fa-f]+)>", array_text)

            for offset, dst in enumerate(values):
                mapping[f"{start + offset:0{width}X}"] = decode_unicode_hex(dst)

    return mapping


def build_font_maps(objects: dict[int, bytes]) -> dict[str, dict[str, str]]:
    font_object_maps: dict[int, dict[str, str]] = {}

    for object_id, body in objects.items():
        match = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", body)

        if match:
            cmap_object_id = int(match.group(1))
            font_object_maps[object_id] = parse_cmap(
                decode_pdf_stream_object(objects.get(cmap_object_id, b""))
            )

    font_name_maps: dict[str, dict[str, str]] = {}

    for body in objects.values():
        for name, ref in re.findall(rb"/(F\d+)\s+(\d+)\s+0\s+R", body):
            font_object_id = int(ref)

            if font_object_id in font_object_maps:
                font_name_maps[name.decode("ascii", errors="ignore")] = font_object_maps[font_object_id]

    return font_name_maps


def decode_hex_with_cmap(hex_value: str, cmap: dict[str, str]) -> str:
    hex_value = re.sub(r"\s+", "", hex_value.upper())
    result = []
    index = 0

    while index < len(hex_value):
        matched = False

        for width in (8, 6, 4, 2):
            code = hex_value[index:index + width]

            if len(code) == width and code in cmap:
                result.append(cmap[code])
                index += width
                matched = True
                break

        if matched:
            continue

        try:
            result.append(bytes.fromhex(hex_value[index:index + 2]).decode("latin-1", errors="ignore"))
        except Exception:
            pass

        index += 2

    return "".join(result)


def decode_text_token_with_font(token: bytes, cmap: dict[str, str]) -> str:
    token = token.strip()

    if token.startswith(b"<") and token.endswith(b">") and not token.startswith(b"<<"):
        return decode_hex_with_cmap(token[1:-1].decode("ascii", errors="ignore"), cmap)

    if token.startswith(b"(") and token.endswith(b")"):
        return decode_pdf_literal(token[1:-1])

    return ""


def clean_extracted_pdf_text(value: str) -> str:
    value = value.replace("\r", "\n")
    value = re.sub(r"\s*-\s*\n\s*", "-", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([A-Za-z])\s+-\s+([A-Za-z])", r"\1-\2", value)
    return value.strip()


def extract_text_from_pdf_content(content: bytes, font_maps: dict[str, dict[str, str]]) -> str:
    token_re = rb"(?:\((?:\\.|[^\\)])*\)|(?<!<)<[0-9A-Fa-f\s]{2,}>(?!>))"
    current_font = ""
    text_parts: list[str] = []

    operator_re = re.compile(
        rb"/(F\d+)\s+[\d.]+\s+Tf|\[(.*?)\]\s*TJ|(" + token_re + rb")\s*(?:Tj|'|\")",
        re.S,
    )

    for match in operator_re.finditer(content):
        if match.group(1):
            current_font = match.group(1).decode("ascii", errors="ignore")
            continue

        cmap = font_maps.get(current_font, {})

        if match.group(2) is not None:
            pieces = []

            for token in re.finditer(token_re, match.group(2), re.S):
                pieces.append(decode_text_token_with_font(token.group(0), cmap))

            value = "".join(pieces)
        else:
            value = decode_text_token_with_font(match.group(3), cmap)

        value = clean_text(value)

        if value and looks_readable(value):
            text_parts.append(value)

    return clean_extracted_pdf_text("\n".join(text_parts))


def content_references(page_body: bytes) -> list[int]:
    match = re.search(rb"/Contents\s+\[(.*?)\]", page_body, re.S)

    if match:
        return [int(ref) for ref in re.findall(rb"(\d+)\s+0\s+R", match.group(1))]

    return [int(ref) for ref in re.findall(rb"/Contents\s+(\d+)\s+0\s+R", page_body)]


def read_pdf_with_cmaps(data: bytes) -> list[dict[str, object]]:
    objects = parse_pdf_objects(data)
    font_maps = build_font_maps(objects)

    if not font_maps:
        return []

    pages: list[dict[str, object]] = []
    page_objects = [
        (object_id, body)
        for object_id, body in objects.items()
        if re.search(rb"/Type\s*/Page\b", body)
    ]

    for page_number, (_, page_body) in enumerate(page_objects, start=1):
        page_parts = []

        for ref in content_references(page_body):
            stream = decode_pdf_stream_object(objects.get(ref, b""))

            if stream:
                page_text = extract_text_from_pdf_content(stream, font_maps)

                if page_text:
                    page_parts.append(page_text)

        text = clean_extracted_pdf_text("\n".join(page_parts))

        if text:
            pages.append({"page": page_number, "text": text})

    return pages


def read_pdf_with_stdlib(file_path: Path) -> list[dict[str, object]]:
    data = file_path.read_bytes()

    cmap_pages = read_pdf_with_cmaps(data)

    if cmap_pages:
        return cmap_pages

    streams = decompress_pdf_streams(data)
    text_parts = []
    text_size = 0

    for stream in streams:
        for extracted in extract_pdf_strings(stream):
            text_parts.append(extracted)
            text_size += len(extracted)

            if text_size >= MAX_FALLBACK_TEXT_CHARS:
                break

        if text_size >= MAX_FALLBACK_TEXT_CHARS:
            break

    if not text_parts:
        for match in re.finditer(rb"[A-Za-z0-9][A-Za-z0-9 ,.;:!?/%+\-()]{24,}", data):
            text = clean_text(decode_pdf_bytes(match.group(0)))
            if looks_readable(text):
                text_parts.append(text)
                text_size += len(text)

            if text_size >= MAX_FALLBACK_TEXT_CHARS:
                break

    text = repair_shifted_words(clean_text(" ".join(part for part in text_parts if part)))
    page_count = max(1, len(re.findall(rb"/Type\s*/Page\b", data)))

    if not text:
        return []

    return [{"page": 1, "page_count": page_count, "text": text}]


def read_pdf_pages(file_path: Path) -> list[dict[str, object]]:
    try:
        import fitz

        pages: list[dict[str, object]] = []
        with fitz.open(str(file_path)) as doc:
            for page_number, page in enumerate(doc, start=1):
                text = clean_text(page.get_text("text"))
                if text:
                    pages.append({"page": page_number, "text": text})
        return pages
    except Exception:
        return read_pdf_with_stdlib(file_path)


def page_count_from_pages(pages: list[dict[str, object]]) -> int:
    if not pages:
        return 0

    return max(int(page.get("page_count", page.get("page", 1))) for page in pages)


def tokenize(text: str, *, keep_numbers: bool = True) -> list[str]:
    tokens = []
    for token in WORD_RE.findall(text.lower()):
        if token in STOP_WORDS:
            continue
        if len(token) < 3 and not token.isdigit():
            continue
        if token.isdigit() and not keep_numbers:
            continue
        tokens.append(token)
    return tokens


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", clean_text(text))
    sentences = []

    for part in parts:
        sentence = re.sub(r"\s+", " ", part).strip(" -\t\r\n")
        word_count = len(WORD_RE.findall(sentence))

        if 6 <= word_count <= 85:
            sentences.append(sentence)

    return sentences


def trim_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip(".,;:") + "..."


def top_terms(text: str, limit: int = 10) -> list[str]:
    counts = Counter(tokenize(text, keep_numbers=False))
    terms = []

    for term, _ in counts.most_common(limit * 3):
        if any(existing in term or term in existing for existing in terms):
            continue
        terms.append(term)
        if len(terms) == limit:
            break

    return terms


def sentence_scores(
    sentences: list[str],
    focus_terms: Iterable[str] | None = None,
) -> list[float]:
    focus = set(focus_terms or [])
    corpus_terms = tokenize(" ".join(sentences), keep_numbers=False)
    counts = Counter(corpus_terms)
    max_count = max(counts.values(), default=1)
    scores = []

    for index, sentence in enumerate(sentences):
        tokens = tokenize(sentence, keep_numbers=False)
        if not tokens:
            scores.append(0.0)
            continue

        unique_tokens = set(tokens)
        term_score = sum(counts[token] / max_count for token in tokens)
        focus_score = len(unique_tokens & focus) * 1.4
        word_count = len(WORD_RE.findall(sentence))
        length_score = 1.0 if 14 <= word_count <= 34 else 0.75
        position_score = 1.2 if index < max(2, len(sentences) * 0.18) else 1.0
        scores.append((term_score + focus_score) * length_score * position_score)

    return scores


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def select_sentences(
    sentences: list[str],
    *,
    max_count: int,
    focus_terms: Iterable[str] | None = None,
) -> list[str]:
    if not sentences:
        return []

    scores = sentence_scores(sentences, focus_terms)
    ranked = sorted(range(len(sentences)), key=lambda index: scores[index], reverse=True)
    selected: list[tuple[int, set[str]]] = []

    for index in ranked:
        tokens = set(tokenize(sentences[index], keep_numbers=False))
        if not tokens:
            continue

        if any(jaccard(tokens, existing_tokens) > 0.58 for _, existing_tokens in selected):
            continue

        selected.append((index, tokens))

        if len(selected) == max_count:
            break

    return [sentences[index] for index, _ in sorted(selected)]


def build_summary(text: str, page_count: int) -> str:
    text = normalize_document_text(text)
    sections = extract_sections(text)
    sentences = split_sentences(text)
    terms = top_terms(text, 10)

    if not sentences:
        return "Overview: This PDF does not contain enough readable text to summarize clearly."

    title = document_title(sections, terms)
    abstract = first_available_section(sections, ["abstract", "overview"])
    overview = " ".join(best_sentences(abstract or text, 2))
    objectives = section_bullets(sections, "objectives", 4)
    theory = section_bullets(sections, "theory", 2)
    procedure = section_bullets(sections, "procedure", 4)
    results = section_bullets(sections, "results and observations", 4)
    discussion = section_bullets(sections, "discussion", 2)
    conclusion = section_bullets(sections, "conclusion", 2)
    fallback_points = best_sentences(text, 6)
    recall_questions = [item["question"] for item in build_suggested_questions(text, page_count)[:6]]

    lines = [
        "Study Brief",
        "Document: " + title,
        "Purpose: " + trim_words(overview or "This document explains the main ideas, process, results, and study takeaways from the uploaded PDF.", 88),
        "",
        "Must-know points:",
    ]

    must_know = objectives or theory or fallback_points[:4]

    for sentence in must_know[:5]:
        lines.append("- " + sentence)

    if procedure:
        lines.extend(["", "Process / method:"])
        for sentence in procedure[:4]:
            lines.append("- " + sentence)

    if results:
        lines.extend(["", "Results / evidence:"])
        for sentence in results[:4]:
            lines.append("- " + sentence)
    elif discussion:
        lines.extend(["", "Discussion highlights:"])
        for sentence in discussion[:3]:
            lines.append("- " + sentence)

    if conclusion:
        lines.extend(["", "Conclusion:"])
        for sentence in conclusion[:2]:
            lines.append("- " + sentence)

    if terms:
        lines.extend(["", "Focus topics: " + ", ".join(terms[:8])])

    if recall_questions:
        lines.extend(["", "Active recall questions:"])
        for question in recall_questions:
            lines.append("- " + question)

    lines.append("")
    lines.append(f"Coverage: {page_count} page{'s' if page_count != 1 else ''} analyzed. Refresh this summary after editing or replacing the PDF.")

    return "\n".join(lines)


def estimate_difficulty(text: str, page_count: int) -> dict[str, object]:
    features = analyze_learning_features(text, page_count)
    word_count = int(features["word_count"])
    avg_sentence_length = float(features["avg_sentence_length"])
    complex_ratio = float(features["complex_ratio"])
    unique_ratio = float(features["unique_ratio"])
    academic_hits = int(features["academic_hits"])
    practice_hits = int(features["practice_hits"])
    number_density = float(features["number_density"])
    symbol_density = float(features["symbol_density"])
    section_count = int(features["section_count"])
    table_like_lines = int(features["table_like_lines"])

    volume_score = min(24.0, (word_count / 3200) * 24)
    reading_score = min(18.0, (avg_sentence_length / 30) * 18)
    vocabulary_score = min(18.0, (complex_ratio / 0.22) * 18)
    concept_score = min(14.0, (unique_ratio / 0.78) * 14)
    academic_score = min(10.0, academic_hits * 1.35)
    practice_score = min(7.0, practice_hits * 0.9)
    data_score = min(5.0, (number_density + symbol_density) * 85)
    structure_score = min(4.0, section_count * 0.55 + table_like_lines * 0.15)
    score = round(
        volume_score
        + reading_score
        + vocabulary_score
        + concept_score
        + academic_score
        + practice_score
        + data_score
        + structure_score,
        2,
    )

    if score >= 72:
        difficulty = "Hard"
    elif score >= 42:
        difficulty = "Medium"
    else:
        difficulty = "Easy"

    total_minutes = estimate_study_minutes(features, difficulty)
    study_hours = max(1, math.ceil(total_minutes / 60))

    return {
        "word_count": word_count,
        "avg_sentence_length": round(avg_sentence_length, 1),
        "complex_ratio": round(complex_ratio, 3),
        "score": score,
        "difficulty": difficulty,
        "study_hours": study_hours,
        "study_minutes": total_minutes,
        "concept_count": academic_hits,
        "practice_count": practice_hits,
    }


def build_study_plan(text: str, study_hours: int, difficulty: str) -> str:
    text = normalize_document_text(text)
    sections = extract_sections(text)
    features = analyze_learning_features(text, page_count=max(1, math.ceil(len(WORD_RE.findall(text)) / 450)))
    topics = top_terms(text, 6)
    total_minutes = estimate_study_minutes(features, difficulty)
    session_minutes = 45 if difficulty == "Easy" else 55 if difficulty == "Medium" else 65
    session_count = max(1, math.ceil(total_minutes / session_minutes))
    topic_text = ", ".join(topics[:4]) if topics else "the main headings"
    priority_section = first_available_section(sections, ["objectives", "procedure", "results and observations", "conclusion"])
    priority = trim_words(" ".join(select_sentences(split_sentences(priority_section), max_count=1)), 24)
    recall_questions = build_recall_questions(sections, topics)

    lines = [
        f"Total target: about {study_hours} hour{'s' if study_hours != 1 else ''} ({total_minutes} minutes) across {session_count} focused session{'s' if session_count != 1 else ''}.",
        f"Session 1 ({session_minutes} min): Preview the summary, list unknown terms, and focus on {topic_text}.",
    ]

    if session_count >= 2:
        lines.append(
            f"Session 2 ({session_minutes} min): Study the core sections, write short notes, and explain the main process aloud."
        )

    if session_count >= 3:
        range_label = f"Sessions 3-{session_count}" if session_count > 3 else "Session 3"
        lines.append(
            f"{range_label} ({session_minutes} min each): Practice recall, test yourself with PDF chat, and repair weak points."
        )

    if priority:
        lines.append("Priority checkpoint: " + priority)

    if recall_questions:
        lines.append("Self-test: " + " | ".join(recall_questions[:3]))

    if difficulty == "Hard":
        lines.append("Review rhythm: recap after 24 hours and again before the exam or lab submission.")
    elif difficulty == "Medium":
        lines.append("Review rhythm: recap once later today and once before the deadline.")
    else:
        lines.append("Review rhythm: spend the last 15-20 minutes testing yourself from memory.")

    return "\n".join(lines)


def make_chunks(pages: list[dict[str, object]]) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []

    for page in pages:
        sentences = split_sentences(normalize_document_text(str(page["text"])))
        current: list[str] = []
        current_words = 0

        for sentence in sentences:
            current.append(sentence)
            current_words += len(WORD_RE.findall(sentence))

            if current_words >= 95:
                chunks.append({"page": page["page"], "text": " ".join(current)})
                current = []
                current_words = 0

        if current:
            chunks.append({"page": page["page"], "text": " ".join(current)})

    return chunks


def rank_chunks(question: str, chunks: list[dict[str, object]]) -> list[dict[str, object]]:
    if not chunks:
        return []

    question_terms = tokenize(question)
    question_set = set(question_terms)
    document_frequency: Counter[str] = Counter()
    chunk_tokens = []

    for chunk in chunks:
        tokens = tokenize(str(chunk["text"]))
        chunk_tokens.append(tokens)
        document_frequency.update(set(tokens))

    ranked = []
    total_chunks = max(1, len(chunks))

    for chunk, tokens in zip(chunks, chunk_tokens):
        token_counts = Counter(tokens)
        chunk_length = max(1, len(tokens))
        score = 0.0

        for term in question_set:
            if term not in token_counts:
                continue

            idf = math.log((total_chunks + 1) / (document_frequency[term] + 1)) + 1
            tf = token_counts[term] / chunk_length
            score += (1 + math.log(1 + token_counts[term])) * idf + tf

        if question_set:
            score += len(question_set & set(tokens)) / len(question_set)

        ranked.append({**chunk, "score": round(score, 4)})

    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def section_answer(question_lower: str, sections: dict[str, str]) -> list[tuple[str, str]]:
    choices = [
        (("objective", "aim", "goal"), "objectives", "Objectives"),
        (("material", "equipment", "tool", "component"), "materials and equipment", "Materials and equipment"),
        (("procedure", "step", "method", "process", "how"), "procedure", "Procedure"),
        (("result", "observation", "output", "ping"), "results and observations", "Results and observations"),
        (("discussion", "explain", "why"), "discussion", "Discussion"),
        (("conclusion", "final", "learned"), "conclusion", "Conclusion"),
        (("abstract", "overview", "about", "topic"), "abstract", "Overview"),
        (("theory", "concept", "background"), "theory", "Theory"),
    ]
    matches = []

    for keywords, section_key, label in choices:
        if any(keyword in question_lower for keyword in keywords) and sections.get(section_key):
            matches.append((label, sections[section_key]))

    return matches


def answer_from_pdf(question: str, pages: list[dict[str, object]], text: str) -> str:
    question_clean = question.strip()
    question_lower = question_clean.lower()
    text = normalize_document_text(text)
    sections = extract_sections(text)

    if not question_clean:
        return "Please ask a clear question about the uploaded PDF."

    if any(term in question_lower for term in ["summarize", "summary", "short note", "what is this pdf"]):
        return build_summary(text, page_count_from_pages(pages))

    if any(term in question_lower for term in ["suggest", "question ideas", "what should i ask", "practice question"]):
        suggestions = build_suggested_questions(text, page_count_from_pages(pages))
        return "Suggested questions:\n" + "\n".join(f"- {item['question']}" for item in suggestions)

    if any(term in question_lower for term in ["quiz", "test me", "practice test", "viva questions"]):
        return build_quiz_answer(text, pages)

    if "study" in question_lower and any(
        term in question_lower for term in ["time", "hour", "plan", "schedule"]
    ):
        stats = estimate_difficulty(text, page_count_from_pages(pages))
        return build_study_plan(text, int(stats["study_hours"]), str(stats["difficulty"]))

    if any(term in question_lower for term in ["why", "reason", "logic", "compare", "difference", "versus", "explain"]):
        reasoned = build_reasoning_answer(question_clean, pages, text)
        if reasoned:
            return reasoned

    direct_sections = section_answer(question_lower, sections)

    if direct_sections:
        answer_lines = []

        for label, content in direct_sections[:3]:
            selected = select_sentences(split_sentences(content), max_count=5)
            answer_lines.append(f"{label}:")

            if selected:
                answer_lines.extend("- " + trim_words(sentence, 34) for sentence in selected)
            else:
                answer_lines.append(trim_words(content, 110))

            answer_lines.append("")

        return "\n".join(answer_lines).strip()

    chunks = rank_chunks(question_clean, make_chunks(pages))
    useful_chunks = [chunk for chunk in chunks[:4] if float(chunk["score"]) > 0.12]

    if not useful_chunks and chunks:
        closest = chunks[0]
        return (
            "I could not find a clear direct answer in the PDF. "
            f"The closest section is on page {closest['page']}: "
            + trim_words(str(closest["text"]), 58)
        )

    evidence_text = " ".join(str(chunk["text"]) for chunk in useful_chunks)
    focus_terms = tokenize(question_clean)
    sentences = select_sentences(
        split_sentences(evidence_text),
        max_count=4,
        focus_terms=focus_terms,
    )

    if not sentences:
        sentences = [trim_words(str(useful_chunks[0]["text"]), 70)]

    pages_found = sorted({int(chunk["page"]) for chunk in useful_chunks})
    page_text = ", ".join(str(page) for page in pages_found)
    answer = " ".join(trim_words(sentence, 38) for sentence in sentences)

    if not answer:
        answer = "I found related text, but it was too fragmented to form a confident answer."

    return f"{answer}\n\nSource page{'s' if len(pages_found) != 1 else ''}: {page_text}"


def analyze_payload(data: dict[str, object]) -> dict[str, object]:
    try:
        file_path = resolve_upload_path(str(data.get("file_path", "")))
        pages = read_pdf_pages(file_path)
        text = normalize_document_text("\n".join(str(page["text"]) for page in pages))
        page_count = page_count_from_pages(pages)

        if not text:
            return {"error": "No readable text was found in this PDF"}

        stats = estimate_difficulty(text, page_count)
        study_hours = int(stats["study_hours"])
        difficulty = str(stats["difficulty"])

        return {
            "word_count": stats["word_count"],
            "page_count": page_count,
            "difficulty": difficulty,
            "score": stats["score"],
            "summary": build_summary(text, page_count),
            "study_hours": study_hours,
            "study_plan": build_study_plan(text, study_hours, difficulty),
            "suggested_questions": build_suggested_questions(text, page_count),
        }
    except Exception as exc:
        return {"error": str(exc)}


def ask_payload(data: dict[str, object]) -> dict[str, object]:
    try:
        file_path = resolve_upload_path(str(data.get("file_path", "")))
        question = str(data.get("question", ""))
        pages = read_pdf_pages(file_path)
        text = normalize_document_text("\n".join(str(page["text"]) for page in pages))

        if not text:
            return {"error": "No readable text was found in this PDF"}

        return {"answer": answer_from_pdf(question, pages, text)}
    except Exception as exc:
        return {"error": str(exc)}


def suggest_payload(data: dict[str, object]) -> dict[str, object]:
    try:
        file_path = resolve_upload_path(str(data.get("file_path", "")))
        pages = read_pdf_pages(file_path)
        text = normalize_document_text("\n".join(str(page["text"]) for page in pages))

        if not text:
            return {"error": "No readable text was found in this PDF"}

        return {"questions": build_suggested_questions(text, page_count_from_pages(pages))}
    except Exception as exc:
        return {"error": str(exc)}


def service_status_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "Study Planner AI",
        "endpoints": ["/analyze", "/ask", "/suggest"],
    }


def route_request(method: str, path: str, body: bytes = b"") -> tuple[int, dict[str, object]]:
    method = method.upper()

    if method == "GET":
        if path in {"/", "/health", "/openapi.json", "/docs"}:
            return 200, service_status_payload()

        return 404, {"error": "Not found"}

    if method == "POST":
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            return 400, {"error": "Invalid JSON request"}

        if path == "/analyze":
            return 200, analyze_payload(payload)

        if path == "/ask":
            return 200, ask_payload(payload)

        if path == "/suggest":
            return 200, suggest_payload(payload)

        return 404, {"error": "Not found"}

    return 405, {"error": "Method not allowed"}


async def app(scope, receive, send) -> None:
    if scope["type"] == "lifespan":
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] != "http":
        return

    chunks = []

    while True:
        message = await receive()

        if message["type"] != "http.request":
            continue

        chunks.append(message.get("body", b""))

        if not message.get("more_body", False):
            break

    status, payload = route_request(
        str(scope.get("method", "GET")),
        str(scope.get("path", "/")),
        b"".join(chunks),
    )
    response_body = json.dumps(payload).encode("utf-8")

    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(response_body)).encode("ascii")),
        ],
    })
    await send({"type": "http.response.body", "body": response_body})


class StudyPlannerHandler(BaseHTTPRequestHandler):
    server_version = "StudyPlannerAI/1.0"

    def send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        status, payload = route_request("GET", path)
        self.send_json(payload, status)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or 0)
        status, payload = route_request("POST", path, self.rfile.read(length))
        self.send_json(payload, status)

    def log_message(self, format: str, *args: object) -> None:
        return


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), StudyPlannerHandler)
    print(f"Study Planner AI running on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Study Planner AI backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    run_server(args.host, args.port)
