# LawAssistant System Audit and Phased Planning Prompt

Date: 2026-07-01

Repository: `/home/lee/Documents/LawAssistant`

Prepared as a read-only audit and planning handoff. The original audit inspected the repository recursively and did not modify source files.

---

## 1. Executive Summary

Overall, LawAssistant is a strong local prototype with clear separation between the Spring Boot law service, FastAPI RAG service, crawlers, reusable datasets, and a local demo UI. The architecture already contains many of the right building blocks for a Vietnamese legal assistant: structured legal crawling, document normalization, vector search, reranking, citation verification, and Q&A benchmark artifacts.

The system is not yet production-ready. Several components still assume a trusted local environment, while the product goal requires high legal reliability, controlled administrative access, reproducible deployment, data freshness, and strong citation quality.

Top 5 improvements to prioritize:

1. Lock down unauthenticated admin, import, bulk indexing, and demo proxy surfaces.
2. Fix import-to-index consistency so RAG never indexes partial, stale, or orphaned data.
3. Replace partial/in-memory lexical retrieval with a production retrieval and evaluation path.
4. Use structured legal anchors and versioned corpus metadata in runtime RAG, not only offline artifacts.
5. Add reproducible builds, integration tests, secrets hygiene, observability, and deployment hardening.

Main risk themes:

- Local-development credentials and trusted-local API assumptions.
- Import, cache, queue, and vector-store consistency gaps.
- Legal answer quality risks from stale chunks, partial lexical recall, and citation verification that is mostly syntactic.
- Data freshness, provenance, privacy, and licensing governance.
- Missing integration tests across MySQL, Redis, RabbitMQ, Qdrant, Celery, and API boundaries.
- Deployment and dependency reproducibility gaps.

---

## 2. System Map

| Component | Purpose | Important Dependencies / Assumptions |
|---|---|---|
| Root docs and data | Project overview, runnable local flow, shared `data_usable` artifacts | Git LFS for parquet; large local artifacts; README labels current state as prototype/local |
| `law-service` | Spring Boot API for legal document search/detail/import and embedding event publishing | Java 19, Spring Boot 3.5, MySQL, Flyway, Redis cache, RabbitMQ, Apache Parquet/Hadoop |
| `rag-service` | FastAPI RAG API, embedding, Qdrant indexing, reranking, LLM prompting, Celery worker, RabbitMQ bridge | Qdrant, Redis/Celery, RabbitMQ, SentenceTransformers, CrossEncoder, OpenAI-compatible LLM, optional Langfuse/OTel |
| `QnA_crawler` | Crawls Vietnamese government legal Q&A and exports benchmark/training parquet | MySQL, HTTP crawling, DOCX parsing, optional document DB matching |
| `dataset/vietnamese_legal_documents/creation/crawler` | Crawls/parses Vietnamese legal documents, PDF/OCR, structured context export | MySQL, Playwright/HTTP, PyMuPDF/Tesseract optional, Thuvienphapluat/Google fallback |
| `data_usable` | Current legal corpus, RAG chunks, Q&A exports, audit files | Large parquet/SQL artifacts; some tracked via Git LFS; local `context.parquet` ignored |
| `UI_test` | Local FastAPI/static demo UI and proxy to RAG API | Browser localStorage, optional OpenAI key test endpoint, in-memory conversation store |

External services and runtime assumptions:

- MySQL stores law-service data and crawler outputs.
- Redis is used for Spring cache and Celery broker/backing queue assumptions.
- RabbitMQ carries document embedding events from law-service to RAG indexing.
- Qdrant stores legal document chunk vectors.
- Hugging Face/SentenceTransformers model downloads are needed for embeddings and reranking.
- OpenAI-compatible LLM credentials are needed for non-stub answers.
- Langfuse/OpenTelemetry are optional and currently lightly integrated.
- Crawlers depend on external legal/government websites and fallback sources.

---

## 3. Prioritized Improvement Table

