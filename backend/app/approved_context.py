"""Caller-owned source spans and generic labelled fields at the speech boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.steer_planner import AnswerSpan, receiver_question

MAX_ANSWER_CHARACTERS = 1200

# These are field spellings, never generated answers. Values remain exact source text.
_FIELD_SPELLINGS = (
    (r"\b(?:date of birth|birth date|dob)\b", " birthdate "),
    (r"\b(?:blood pressure|bp)\b", " bloodpressure "),
    (r"\b(?:patient(?:['’]s)? id|registration (?:number|id))\b", " identifier "),
    (r"\b(?:registration status|registered patient)\b", " registrationstatus "),
    (r"\b(?:identification number|id)\b", " identifier "),
    (r"\b(?:physician|clinician|consultant|doctor|dr)\b", " doctor "),
    (r"\b(?:allergic|allergies|allergy)\b", " allergy "),
    (r"\b(?:tablets|medicines|medications|medication)\b", " medication "),
)
_STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "what",
        "which",
        "who",
        "whose",
        "how",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "any",
        "or",
        "and",
        "of",
        "at",
        "on",
        "in",
        "to",
        "for",
        "from",
        "their",
        "they",
        "them",
        "your",
        "you",
        "his",
        "her",
        "my",
        "me",
        "our",
        "can",
        "could",
        "please",
        "tell",
        "give",
        "share",
        "about",
        "it",
        "s",
        "last",
        "latest",
        "previous",
        "checkup",
        "check",
        "visit",
        "supplied",
        "printed",
        "document",
        "form",
        "report",
        "information",
        "detail",
        "value",
        "registered",
        "patient",
        "caller",
        "person",
    ]
)


def terms(text: str) -> frozenset[str]:
    text = text.lower()
    for pattern, replacement in _FIELD_SPELLINGS:
        text = re.sub(pattern, replacement, text)
    words = re.findall(r"[a-z0-9]+", text)
    return frozenset(
        word[:-3] + "y" if word.endswith("ies") else word[:-1] if word.endswith("s") else word
        for word in words
        if word not in _STOP_WORDS
    )


def role(text: str) -> str | None:
    return (
        "doctor"
        if terms(text) & {"doctor"}
        else ("caller" if re.search(r"\b(patient|caller)\b", text, re.I) else None)
    )


@dataclass(frozen=True)
class SourceField:
    label: str
    value: str

    @property
    def keys(self) -> frozenset[str]:
        abbreviations = " ".join(re.findall(r"\b[A-Z]{2,6}\b", self.value))
        return terms(self.label + " " + abbreviations)


def fields(text: str) -> list[SourceField]:
    result: list[SourceField] = []
    matches = list(re.finditer(r"(?m)^\s*([^:\n]{1,80}):[ \t]*", text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = next(
            (line.strip() for line in text[match.end() : end].splitlines() if line.strip()), ""
        )
        if value:
            result.append(SourceField(match.group(1).strip(), value))
    return result


def source_fields(source: dict[str, Any]) -> list[SourceField]:
    if source["source_id"].startswith("document:"):
        return fields(source["text"])
    label = source.get("label", "")
    return [SourceField(label, source["text"])] if label else []


_NAME_MODIFIERS = frozenset({"full", "first", "last", "middle", "given", "family", "preferred"})


def _field_role(field: SourceField) -> str | None:
    explicit = role(field.label)
    if explicit:
        return explicit
    label_keys = terms(field.label)
    return (
        "caller" if "name" in label_keys and not (label_keys - {"name"} - _NAME_MODIFIERS) else None
    )


def _name_scope(question: str) -> tuple[set[str], bool]:
    if "name" not in terms(question):
        return set(), False
    subjects = re.findall(r"\b([a-z][\w-]*)(?:['’]s)?\s+names?\b", question, re.I)
    subjects += re.findall(r"\bnames? of (?:the )?([a-z][\w-]*)", question, re.I)
    specific = set().union(*(terms(subject) for subject in subjects)) - _NAME_MODIFIERS
    caller = bool(
        re.search(
            r"\b(?:patient|caller|your|their|my|our)(?:['’]s)?\s+"
            r"(?:(?:full|first|last|given|middle|family)\s+)?names?\b"
            r"|\b(?:patient|caller)(?:['’]s)?\s+and\b"
            r"|\bnames? of (?:the )?(?:patient|caller)\b",
            question,
            re.I,
        )
    )
    return specific, caller


def referenced_provider_target(
    request: str, sources: list[dict[str, Any]]
) -> tuple[bool, str | None]:
    """Resolve only an explicit provider reference to one current labelled value."""
    reference = re.search(
        r"\b([a-z]+)(?:\s+name)?\s+(?:(?:listed|named|shown)\s+)?(?:in|from|on)\s+"
        r"[^.!?;\n]{0,80}\b(?:report|document|attachment|file)\b",
        request,
        re.I,
    )
    if not reference:
        return False, None
    requested = terms(reference[1])
    values: dict[str, str] = {}
    for source in sources:
        if not source["source_id"].startswith("document:"):
            continue
        for field in source_fields(source):
            label = terms(field.label)
            if not requested <= label:
                continue
            if re.search(r"\b(previous|former|historical)\b", field.label, re.I):
                continue
            if label - requested - {"name"}:
                return True, None
            values.setdefault(" ".join(field.value.casefold().split()).rstrip(".! ,;"), field.value)
    return True, next(iter(values.values())) if len(values) == 1 else None


def retrieve_known_fields(
    sources: list[dict[str, Any]], question: str, question_id: str
) -> list[AnswerSpan] | None:
    """Retrieve clear labelled facts only; the speech validator retains authority."""
    if any(
        source["source_id"].startswith("caller:") and source.get("question_id") == question_id
        for source in sources
    ):
        return None
    question_keys = terms(question)
    name_subjects, caller_name_asked = _name_scope(question)
    question_role = role(question) or "caller"
    allowed_roles = {question_role}
    if (
        question_role == "doctor"
        and re.search(r"\band\b", question, re.I)
        and re.search(r"\b(patient|caller)\b", question, re.I)
    ):
        allowed_roles.add("caller")
    candidates: dict[frozenset[str], tuple[str, AnswerSpan]] = {}
    for source in sources:
        if source["source_id"].startswith("caller:") and source.get("question_id") != question_id:
            continue
        for field in source_fields(source):
            field_role = _field_role(field)
            if not (field.keys & question_keys) or (field_role and field_role not in allowed_roles):
                continue
            if re.search(r"\b(previous|former|historical)\b", field.label, re.I) and not re.search(
                r"\b(previous|former|historical)\b", question, re.I
            ):
                continue
            if (
                "name" in field.keys
                and name_subjects
                and not caller_name_asked
                and not (field.keys & name_subjects)
            ):
                continue
            if terms(field.label) - question_keys:
                return None
            if len(field.value) > 600:
                return None
            key = field.keys & question_keys
            value = " ".join(field.value.casefold().split()).rstrip(".! ,;")
            if key in candidates and candidates[key][0] != value:
                return None
            candidates.setdefault(
                key, (value, AnswerSpan(source_id=source["source_id"], quote=field.value))
            )
    spans = [span for _, span in candidates.values()]
    covered = frozenset().union(*candidates)
    if not spans or len(spans) > 6 or question_keys - covered:
        return None
    _, rejection = validate_answer(sources, question, question_id, spans)
    return spans if rejection is None else None


def validate_answer(
    sources: list[dict[str, Any]], question: str, question_id: str, spans: list[AnswerSpan]
) -> tuple[str | None, str | None]:
    """Validate provenance and explicit field/entity scope, without inventing prose."""
    by_id = {source["source_id"]: source for source in sources}
    selected: list[tuple[dict[str, Any], str]] = []
    for span in spans:
        source = by_id.get(span.source_id)
        if source is None or not span.quote.strip():
            return None, "source_span"
        exact = span.quote
        if exact not in source["text"]:
            folded: list[str] = []
            positions: list[int] = []
            for index, character in enumerate(source["text"]):
                if character.isalnum():
                    folded.extend(character.lower())
                    positions.extend([index] * len(character.lower()))
            needle = "".join(c.lower() for c in exact if c.isalnum())
            offset = "".join(folded).find(needle) if needle else -1
            if offset < 0:
                return None, "source_span"
            exact = source["text"][positions[offset] : positions[offset + len(needle) - 1] + 1]
        if span.source_id.startswith("caller:") and source.get("question_id") != question_id:
            return None, "question_binding"
        selected.append((source, exact.strip()))
    clauses = re.findall(r"[^.!?]+[.!?]?", question)
    questions: list[str] = []
    for clause in clauses:
        if receiver_question(clause) or (
            questions and re.match(r"^\s*(?:and|or|also)\b", clause, re.I)
        ):
            questions.append(clause)
    question = " ".join(questions) if questions else question
    question_keys = terms(question)
    # Provenance is strict for every proposed span. Once established, discard
    # inert document headings rather than treating them as answer facts. Actual
    # labelled fields remain subject to every coverage/entity/history guard.
    selected = [
        (source, quote)
        for source, quote in selected
        if not (
            source["source_id"].startswith("document:")
            and source_fields(source)
            and not any(
                quote in field.value or field.value.rstrip(".! ,;") in quote
                for field in source_fields(source)
            )
            and not (terms(quote) & question_keys)
        )
    ]
    if not selected:
        return None, "answer_scope"
    answer = "; ".join(dict.fromkeys(quote for _, quote in selected))
    if len(answer) > MAX_ANSWER_CHARACTERS:
        return None, "answer_size"
    name_subjects, caller_name_asked = _name_scope(question)
    question_role = role(question) or "caller"
    allowed_roles = {question_role}
    if (
        question_role == "doctor"
        and re.search(r"\band\b", question, re.I)
        and re.search(r"\b(patient|caller)\b", question, re.I)
    ):
        allowed_roles.add("caller")
    required: set[frozenset[str]] = set()
    covered: set[frozenset[str]] = set()
    for source in sources:
        for field in source_fields(source):
            field_role = _field_role(field)
            overlap = field.keys & question_keys
            if not overlap or (field_role and field_role not in allowed_roles):
                continue
            if re.search(r"\b(previous|former|historical)\b", field.label, re.I) and not re.search(
                r"\b(previous|former|historical)\b", question, re.I
            ):
                continue
            required.add(overlap)
            for chosen_source, quote in selected:
                if (
                    chosen_source["source_id"] == "request"
                    and field_role
                    and role(quote) == field_role
                ):
                    covered.add(overlap)
                if chosen_source["source_id"] == source["source_id"] and (
                    quote in field.value or field.value.rstrip(".! ,;") in quote
                ):
                    covered.add(overlap)
    if (
        not caller_name_asked
        and frozenset({"name"}) in required
        and any(frozenset({"name"}) < specific for specific in required)
    ):
        required.remove(frozenset({"name"}))
    if required - covered:
        return None, "requested_field"
    for source, quote in selected:
        chosen_fields = [
            f for f in source_fields(source) if quote in f.value or f.value.rstrip(".! ,;") in quote
        ]
        if (
            source["source_id"].startswith("document:")
            and source_fields(source)
            and not chosen_fields
            and not (terms(quote) & question_keys)
        ):
            return None, "answer_scope"
        if any(_field_role(f) not in allowed_roles for f in chosen_fields if _field_role(f)):
            return None, "entity_scope"
        if any(
            re.search(r"\b(previous|former|historical)\b", f.label, re.I) for f in chosen_fields
        ) and not re.search(r"\b(previous|former|historical)\b", question, re.I):
            return None, "historical_field"
        if (
            name_subjects
            and not caller_name_asked
            and (
                source["source_id"] == "name"
                or any(_field_role(f) == "caller" for f in chosen_fields)
            )
        ):
            return None, "entity_scope"
        if source["source_id"] == "name" and "caller" not in allowed_roles:
            return None, "entity_scope"
    return answer, None
