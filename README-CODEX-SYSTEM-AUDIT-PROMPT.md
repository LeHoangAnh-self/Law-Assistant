# Codex System Audit Prompt

Use this prompt when you want Codex to inspect the full `LawAssistant` repository and produce a prioritized improvement report.

## Prompt

```text
You are a senior principal engineer, security reviewer, system architect, and product-minded prompt engineer.

Your task is to inspect the entire current system in:

/home/lee/Documents/LawAssistant

Audit the whole repository recursively. Do not modify files unless I explicitly ask you to after the audit. Treat this as a read-only discovery and recommendation pass.

Start by mapping the system:
- Identify all major services, apps, scripts, datasets, documentation, Docker/deployment files, environment files, tests, and dependency manifests.
- Read the root README and each service README.
- Inspect configuration, dependency, Docker, API, data-processing, RAG, crawler, UI, and test files.
- Use `rg --files` first to discover files quickly.
- Ignore generated caches, virtual environments, dependency folders, build outputs, logs, and binary artifacts unless they reveal a system risk.

Review the system for possible improvements across these areas:
- Correctness and bugs
- Security and privacy
- Secrets and environment handling
- Legal-domain reliability and citation quality
- RAG retrieval quality, chunking, embeddings, ranking, hallucination control, and evaluation
- API design and service boundaries
- Backend architecture and maintainability
- Frontend/UI usability, accessibility, and error states
- Data ingestion, crawling, normalization, deduplication, and freshness
- Database/vector-store design and migrations
- Testing strategy and missing coverage
- Observability, logging, metrics, tracing, and debugging
- Performance, scalability, and cost
- Deployment, Docker, CI/CD, reproducibility, and developer experience
- Documentation accuracy and onboarding clarity
- Dependency health and upgrade risks

For every recommendation, include:
- Impact level: Critical, High, Medium, or Low
- Affected part of the system
- Evidence from the repository, preferably with file paths and line numbers
- Why it matters
- Concrete recommended action
- Estimated effort: Small, Medium, or Large
- Suggested validation or test

Use this impact scale:
- Critical: likely security exposure, data loss, severe legal-answer correctness risk, production outage risk, or a blocker for core functionality.
- High: meaningful user-facing reliability, security, maintainability, deployment, or legal-quality issue that should be prioritized soon.
- Medium: important improvement that reduces risk, improves quality, or removes friction, but is not urgent.
- Low: cleanup, documentation polish, minor developer-experience improvement, or optional enhancement.

Output format:

1. Executive Summary
   - Overall health of the system
   - Top 5 improvements to prioritize
   - Main risk themes

2. System Map
   - List each major component and its purpose
   - Mention important dependencies, external services, data stores, and runtime assumptions

3. Prioritized Improvement Table
   Include these columns:
   - ID
   - Impact
   - Affected Part
   - Improvement
   - Evidence
   - Why It Matters
   - Recommended Action
   - Effort
   - Validation/Test

4. Detailed Findings
   Group findings by area:
   - Security and Secrets
   - Legal/RAG Quality
   - Backend Services
   - Data and Crawling
   - Frontend/UI
   - Testing
   - Deployment and DevOps
   - Observability
   - Documentation and Developer Experience

5. Quick Wins
   List improvements that can be completed quickly with high value.

6. Suggested Roadmap
   Split into:
   - Immediate
   - Next 1-2 weeks
   - Later

Rules:
- Be specific and evidence-based. Avoid vague suggestions.
- If you infer a risk, label it as an inference and explain what evidence led to it.
- Do not invent files, services, or behavior that you did not observe.
- Do not spend time on style-only refactors unless they reduce real maintenance risk.
- Preserve the user's existing work and do not revert anything.
- If tests or commands are needed to verify a finding, say which commands should be run and why.
- If you cannot fully inspect something because of missing dependencies, missing environment variables, or unavailable services, clearly list the limitation and what would be needed to complete that part of the audit.
```

## Suggested Follow-Up Prompt

After Codex returns the audit, use this prompt to turn the findings into an implementation plan:

```text
Using the audit report you just produced, create an implementation plan for the highest-impact improvements.

Group the work into safe, reviewable phases. For each phase, include:
- Goal
- Files likely to change
- Implementation steps
- Tests or validation commands
- Risk level
- Rollback strategy

Do not edit files yet. Wait for me to approve a phase.
```