| ID | Impact | Affected Part | Improvement | Evidence | Why It Matters | Recommended Action | Effort | Validation/Test |
|---|---|---|---|---|---|---|---|---|
| F1 | Critical | API/admin surfaces | Add auth and admin isolation | Import accepts caller path at `law-service/src/main/java/com/lawassistant/lawservice/importer/ProvidedDataImportController.java:20`; bulk embeddings at `law-service/src/main/java/com/lawassistant/lawservice/document/LegalDocumentController.java:79`; RAG ask/proxy public at `rag-service/app/rag_service/main.py:32` | If exposed, callers can trigger imports, read service-accessible paths, or force expensive indexing | Require auth, separate admin profile/network, path allowlist, and rate limits | Medium | Unauthenticated import/bulk endpoints return `401/403`; admin token path works |
| F2 | High | Secrets/config | Remove production defaults for credentials | MySQL/Rabbit defaults at `law-service/src/main/resources/application.properties:4` and `:17`; compose creds at `law-service/docker-compose.yml:3` and `:20` | Default `law/law` and exposed ports are risky outside localhost | Use required env vars in non-local profiles, generated dev secrets, private Docker networks | Small | Production profile fails fast without secrets; local compose remains documented |
| F3 | High | Import/index pipeline | Publish embedding events only after successful import | Import order at `ProvidedDataImportService.java:61`; events emitted during metadata import at `ProvidedDataImportService.java:145` | RAG can index title-only or stale content before content and relationships are loaded | Make import transactional/job-based; emit events after commit; update indexing status | Medium | Integration test imports with `publishEmbeddingEvents=true` and verifies worker sees full content |
| F4 | High | Vector store | Delete stale chunks and validate collection schema | Default delete disabled at `rag-service/app/rag_service/config.py:18`; replacement logic at `rag-service/app/rag_service/vector_store.py:52`; collection check only existence at `vector_store.py:28` | Old chunks can survive reindex and pollute legal answers | Always replace by document/version, validate vector size/distance, use aliases for rebuilds | Medium | Reindex doc with fewer chunks; assert old chunk IDs disappear |
| F5 | High | Retrieval | Replace capped in-memory BM25 | BM25 corpus limit `200000` at `rag-service/app/rag_service/bm25_retriever.py:38`; cached forever at `bm25_retriever.py:104`; corpus is about 1.2M chunks in root README | Lexical recall misses most chunks and becomes stale after indexing | Use OpenSearch, Tantivy, SQLite FTS, or Qdrant sparse vectors; invalidate on reindex | Large | Known docs past first 200k chunks are retrievable; MRR/recall improves |
| F6 | High | Legal/RAG eval | Make evaluation match production retrieval | Eval uses dense vector search only at `rag-service/app/rag_service/evaluation.py:173`; production pipeline is hybrid at `rag-service/app/rag_service/pipeline.py:106` | Offline metrics may not predict real answer quality | Run the same retrieval/rerank/citation path against golden Q&A; add CI threshold | Medium | CI fails on retrieval/citation regression |
| F7 | High | Legal citation quality | Use structured anchors/context in runtime RAG | Runtime indexes document detail text at `rag-service/app/rag_service/indexing.py:32`; dataset has structured context/anchors in `data_usable` and root README | Legal answers need article/clause/point precision, not only document-level chunks | Index `law_chunks.parquet`/anchors or expose structured context through law-service | Large | Queries requiring clause/point citations return anchored references |
| F8 | High | Freshness/provenance | Add corpus versioning and freshness checks | README notes freshness depends on artifact updates at `README.md:358`; crawler stores source hashes at `dataset/.../repository.py:70` | Users need to know whether legal answers are current | Generate corpus manifest, source dates, hash/version, UI/API freshness banner | Medium | API exposes corpus version/date; stale corpus check fails deploy |
| F9 | High | Search/API performance | Use real full-text search | Current query uses `LIKE %query%` at `LegalDocumentRepository.java:16`; fulltext indexes exist at `law-service/src/main/resources/db/migration/V1__init.sql:27` | Leading wildcards bypass indexes and degrade as corpus grows | Use MySQL fulltext or external search; add keyset pagination | Medium | `EXPLAIN` uses indexes; latency measured on full corpus |
| F10 | High | Testing | Add integration coverage | Only Spring context test at `law-service/src/test/java/.../LawServiceApplicationTests.java:6`; RAG mostly unit tests | Import, queues, Qdrant, cache, and DB behavior are where failures will hide | Testcontainers for MySQL/Redis/Rabbit/Qdrant; end-to-end import-to-answer test | Large | CI runs Java/Python integration suite |
| F11 | Medium | Data/privacy | Review tracked Q&A SQL/backups and training artifacts | Q&A exporter includes question/answer text at `QnA_crawler/src/qna_crawler/exporter.py:183`; `.gitignore` does not broadly ignore SQL backups | Legal Q&A may include personal facts; SQL backups are harder to govern in git | PII/license scan, remove unnecessary backups, document dataset policy | Small | Secret/PII scanner passes before release |
| F12 | Medium | Demo UI | Guard OpenAI key test and in-memory conversations | Key test endpoint at `UI_test/app.py:111`; global conversations at `UI_test/app.py:20` | If exposed, service can be abused as a key validator and leaks session state across users | Dev-only flag, bind localhost, TTL/session isolation, rate limit | Small | Endpoint disabled unless explicit dev env |
| F13 | Medium | UI security | Sanitize external source URLs | `href` uses crawler-provided source URL at `UI_test/static/document.js:200` | Escaping HTML is not enough for unsafe URL schemes | Allow only `http/https`; render invalid URLs as text; add CSP | Small | `javascript:` URL fixture is inert |
| F14 | Medium | RAG API | Allowlist filters | Request accepts arbitrary filter dict at `rag-service/app/rag_service/models.py:7`; vector filter uses keys directly at `vector_store.py:309` | Unknown filters silently degrade retrieval and complicate API contracts | Define supported filters and reject unknown fields | Small | Unknown filter returns `422` |
| F15 | Medium | Observability | Add structured retrieval and queue telemetry | OTel hook is minimal at `rag-service/app/rag_service/observability.py:1` | Legal answer debugging requires retrieved docs, scores, model, retries, and queue state | Request IDs, structured logs, spans, metrics, redaction policy | Medium | Trace shows rewrite, retrieval, rerank, LLM, verifier timings |
| F16 | Medium | Prompt/retrieval maintainability | Move hardcoded legal heuristics into versioned rules/evals | Broad non-legal prompt instructions at `rag-service/app/rag_service/prompting.py:72`; hardcoded tax/labor rules at `pipeline.py:294` | Hidden prompt/rule drift is hard to review and test | Externalize rules, snapshot prompts, add golden tests per domain | Medium | Prompt snapshot and domain regression tests pass |
| F17 | Medium | Citation verifier | Add semantic support checking | Verifier mainly checks citation syntax/existence at `rag-service/app/rag_service/citation_verifier.py:88` | A cited source can exist while the claim is unsupported | Add quote/span or entailment checks for cited claims | Medium/Large | Adversarial answer with valid citation but false claim is rejected |
| F18 | Medium | Queues | Add DLQ and indexing status | Bridge nacks without requeue at `rag-service/app/rag_service/rabbit_bridge.py:28`; worker retries transients at `rag-service/app/rag_service/worker.py:30` | Failed indexing can vanish without user-visible status | DLQ, retry policy, status callback to law-service, queue dashboards | Medium | Poison message lands in DLQ and document status shows failed |
| F19 | Medium | Crawling | Make legal crawler job claiming concurrency-safe | Claim selects then updates at `dataset/vietnamese_legal_documents/creation/crawler/src/law_crawler/site_crawler.py:169` | Multiple workers can duplicate work or race attempts | Use atomic claim or `FOR UPDATE SKIP LOCKED` | Medium | Concurrent worker test claims each URL once |
| F20 | Medium | Build/deps | Add lockfiles and align runtimes | RAG installs unlocked package set at `rag-service/Dockerfile:11`; Java 19 at `law-service/pom.xml:30` | Reproducibility and dependency CVE response are weak | Use `uv.lock` or pip-tools, Maven wrapper/OWASP scan, Java 21 LTS plan | Medium | Fresh clone build produces same dependency graph |
| F21 | Medium | Deployment | Harden containers/compose | RAG Docker runs default root user at `rag-service/Dockerfile:1`; compose only starts Qdrant at `rag-service/docker-compose.yml:1` | Local compose is not a production deployment boundary | Non-root users, healthchecks, resource limits, persistent volumes, prod compose/k8s manifests | Medium | Healthchecks and restart behavior verified |
| F22 | Low/Medium | Importer correctness | Fix legacy `content.parquet` schema handling | Projection omits `id` at `ProvidedDataImportService.java:34`; importer later accepts `id` at `ProvidedDataImportService.java:175` | Legacy files documented as `content.parquet` may import null IDs | Include optional `id` in projection or schema-discover content files | Small | Unit test imports both `id` and `document_id` schemas |
| F23 | Low/Medium | Importer data consistency | Replace relationships instead of only inserting | Relationship import uses `insert ignore` at `ProvidedDataImportService.java:240` | Removed upstream relationships can remain forever | Delete/replace relationships per snapshot or document | Small | Reimport without relationship removes old edge |
| F24 | Low/Medium | Docs/DX | Document faster content extraction path | Importer can scan huge `context.parquet`; extraction script exists at `scripts/extract_current_new_content.py:13` | Importing a 5GB context file is slow and fragile for onboarding | Make `content.parquet` generation an explicit pre-import step | Small | Fresh setup follows documented path successfully |

