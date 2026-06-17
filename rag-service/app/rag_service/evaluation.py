import argparse
import asyncio
import csv
import json
import re
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
                )
            )
        else:
            raise ValueError("Questions must be strings or objects with a question field")
    return cases[:limit] if limit else cases


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
    output = await judge_client.generate(prompt)
    return parse_judge_scores(output)


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
    judge = await judge_result(
        judge_enabled,
        judge_client,
        case.question,
        answer,
        references,
        case.expected_answer,
    )
    top_document_ids = ",".join(str(ref.get("document_id")) for ref in references)
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
        judge=judge,
    )


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
    print("")
    print(f"Evaluated questions: {len(results)}")
    print(f"Average latency: {avg_latency:.0f} ms")
    print(f"Average references: {avg_refs:.2f}")
    print(f"Average citation coverage: {avg_coverage:.2%}")
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
