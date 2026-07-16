import json
import logging
import httpx
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class AIClient:
    async def generate_pr_review(
        self,
        diffs: str,
        violations: List[str],
        related_incidents: List[str],
        score: float
    ) -> str:
        """
        Generates a comprehensive architectural code review critique in Markdown
        using the configured LLM provider.
        """
        if settings.LLM_PROVIDER == "ollama":
            return await self._generate_ollama_review(diffs, violations, related_incidents, score)
        else:
            raise ValueError(f"Unsupported or unconfigured LLM provider '{settings.LLM_PROVIDER}'.")

    async def _generate_ollama_review(
        self,
        diffs: str,
        violations: List[str],
        related_incidents: List[str],
        score: float
    ) -> str:
        """Connects to local Ollama instance to generate the architectural review."""
        system_prompt = (
            "You are Antigravity, an expert AI Software Architect reviewing a developer's Pull Request.\n"
            "Your task is to analyze the changed files (Git diffs), static analysis violations, and RAG post-mortem contexts.\n"
            "Provide a clear architectural critique in Markdown format.\n"
            "Include:\n"
            "1. Architectural Risk Score (0-100) and brief review summary.\n"
            "2. Critical concerns or rule violations found (with file path and lines).\n"
            "3. Actionable code refactorings or fixes.\n"
            "Keep the feedback direct, technical, and objective."
        )

        violations_str = "\n".join(f"- {v}" for v in violations) if violations else "No static violations found."
        incidents_str = "\n".join(f"- {inc}" for inc in related_incidents) if related_incidents else "No related incidents matching historical outages found."

        user_prompt = (
            f"### Repository Architectural Score: {score}/100\n\n"
            f"### Changed Code Diffs:\n{diffs}\n\n"
            f"### Deterministic Rule Violations:\n{violations_str}\n\n"
            f"### Historical Post-Mortem Incident Context:\n{incidents_str}\n\n"
            f"Generate the architectural PR review:"
        )

        payload = {
            "model": settings.OLLAMA_GEN_MODEL,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.OLLAMA_GEN_URL,
                    json=payload,
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # Ollama return: {"response": "..."}
                    if "response" in data:
                        return data["response"]
                    else:
                        raise ValueError(f"Ollama response missing 'response' text: {data}")
                else:
                    raise httpx.HTTPStatusError(
                        f"Ollama returned status code {response.status_code}",
                        request=response.request,
                        response=response
                    )
        except Exception as e:
            logger.error(f"Failed to query Ollama for review generation: {e}")
            raise e

    async def scan_file_ast_rules(
        self,
        file_path: str,
        content: str
    ) -> List[dict]:
        """
        Queries the local Ollama model in JSON format to perform a structural check
        on code files of any language (including C, C++, Go, Rust, Java, etc.).
        """
        system_prompt = (
            "You are an expert Static Code Analyzer. Your task is to scan the provided source code file and identify ONLY two specific architectural violations:\n\n"
            "1. \"N+1 Query Detector\" (Severity: HIGH)\n"
            "   - Trigger: A database query, SQL statement, or ORM operation (e.g., '.find()', '.query()', 'db.select()', 'session.save()', 'prisma.') executed inside a loop (like 'for', 'while', 'forEach', 'map', or list comprehension).\n\n"
            "2. \"Blocking Async Scope\" (Severity: MEDIUM)\n"
            "   - Trigger: A synchronous blocking function (e.g., 'sleep()', 'time.sleep()', 'fs.readFileSync()', 'execSync()') executed inside the body of an 'async' function.\n\n"
            "CONSTRAINTS:\n"
            "- Do not output any markdown code blocks, summary text, introduction, or explanations.\n"
            "- You must respond ONLY with a valid JSON array of objects matching the schema below.\n"
            "- If no violations are found, return an empty JSON array: []\n\n"
            "JSON Schema:\n"
            "[\n"
            "  {\n"
            "    \"rule_name\": \"N+1 Query Detector\" or \"Blocking Async Scope\",\n"
            "    \"severity\": \"HIGH\" or \"MEDIUM\",\n"
            "    \"line\": <line_number_integer>,\n"
            "    \"message\": \"<description of what was called and why it is a violation>\"\n"
            "  }\n"
            "]"
        )

        user_prompt = (
            f"File Path: {file_path}\n"
            f"Source Code Content:\n"
            f"```\n{content}\n```"
        )

        payload = {
            "model": settings.OLLAMA_GEN_MODEL,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json"
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.OLLAMA_GEN_URL,
                    json=payload,
                    timeout=30.0
                )
                if response.status_code == 200:
                    data = response.json()
                    response_text = data.get("response", "[]").strip()
                    parsed = json.loads(response_text)
                    if isinstance(parsed, list):
                        return parsed
                    logger.warning(f"Ollama returned non-list JSON payload: {response_text}")
                else:
                    logger.warning(f"Ollama returned status code {response.status_code} in scan_file_ast_rules")
        except Exception as e:
            logger.error(f"Failed to query Ollama for file scan on '{file_path}': {e}")
            raise e

    def _get_mock_review(self, diffs: str, violations: List[str], score: float) -> str:
        """Returns a cleanly formatted fallback review if the LLM cannot be accessed."""
        violations_str = "\n".join(f"- {v}" for v in violations) if violations else "No static violations found."
        
        risk = "LOW"
        if score < 70:
            risk = "CRITICAL"
        elif score < 90:
            risk = "MEDIUM"
            
        return (
            "## 🤖 Antigravity Architecture Code Review (Offline Mock)\n\n"
            "### 📊 Summary & Score\n"
            f"- **Architectural Score**: {score}/100\n"
            f"- **Risk Assessment**: {risk}\n"
            "- *Note: Local Ollama server is offline or unreachable. Displaying deterministic engine results.*\n\n"
            "### ⚠️ Violations & Structural Concerns\n"
            f"{violations_str}\n\n"
            "### 💡 Actionable Fixes\n"
            "1. **Clean Architecture Boundary**: Avoid importing `src/db/db.ts` or database utilities directly inside controllers. Instead, inject a Service class layer (e.g. `src/services/applyJob.service.ts`) to handle query execution.\n"
            "2. **N+1 Loops**: Ensure queries are batched using `In` operators or bulk inserts rather than executing model saves inside loop blocks."
        )


# Singleton instance
ai_client = AIClient()