---

## 4. Detailed Findings by Area

### Security and Secrets

- F1, F2, F11, F12, F13, and F14 are the main security issues.
- No committed live `.env` secret was observed in the inspected source files; real local `.env` files are ignored, which is good.
- The main risk is that default credentials and trusted-local endpoints can become production vulnerabilities if deployed without guardrails.

### Legal and RAG Quality

- F4 through F8, F16, and F17 are the core legal-answer risks.
- The system has thoughtful retrieval heuristics, reranking, and tests, but runtime retrieval is not yet tightly tied to structured legal anchors, full-corpus lexical search, enforceable citation support, and freshness metadata.

### Backend Services

- F3, F9, F22, and F23 are the main correctness risks in `law-service`.
- Importing, caching, eventing, and relationship replacement need stronger transactional semantics.

### Data and Crawling

- The crawlers are capable and modular, but freshness, source policy, PII/license handling, and concurrent job claiming need tightening before automation at scale.
- Data artifacts should have explicit provenance manifests and release/version metadata.

### Frontend/UI

- `UI_test` is useful as a local demo.
- It should remain dev-only unless auth, URL sanitization, session isolation, and rate limiting are added.

### Testing

- RAG has meaningful unit coverage.
- Spring coverage is very thin.
- The missing layer is integration testing across MySQL, RabbitMQ, Redis, Qdrant, Celery, and the importer.

