# System Architecture Document: AI Architecture Code Reviewer

This document details the architectural layout, modules, data models, and processing pipelines for the AI Architecture Code Reviewer system.

---

## 1. High-Level Architecture Overview

The system follows a decoupled, async-first **Modular Monolith** architecture. High-latency processes (like cloning code, AST building, graph processing, and LLM reasoning) are delegated to background workers to ensure the FastAPI Web API remains highly responsive.

```mermaid
graph TD
    subgraph Client Layer
        FE[Next.js + TypeScript Frontend]
    end

    subgraph API & Event Ingestion Layer
        API[FastAPI Web API Gateway]
        GH[GitHub Webhooks / REST API]
    end

    subgraph Queue & Cache Layer
        Broker[Redis Message Broker]
    end

    subgraph Async Compute Workers
        Worker[Celery Analysis Worker]
        AST[Tree-sitter Parser Engine]
        GraphEng[NetworkX Dependency Engine]
        RAGEng[pgvector RAG Retrieval]
        LLM[AI Reasoning Agent]
    end

    subgraph Data Storage Layer
        DB[(PostgreSQL + pgvector)]
    end

    GH -->|Webhook Event / REST| API
    FE -->|GraphQL / REST / WebSockets| API
    API -->|Write metadata / Read Reports| DB
    API -->|Enqueue Task| Broker
    Broker -->|Fetch Job| Worker
    Worker -->|Shallow clone & parse| AST
    Worker -->|Analyze graph & rules| GraphEng
    Worker -->|Fetch similar failure cases| RAGEng
    Worker -->|Summarize and rank risks| LLM
    Worker -->|Save report findings| DB
    RAGEng -->|Vector Query| DB
```

---

## 2. Component Layout & Module Design

### 2.1 Next.js Frontend
- **Framework**: Next.js (using App Router) + Tailwind CSS + shadcn/ui.
- **Visuals**: Dependency relationships and circular loops visualized via D3.js or Cytoscape.js.
- **WebSockets**: Real-time status update feeds from FastAPI when Celery processes a PR.

### 2.2 FastAPI Backend API
- **Entrypoint**: `app/main.py`
- **Routing**: Separated by functional domain (e.g., `/api/v1/github`, `/api/v1/repositories`, `/api/v1/analysis`).
- **ORM & DB Connection**: SQLAlchemy 2.0 with asyncpg driver for asynchronous connections.

### 2.3 Celery Worker Tasks
- **Clone Task**: Handles repository checkout with shallow cloning (`git clone --depth 1`).
- **AST Parser Task**: Parses files using language-specific Tree-sitter bindings.
- **Analysis Execution**: Evaluates AST structure against predefined rule classes and graph cycles.
- **RAG & Reasoning**: Aggregates metadata, queries vector store for historical bugs, prompts the LLM, and publishes reviews.

---

## 3. Database Schema Design (SQLAlchemy Models)

```mermaid
erDiagram
    REPOSITORY ||--o{ PULL_REQUEST : has
    PULL_REQUEST ||--o{ ANALYSIS_REPORT : analyzed-by
    ANALYSIS_REPORT ||--o{ ARCHITECTURAL_FINDING : contains
    HISTORICAL_INCIDENT ||--o{ CODE_EMBEDDING : embeds
    
    REPOSITORY {
        int id PK
        string github_id
        string name
        string full_name
        boolean is_active
        datetime created_at
    }

    PULL_REQUEST {
        int id PK
        int repo_id FK
        int pr_number
        string title
        string state
        string head_sha
        string base_sha
        datetime updated_at
    }

    ANALYSIS_REPORT {
        int id PK
        int pr_id FK
        string status "pending / processing / completed / failed"
        float risk_score "overall calculated score"
        datetime completed_at
    }

    ARCHITECTURAL_FINDING {
        int id PK
        int report_id FK
        string risk_level "Critical / High / Medium / Low"
        string category "coupling / circular-dependency / n+1-query / pattern-violation"
        string file_path
        int line_number
        string description
        string remediation
        float confidence
    }

    HISTORICAL_INCIDENT {
        int id PK
        string incident_id
        string summary
        string root_cause
        string resolution
    }

    CODE_EMBEDDING {
        int id PK
        int incident_id FK
        vector embedding "pgvector size 1536/384"
        string code_snippet
        string source_file
    }
```

---

## 4. Architectural Analysis Pipeline Flow

Here is the sequential flow of how a PR undergoes review:

```mermaid
sequenceDiagram
    autonumber
    actor Developer
    participant GH as GitHub App
    participant API as FastAPI Web Server
    participant Redis as Redis Broker
    participant Celery as Celery Worker
    participant DB as PostgreSQL
    participant LLM as LLM API

    Developer->>GH: Open Pull Request
    GH->>API: Deliver Webhook (pull_request.opened)
    API->>DB: Log PR metadata and create Pending Analysis
    API->>Redis: Enqueue 'analyze_pr' task
    API-->>GH: HTTP 202 Accepted
    
    Note over Celery, DB: Worker starts processing
    Celery->>GH: Fetch PR Changed Files & Diff (via Client Token)
    Celery->>Celery: Parse changed files via Tree-sitter (AST)
    Celery->>Celery: Build Dependency & Call Graph
    Celery->>Celery: Run Rule Engine (layer checking, N+1 patterns)
    Celery->>DB: Fetch past code embeddings similar to PR changes
    DB-->>Celery: Return relevant historical bugs/incident logs
    Celery->>LLM: Pass diffs, patterns, and historical context
    LLM-->>Celery: Return prioritized risk explanations & suggested fixes
    Celery->>DB: Save findings & update Analysis status to Completed
    Celery->>GH: Post architectural review comments directly to the PR
```

---

## 5. Security & Edge Mitigation Architecture

1.  **Code Isolation**: AST parsing is purely static and does not execute the target codebase. Cloned code is confined to ephemeral scratch paths that are cleaned up inside a `finally:` block.
2.  **Access Token Least Privilege**: GitHub Installation Access Tokens are scoped strictly to the repository being reviewed, with short-lived 1-hour expirations.
3.  **LLM Input Size Management**: PR diffs are filtered to skip dependencies (like `node_modules` or `.venv`) and non-code assets. Code blocks are chunked to fit LLM context lengths.
