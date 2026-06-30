import argparse
import asyncio
import csv
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from rag_service.llm import LlmClient


def normalize_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    return None


@dataclass
class EvaluationCase:
    question: str
    expected_answer: str | None = None
    source_url: str | None = None
    title: str | None = None
    question_date: str | None = None
    retrieval_cutoff_date: str | None = None
    gold_document_ids: list[int] | None = None
    gold_chunk_ids: list[str] | None = None


@dataclass
class JudgeScores:
    retrieval_relevance: int | None = None
    answer_groundedness: int | None = None
    citation_quality: int | None = None
    legal_usefulness: int | None = None
    answer_correctness: int | None = None
    notes: str | None = None


@dataclass
class EvaluationResult:
    question: str
    expected_answer: str | None
    source_url: str | None
    answer: str
    latency_ms: int
    reference_count: int
    cited_reference_count: int
    citation_coverage: float
    top_document_ids: str
    top_chunk_ids: str
    top_document_types: str
    top_validity_statuses: str
    top_scopes: str
    top_issuing_authorities: str
    top_issued_dates: str
    top_effective_dates: str
    top_expired_dates: str
    top_external_docids: str
    gold_document_recall_at_k: float | None
    gold_chunk_recall_at_k: float | None
    top1_gold_hit: bool | None
    duplicate_document_rate: float
    retrieval_cutoff_violation_count: int
    judge: JudgeScores


def load_questions(path: str | None, url: str | None, limit: int | None) -> list[EvaluationCase]:
    if path:
        with Path(path).open(encoding="utf-8") as file:
            questions = json.load(file)
    elif url:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            questions = response.json()
    else:
        raise ValueError("Pass --questions-file or --questions-url")

    if not isinstance(questions, list):
        raise ValueError("Questions must be a JSON array")
    cases: list[EvaluationCase] = []
    for item in questions:
        if isinstance(item, str):
            cases.append(EvaluationCase(question=item))
        elif isinstance(item, dict) and isinstance(item.get("question"), str):
            question_date = normalize_date(item.get("question_date") or item.get("published_date"))
            retrieval_cutoff_date = normalize_date(
                item.get("retrieval_cutoff_date")
                or item.get("question_date")
                or item.get("published_date")
            )
            cases.append(
                EvaluationCase(
                    question=item["question"],
                    expected_answer=item.get("expected_answer"),
                    source_url=item.get("source_url"),
                    title=item.get("title"),
                    question_date=question_date,
                    retrieval_cutoff_date=retrieval_cutoff_date,
                    gold_document_ids=_gold_document_ids(item),
                    gold_chunk_ids=_str_list(item.get("gold_chunk_ids")),
                )
            )
        else:
            raise ValueError("Questions must be strings or objects with a question field")
    return cases[:limit] if limit else cases


def _int_list(value: Any) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("gold_document_ids must be a list")
    return [int(item) for item in value]


def _gold_document_ids(item: dict[str, Any]) -> list[int] | None:
    explicit_ids = _int_list(item.get("gold_document_ids"))
    if explicit_ids:
        return _dedupe_preserving_order(explicit_ids)

    citation_ids = [
        int(citation["document_id"])
        for citation in item.get("expected_legal_citations", [])
        if isinstance(citation, dict) and citation.get("document_id") is not None
    ]
    if citation_ids:
        return _dedupe_preserving_order(citation_ids)

    matched_ids: list[int] = []
    for link in item.get("matched_direct_legal_documents", []):
        if not isinstance(link, dict):
            continue
        for document in link.get("matched_documents", []):
            if isinstance(document, dict) and document.get("document_id") is not None:
                matched_ids.append(int(document["document_id"]))
    if matched_ids:
        return _dedupe_preserving_order(matched_ids)
    return None


def _dedupe_preserving_order(values: list[int]) -> list[int]:
    return list(dict.fromkeys(values))


def _str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("gold_chunk_ids must be a list")
    return [str(item) for item in value]


async def ask_rag(
    rag_base_url: str,
    question: str,
    top_k: int,
    retrieval_cutoff_date: str | None = None,
) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    payload: dict[str, Any] = {"question": question, "top_k": top_k}
    if retrieval_cutoff_date:
        payload["retrieval_cutoff_date"] = retrieval_cutoff_date
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{rag_base_url.rstrip('/')}/api/rag/ask",
            json=payload,
        )
        response.raise_for_status()
    latency_ms = int((time.perf_counter() - started) * 1000)
    return response.json(), latency_ms