### Deployment and DevOps

- Docker and compose files are local-development oriented.
- Production needs locked dependencies, non-root containers, healthchecks, secrets management, CI, and clearer service composition.

### Observability

- Current instrumentation is minimal.
- Legal RAG needs structured logs and traces for query rewrite, retrieval, reranking, LLM calls, citation verification, queue failures, and corpus version.

### Documentation and Developer Experience

- The root README is helpful.
- Documentation should distinguish local prototype defaults from production requirements and make the recommended data preparation/import path unambiguous.

---

## 5. Quick Wins

1. Add a simple admin token guard to import and bulk embedding endpoints.
2. Fail fast on default credentials outside the `local` profile.
3. Set Qdrant document replacement to delete stale chunks by default.
4. Add filter allowlisting for RAG requests.
5. Sanitize UI source links to `http/https`.
6. Add `id` to the importer content projection.
7. Add tests for `content.parquet` schema variants and relationship replacement.
8. Add a documented `content.parquet` extraction step before Java import.
9. Add a secret/PII scan for tracked SQL and Q&A artifacts.

---

## 6. Suggested Roadmap

### Immediate

- Lock down admin endpoints and demo-only UI routes.
- Fix import event ordering and stale Qdrant chunk deletion.
- Add corpus version/freshness metadata to RAG responses.
- Run dependency and secret/PII scans.

