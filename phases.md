# Development Roadmap & Implementation Phases (phases.md)

This document outlines the step-by-step phased roadmap for building the **AI Architecture Code Reviewer** system.

---

## 🗺️ Phase Roadmap Overview

```text
┌────────────────────────┐
│ Phase 1: GitHub Auth   │ ◄── [Completed]
└───────────┬────────────┘
            ▼
┌────────────────────────┐
│ Phase 2: AST Parser    │
└───────────┬────────────┘
            ▼
┌────────────────────────┐
│ Phase 3: Graph Engine  │
└───────────┬────────────┘
            ▼
┌────────────────────────┐
│ Phase 4: Rule Engine   │
└───────────┬────────────┘
            ▼
┌────────────────────────┐
│ Phase 5: pgvector RAG  │
└───────────┬────────────┘
            ▼
┌────────────────────────┐
│ Phase 6: AI reasoning  │
└───────────┬────────────┘
            ▼
┌────────────────────────┐
│ Phase 7: Next.js UI    │
└───────────┬────────────┘
            ▼
┌────────────────────────┐
│ Phase 8: Celery Async  │
└───────────┬────────────┘
```

---

## 🚀 Phase Details

### Phase 1: Foundational Setup & GitHub Auth (Completed)
- **Goal**: Initialize backend, establish virtual environment, set up settings management, configure short-lived token auth client, and pull repositories and PR file diff metadata.
- **Key Deliverables**:
  - `requirements.txt` environment configuration.
  - Pydantic settings loading (`app/core/config.py`).
  - Async GitHub API Client (`app/services/github/github_client.py`).
  - Auth test and PR/files fetch routes (`app/api/routes/github.py`).

### Phase 2: AST Ingestion & Parser Engine
- **Goal**: Parse repository code statically using Tree-sitter to extract structural symbols.
- **Key Deliverables**:
  - Integrate `tree-sitter` (Python and TypeScript bindings).
  - Create file-parser service extracting imports, class declarations, inheritance hierarchies, function definitions, database queries, and decorator annotations.
- **Verification**: Run parser script on local test directories and print JSON representing extracted structures.

### Phase 3: Dependency Graph Engine
- **Goal**: Build a directed dependency graph representing import structures and module relationships.
- **Key Deliverables**:
  - Construct graph representation using the `NetworkX` library.
  - Implement cycle detection to flag circular dependencies.
  - Calculate coupling metrics (e.g., instability, afferent/efferent coupling).
- **Verification**: Assert graph cycles are correctly identified in a test project containing circular modules.

### Phase 4: Structural Rule Engine
- **Goal**: Implement deterministic architectural checks based on layers, performance, and code safety.
- **Key Deliverables**:
  - Create validation rules checking layer imports (e.g. controllers importing db directly).
  - Implement N+1 query detectors scanning AST for db requests within loops.
  - Implement async block-scanners checking for blocking synchronous functions in async routes.
- **Verification**: Run rule checks against test files containing intentional rule violations.

### Phase 5: pgvector & RAG Integration
- **Goal**: Implement historical codebase failure search capability.
- **Key Deliverables**:
  - Setup database migrations for `pgvector` extension integration.
  - Implement code embedding generation pipeline using a local or open-source embedding model.
  - Create ingestion script for crawling historical GitHub issues, pull requests, and post-mortem logs.
- **Verification**: Perform similarity search queries on vector database and verify relevant matches.

### Phase 6: AI Reasoning and Review System
- **Goal**: Synthesize deterministic finding parameters, historical similarities, and diff files using LLMs.
- **Key Deliverables**:
  - LLM pipeline integration with context building and prompt templates.
  - Design Risk Ranking rules (Low, Medium, High, Critical).
  - Implement GitHub PR commenting client posting results back to reviews.
- **Verification**: Trigger a mock review and check if the GitHub App publishes reviews on the test repository.

### Phase 7: Next.js Frontend Dashboard
- **Goal**: Provide a user interface for repository management and PR architectural visualizations.
- **Key Deliverables**:
  - Init Next.js + Tailwind CSS + shadcn/ui.
  - Create interactive dashboards representing PR analysis findings.
  - Implement Interactive Dependency Graph visualizer (using D3.js or Cytoscape.js).
- **Verification**: Run frontend locally, login, select repository, and view review reports.

### Phase 8: Async Worker Queue (Productionizing)
- **Goal**: Offload heavy computational analysis workloads using distributed queue architectures.
- **Key Deliverables**:
  - Integrate Celery worker pipelines using Redis as a task broker.
  - Implement WebSocket message triggers updating frontend with worker process statuses.
  - Dockerize database, backend, workers, and frontend with `docker-compose.yml`.
- **Verification**: Process multiple concurrent webhooks and verify tasks are queued and processed asynchronously.