def citation_coverage(answer: str, reference_count: int) -> tuple[int, float]:
    cited_indexes = {int(match) for match in re.findall(r"\[(\d+)]", answer)}
    cited_reference_count = len({index for index in cited_indexes if 1 <= index <= reference_count})
    if reference_count == 0:
        return 0, 0.0
    return cited_reference_count, cited_reference_count / reference_count


def recall_at_k(retrieved: list[Any], gold: list[Any] | None) -> float | None:
    if not gold:
        return None
    return len(set(retrieved) & set(gold)) / len(set(gold))


def top1_gold_hit(
    retrieved_document_ids: list[int],
    gold_document_ids: list[int] | None,
) -> bool | None:
    if not gold_document_ids:
        return None
    if not retrieved_document_ids:
        return False
    return retrieved_document_ids[0] in set(gold_document_ids)


def duplicate_document_rate(document_ids: list[int]) -> float:
    if not document_ids:
        return 0.0
    duplicate_count = len(document_ids) - len(set(document_ids))
    return duplicate_count / len(document_ids)


def retrieval_cutoff_violation_count(
    references: list[dict[str, Any]],
    retrieval_cutoff_date: str | None,
) -> int:
    if not retrieval_cutoff_date:
        return 0
    count = 0
    for reference in references:
        issued_date = normalize_date(reference.get("issued_date"))
        if issued_date and issued_date > retrieval_cutoff_date:
            count += 1
    return count


def build_judge_prompt(
    question: str,
    answer: str,
    references: list[dict[str, Any]],
    expected_answer: str | None = None,
) -> str:
    reference_text = "\n\n".join(
        f"[{index}] document_id={ref.get('document_id')} title={ref.get('title')}\n"
        f"{ref.get('text')}"
        for index, ref in enumerate(references, start=1)
    )
    return (
        "Bạn là giám khảo đánh giá hệ thống RAG pháp luật Việt Nam. "
        "Chỉ dựa trên câu hỏi, câu trả lời và các trích đoạn được cung cấp. "
        "Hãy trả về JSON hợp lệ, không thêm markdown, theo schema: "
        '{"retrieval_relevance":0-100,"answer_groundedness":0-100,'
        '"citation_quality":0-100,"legal_usefulness":0-100,'
        '"answer_correctness":0-100,"notes":"ngắn gọn"}.\n\n'
        f"Câu hỏi:\n{question}\n\n"
        f"Câu trả lời:\n{answer}\n\n"
        f"Câu trả lời tham chiếu chính thức:\n{expected_answer or 'Không có'}\n\n"
        f"Trích đoạn truy xuất:\n{reference_text}"
    )


def parse_judge_scores(text: str) -> JudgeScores:
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).removesuffix("```").strip()
        payload = json.loads(cleaned)
        return JudgeScores(
            retrieval_relevance=_score(payload.get("retrieval_relevance")),
            answer_groundedness=_score(payload.get("answer_groundedness")),
            citation_quality=_score(payload.get("citation_quality")),
            legal_usefulness=_score(payload.get("legal_usefulness")),
            answer_correctness=_score(payload.get("answer_correctness")),
            notes=str(payload.get("notes")) if payload.get("notes") is not None else None,
        )
    except Exception:
        return JudgeScores(notes=f"Could not parse judge output: {text[:300]}")


def _score(value: Any) -> int | None:
    if value is None:
        return None
    score = int(float(value))
    return max(0, min(100, score))


async def judge_result(
    enabled: bool,
    judge_client: LlmClient,
    question: str,
    answer: str,
    references: list[dict[str, Any]],
    expected_answer: str | None,
) -> JudgeScores:
    if not enabled:
        return JudgeScores()
    prompt = build_judge_prompt(question, answer, references, expected_answer)
    try:
        output = await judge_client.generate(prompt)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return JudgeScores(notes=f"Judge failed: {type(exc).__name__}: {exc}")
    return parse_judge_scores(output)


def warn_if_judge_endpoint_looks_local(args: argparse.Namespace) -> None:
    if args.judge_provider != "openai-compatible":
        return
    base_url = args.judge_api_base_url or ""
    if "localhost" in base_url or "127.0.0.1" in base_url:
        print(
            "Warning: judge API base URL is local; ensure an OpenAI-compatible server is "
            f"running at {base_url}. Judge failures will be recorded in judge_notes.",
            file=sys.stderr,
        )