### Next 1-2 Weeks

- Add Testcontainers integration tests for import, queue, cache, and Qdrant indexing.
- Replace capped BM25 with a full-corpus lexical/sparse retrieval layer.
- Add production-shaped evaluation using the actual retrieval, rerank, and citation pipeline.
- Add structured logs, request IDs, queue metrics, and retrieval traces.

### Later

- Move runtime RAG to structured legal anchors and versioned corpus artifacts.
- Build a reproducible crawler-to-dataset-to-index pipeline with manifests.
- Harden Docker/Kubernetes deployment, secrets, healthchecks, and CI/CD.
- Add semantic citation verification and broader legal-domain golden sets.

---

## 7. Audit Limitations

Builds and tests were not run during the read-only audit because they may create `target`, cache, database, or vector-store artifacts.

Recommended validation commands:

```bash
cd /home/lee/Documents/LawAssistant/law-service && mvn test
cd /home/lee/Documents/LawAssistant/rag-service && pytest
cd /home/lee/Documents/LawAssistant/QnA_crawler && pytest -q
cd /home/lee/Documents/LawAssistant/dataset/vietnamese_legal_documents/creation/crawler && pytest -q
```

Binary/parquet contents were not deeply inspected. A complete data governance pass should sample and scan parquet and SQL artifacts for PII, provenance, licensing, and freshness.

---

# Enhanced Phased Planning Prompt

Use the prompt below to ask a coding/planning agent to convert this audit into an implementation roadmap. It is designed to produce a few manageable phases with clear deliverables, validation, and decision points.