async def evaluate_question(
    rag_base_url: str,
    judge_enabled: bool,
    judge_client: LlmClient,
    case: EvaluationCase,
    top_k: int,
) -> EvaluationResult:
    response, latency_ms = await ask_rag(
        rag_base_url,
        case.question,
        top_k,
        case.retrieval_cutoff_date,
    )
    answer = response.get("answer", "")
    references = response.get("references", [])
    cited_count, coverage = citation_coverage(answer, len(references))
    document_ids = [int(ref.get("document_id")) for ref in references if ref.get("document_id")]
    chunk_ids = [str(ref.get("chunk_id")) for ref in references if ref.get("chunk_id")]
    judge = await judge_result(
        judge_enabled,
        judge_client,
        case.question,
        answer,
        references,
        case.expected_answer,
    )
    top_document_ids = ",".join(str(document_id) for document_id in document_ids)
    top_chunk_ids = ",".join(chunk_ids)
    return EvaluationResult(
        question=case.question,
        expected_answer=case.expected_answer,
        source_url=case.source_url,
        answer=answer,
        latency_ms=latency_ms,
        reference_count=len(references),
        cited_reference_count=cited_count,
        citation_coverage=round(coverage, 4),
        top_document_ids=top_document_ids,
        top_chunk_ids=top_chunk_ids,
        top_document_types=_join_reference_field(references, "document_type"),
        top_validity_statuses=_join_reference_field(references, "validity_status"),
        top_scopes=_join_reference_field(references, "scope"),
        top_issuing_authorities=_join_reference_field(references, "issuing_authority"),
        top_issued_dates=_join_reference_field(references, "issued_date"),
        top_effective_dates=_join_reference_field(references, "effective_date"),
        top_expired_dates=_join_reference_field(references, "expired_date"),
        top_external_docids=_join_reference_field(references, "external_docid"),
        gold_document_recall_at_k=_round_optional(
            recall_at_k(document_ids, case.gold_document_ids)
        ),
        gold_chunk_recall_at_k=_round_optional(recall_at_k(chunk_ids, case.gold_chunk_ids)),
        top1_gold_hit=top1_gold_hit(document_ids, case.gold_document_ids),
        duplicate_document_rate=round(duplicate_document_rate(document_ids), 4),
        retrieval_cutoff_violation_count=retrieval_cutoff_violation_count(
            references,
            case.retrieval_cutoff_date,
        ),
        judge=judge,
    )


def _round_optional(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _join_reference_field(references: list[dict[str, Any]], field: str) -> str:
    return ",".join(str(reference.get(field) or "") for reference in references)


def write_jsonl(path: Path, result: EvaluationResult) -> None:
    with path.open("a", encoding="utf-8") as file:
        row = asdict(result)
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, results: list[EvaluationResult]) -> None:
    fieldnames = [
        "question",
        "source_url",
        "latency_ms",
        "reference_count",
        "cited_reference_count",
        "citation_coverage",
        "top_document_ids",
        "top_chunk_ids",
        "top_document_types",
        "top_validity_statuses",
        "top_scopes",
        "top_issuing_authorities",
        "top_issued_dates",
        "top_effective_dates",
        "top_expired_dates",
        "top_external_docids",
        "gold_document_recall_at_k",
        "gold_chunk_recall_at_k",
        "top1_gold_hit",
        "duplicate_document_rate",
        "retrieval_cutoff_violation_count",
        "retrieval_relevance",
        "answer_groundedness",
        "citation_quality",
        "legal_usefulness",
        "answer_correctness",
        "judge_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "question": result.question,
                    "source_url": result.source_url,
                    "latency_ms": result.latency_ms,
                    "reference_count": result.reference_count,
                    "cited_reference_count": result.cited_reference_count,
                    "citation_coverage": result.citation_coverage,
                    "top_document_ids": result.top_document_ids,
                    "top_chunk_ids": result.top_chunk_ids,
                    "top_document_types": result.top_document_types,
                    "top_validity_statuses": result.top_validity_statuses,
                    "top_scopes": result.top_scopes,
                    "top_issuing_authorities": result.top_issuing_authorities,
                    "top_issued_dates": result.top_issued_dates,
                    "top_effective_dates": result.top_effective_dates,
                    "top_expired_dates": result.top_expired_dates,
                    "top_external_docids": result.top_external_docids,
                    "gold_document_recall_at_k": result.gold_document_recall_at_k,
                    "gold_chunk_recall_at_k": result.gold_chunk_recall_at_k,
                    "top1_gold_hit": result.top1_gold_hit,
                    "duplicate_document_rate": result.duplicate_document_rate,
                    "retrieval_cutoff_violation_count": result.retrieval_cutoff_violation_count,
                    "retrieval_relevance": result.judge.retrieval_relevance,
                    "answer_groundedness": result.judge.answer_groundedness,
                    "citation_quality": result.judge.citation_quality,
                    "legal_usefulness": result.judge.legal_usefulness,
                    "answer_correctness": result.judge.answer_correctness,
                    "judge_notes": result.judge.notes,
                }
            )