```text
You are a senior principal engineer, security reviewer, system architect, legal-domain RAG architect, and product-minded technical lead.

Repository:
/home/lee/Documents/LawAssistant

Objective:
Turn the existing LawAssistant audit into a practical phased execution plan. Do not start implementation yet. First produce a clear plan that divides the work into a few phases that can be implemented, reviewed, tested, and shipped safely.

Context:
The repository contains:
- law-service: Spring Boot legal document API, importer, MySQL, Redis, RabbitMQ, Flyway.
- rag-service: FastAPI RAG API, Qdrant vector store, Celery/Redis worker, RabbitMQ bridge, embeddings, reranking, prompt, citation verifier, evaluation tools.
- QnA_crawler: government legal Q&A crawler and benchmark/training exporter.
- dataset/vietnamese_legal_documents/creation/crawler: legal document crawler/parser/OCR/export pipeline.
- data_usable: large legal corpus, RAG chunks, Q&A artifacts, audit files.
- UI_test: local FastAPI/static demo UI and proxy.

Primary risks to address:
1. Unauthenticated admin/import/bulk-index/demo surfaces.
2. Default local credentials and weak production secret handling.
3. Import-to-index inconsistency, stale cache, stale Qdrant chunks, and missing indexing status.
4. RAG retrieval gaps: capped BM25, stale lexical cache, missing structured anchor use, insufficient legal citation support.
5. Evaluation not matching production retrieval.
6. Missing integration tests across MySQL, Redis, RabbitMQ, Qdrant, Celery, and APIs.
7. Data freshness, provenance, PII/license governance, and crawler reliability.
8. Weak observability, reproducibility, Docker hardening, and CI/CD.

Planning requirements:
- Read the repository before planning. Use `rg --files` first.
- Preserve existing work. Do not revert unrelated changes.
- Do not modify files during the planning pass unless explicitly asked.
- Separate work into 4-6 phases.
- Each phase must be independently valuable and testable.
- Put security and correctness foundations before feature expansion.
- Avoid broad refactors unless they reduce a concrete risk from the audit.
- Identify dependencies between phases.
- Include acceptance criteria and validation commands for each phase.
- Include likely files/modules to touch for each phase.
- Include estimated effort: Small, Medium, Large.
- Include risk level: Critical, High, Medium, Low.
- Include rollback strategy when a phase changes runtime behavior.
- Include open questions that need user/product decisions.

Recommended phase shape:

Phase 0 - Baseline and Safety Net
- Confirm current build/test status.
- Add or document safe local test commands.
- Establish branch, baseline logs, and known failing tests.
- No behavioral changes unless necessary to unblock tests.

Phase 1 - Security and Admin Boundary
- Protect import, bulk embedding, demo key-test, and privileged endpoints.
- Remove production credential defaults.
- Add request/rate limits where appropriate.
- Add URL sanitization in UI.
- Validation: unauthenticated requests fail; local dev path remains usable.

Phase 2 - Import, Cache, Queue, and Vector Consistency
- Make import event emission happen after successful import.
- Delete stale vector chunks on reindex.
- Add indexing status and dead-letter handling.
- Evict or refresh law-service detail cache after import.
- Add tests for content/context schema variants and relationship replacement.

Phase 3 - Legal RAG Retrieval and Citation Quality
- Replace capped BM25 or introduce full-corpus lexical/sparse retrieval.
- Wire structured anchors/context into runtime retrieval.
- Add corpus version/freshness metadata.
- Improve citation verification beyond syntax-only checks.
- Add golden legal queries and Q&A retrieval regression tests.

Phase 4 - Data Pipeline, Freshness, and Governance
- Add corpus manifest with source hashes, crawl/export timestamps, and artifact versions.
- Define PII/license scan workflow for Q&A and SQL/parquet artifacts.
- Improve crawler job claiming and source policy documentation.
- Make content extraction/import workflow reproducible.

Phase 5 - Production Readiness, Observability, and Developer Experience
- Add structured logs, request IDs, metrics, traces, queue dashboards.
- Add Docker hardening: non-root containers, healthchecks, resource limits, persistent volumes.
- Add lockfiles/SBOM/dependency scanning.
- Add CI pipeline for unit, integration, lint, security, and RAG eval checks.
- Update onboarding and production deployment docs.

Output format:

1. Executive Plan
   - Overall strategy.
   - Recommended number of phases.
   - Key sequencing decisions.

2. Phase-by-Phase Roadmap
   For each phase include:
   - Goal.
   - Scope.
   - Out of scope.
   - Affected files/modules.
   - Implementation tasks.
   - Acceptance criteria.
   - Validation commands.
   - Rollback strategy.
   - Effort estimate.
   - Risks and mitigations.

3. Dependency Map
   - Which phases depend on earlier work.
   - Which tasks can run in parallel.

4. Test and Evaluation Plan
   - Unit tests.
   - Integration tests.
   - RAG retrieval/citation eval.
   - Security tests.
   - Manual smoke tests.

5. Decision Log
   - Product/security/legal decisions needed before implementation.
   - Recommended defaults if the user does not specify.

6. First Implementation Sprint
   - Select the smallest high-value subset to implement first.
   - List exact files likely to change.
   - List exact commands to run for validation.

Rules:
- Be specific and evidence-based.
- Do not invent repository behavior.
- If a risk is inferred, label it as an inference and cite the evidence.
- Prefer conservative changes aligned with the existing architecture.
- Keep the plan practical enough for incremental pull requests.
- Do not start implementation until the user approves the phase plan.
```