def print_summary(results: list[EvaluationResult]) -> None:
    if not results:
        print("No evaluation results.")
        return
    avg_latency = sum(result.latency_ms for result in results) / len(results)
    avg_refs = sum(result.reference_count for result in results) / len(results)
    avg_coverage = sum(result.citation_coverage for result in results) / len(results)
    avg_duplicate_document_rate = sum(result.duplicate_document_rate for result in results) / len(
        results
    )
    cutoff_violations = sum(result.retrieval_cutoff_violation_count for result in results)
    print("")
    print(f"Evaluated questions: {len(results)}")
    print(f"Average latency: {avg_latency:.0f} ms")
    print(f"Average references: {avg_refs:.2f}")
    print(f"Average citation coverage: {avg_coverage:.2%}")
    print(f"Average duplicate document rate: {avg_duplicate_document_rate:.2%}")
    print(f"Retrieval cutoff violations: {cutoff_violations}")
    for field in ["gold_document_recall_at_k", "gold_chunk_recall_at_k"]:
        scores = [getattr(result, field) for result in results]
        scores = [score for score in scores if score is not None]
        if scores:
            print(f"Average {field}: {sum(scores) / len(scores):.2%}")
    top1_scores = [result.top1_gold_hit for result in results if result.top1_gold_hit is not None]
    if top1_scores:
        print(f"Top-1 gold hit rate: {sum(top1_scores) / len(top1_scores):.2%}")
    for field in [
        "retrieval_relevance",
        "answer_groundedness",
        "citation_quality",
        "legal_usefulness",
        "answer_correctness",
    ]:
        scores = [getattr(result.judge, field) for result in results]
        scores = [score for score in scores if score is not None]
        if scores:
            print(f"Average {field}: {sum(scores) / len(scores):.1f}")


async def run(args: argparse.Namespace) -> None:
    warn_if_judge_endpoint_looks_local(args)
    cases = load_questions(args.questions_file, args.questions_url, args.limit)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "rag_eval_results.jsonl"
    csv_path = output_dir / "rag_eval_results.csv"
    if args.reset and jsonl_path.exists():
        jsonl_path.unlink()

    judge_client = LlmClient(
        provider=args.judge_provider,
        api_base_url=args.judge_api_base_url,
        api_key=args.judge_api_key,
        model=args.judge_model,
    )
    judge_enabled = args.judge_provider != "none"

    results: list[EvaluationResult] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case.question[:100]}")
        result = await evaluate_question(
            args.rag_base_url,
            judge_enabled,
            judge_client,
            case,
            args.top_k,
        )
        results.append(result)
        write_jsonl(jsonl_path, result)
        print(
            f"  refs={result.reference_count} citations={result.cited_reference_count} "
            f"latency={result.latency_ms}ms"
        )

    write_csv(csv_path, results)
    print_summary(results)
    print(f"JSONL: {jsonl_path}")
    print(f"CSV: {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the RAG API on Vietnamese legal questions."
    )
    parser.add_argument("--rag-base-url", default="http://localhost:8090")
    parser.add_argument("--questions-file")
    parser.add_argument("--questions-url")
    parser.add_argument("--output-dir", default="evaluation")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument(
        "--judge-provider",
        default="none",
        choices=["none", "stub", "openai-compatible"],
    )
    parser.add_argument("--judge-api-base-url")
    parser.add_argument("--judge-api-key")
    parser.add_argument("--judge-model")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
