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
        score: float,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        ollama_url: Optional[str] = None
    ) -> str:
        """
        Generates a comprehensive architectural code review critique in Markdown
        using the configured or user-specified LLM provider (Ollama, OpenAI, Gemini).
        """
        llm_provider = (provider or settings.LLM_PROVIDER).lower().strip()

        system_prompt = (
            "You are an expert AI Principal Software Architect performing an automated Pull Request Code Review.\n"
            "Your objective is to analyze modified code diffs, AST static analysis violations, and historical post-mortem incident context to deliver a precise, production-grade architectural review in GitHub Flavored Markdown.\n\n"
            "Structure your review as follows:\n"
            "## 🤖 Automated Architecture Code Review\n\n"
            "### 📊 Score & Risk Assessment\n"
            "- **Architectural Score**: <Score>/100\n"
            "- **Risk Assessment**: <CRITICAL | HIGH | MEDIUM | LOW>\n"
            "- **Executive Summary**: 2-3 sentences summarizing overall impact and code quality.\n\n"
            "### 🔍 Critical Issues & Violations\n"
            "- Detail specific code anti-patterns, layer boundary breaches, N+1 query loops, or security flaws found in the diffs.\n\n"
            "### 💡 Actionable Refactoring & Fixes\n"
            "- Provide clear code snippets showing exact refactorings to fix identified concerns.\n\n"
            "Maintain a technical, constructive, and objective tone."
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

        try:
            if llm_provider == "openai":
                return await self._generate_openai_review(
                    api_key=api_key,
                    model=model or "gpt-4o-mini",
                    user_prompt=user_prompt,
                    system_prompt=system_prompt
                )
            elif llm_provider == "gemini":
                return await self._generate_gemini_review(
                    api_key=api_key,
                    model=model or "gemini-1.5-flash",
                    user_prompt=user_prompt,
                    system_prompt=system_prompt
                )
            elif llm_provider == "ollama":
                return await self._generate_ollama_review(
                    model=model or settings.OLLAMA_GEN_MODEL,
                    ollama_url=ollama_url or settings.OLLAMA_GEN_URL,
                    user_prompt=user_prompt,
                    system_prompt=system_prompt
                )
            else:
                raise ValueError(f"Unsupported LLM provider '{llm_provider}'. Please configure Ollama, OpenAI, or Gemini in Settings.")
        except Exception as e:
            logger.error(f"AI generation failed for provider '{llm_provider}': {e}")
            raise RuntimeError(f"AI Review Generation Failed ({llm_provider.upper()}): {str(e)}")

    async def _generate_ollama_review(
        self,
        model: str,
        ollama_url: str,
        user_prompt: str,
        system_prompt: str
    ) -> str:
        """Connects to local Ollama instance to generate the architectural review."""
        gen_url = ollama_url
        if "/api/" not in gen_url:
            gen_url = f"{ollama_url.rstrip('/')}/api/generate"

        payload = {
            "model": model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                gen_url,
                json=payload,
                timeout=300.0
            )
            
            if response.status_code == 200:
                data = response.json()
                if "response" in data:
                    return data["response"]
                raise ValueError(f"Ollama response missing 'response' field: {data}")
            else:
                raise httpx.HTTPStatusError(
                    f"Ollama returned HTTP {response.status_code}",
                    request=response.request,
                    response=response
                )

    async def _generate_openai_review(
        self,
        api_key: Optional[str],
        model: str,
        user_prompt: str,
        system_prompt: str
    ) -> str:
        """Connects to OpenAI API using user API key or environment key."""
        key = api_key or getattr(settings, "OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OpenAI API key missing. Please configure OpenAI Key in settings.")

        headers = {
            "Authorization": f"Bearer {key.strip()}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }

        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=45.0
            )
            if res.status_code == 200:
                data = res.json()
                return data["choices"][0]["message"]["content"]
            elif res.status_code == 401:
                raise ValueError("Invalid OpenAI API Key (HTTP 401 Unauthorized).")
            elif res.status_code == 429:
                raise ValueError("OpenAI API Rate Limit Exceeded or Out of Credits (HTTP 429).")
            else:
                raise ValueError(f"OpenAI API error ({res.status_code}): {res.text}")

    async def _generate_gemini_review(
        self,
        api_key: Optional[str],
        model: str,
        user_prompt: str,
        system_prompt: str
    ) -> str:
        """Connects to Google Gemini API using user API key."""
        key = api_key or getattr(settings, "GEMINI_API_KEY", "")
        if not key:
            raise ValueError("Google Gemini API key missing. Please configure Gemini Key in settings.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key.strip()}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_prompt}\n\n{user_prompt}"}
                    ]
                }
            ]
        }

        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=45.0)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                raise ValueError(f"Gemini returned empty text candidate: {data}")
            elif res.status_code == 400 or res.status_code == 403:
                raise ValueError(f"Invalid Gemini API Key or model error ({res.status_code}).")
            else:
                raise ValueError(f"Gemini API error ({res.status_code}): {res.text}")

    async def scan_file_ast_rules(
        self,
        file_path: str,
        content: str
    ) -> List[dict]:
        """
        Queries local Ollama model in JSON format to perform a structural check
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
            "    \"message\": \"<description of what was called and why it is a violation>\",\n"
            "    \"suggested_fix\": \"<actionable AI refactoring advice explaining step-by-step how to fix this violation in this code>\"\n"
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
                    timeout=5.0
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
            logger.warning(f"Ollama AI scan skipped for '{file_path}' (AI service offline or timed out): {e}")
            return []

    async def generate_violation_fix_suggestion(
        self,
        rule_name: str,
        message: str,
        file_path: str,
        code_snippet: Optional[str] = None
    ) -> str:
        """
        Uses AI to generate a precise, custom refactoring code fix for any architectural violation.
        """
        system_prompt = (
            "You are an expert AI Principal Software Architect. Your task is to provide a concise, actionable 2-3 sentence refactoring solution "
            "for an architectural code violation found during static analysis."
        )
        user_prompt = (
            f"Rule Violation: {rule_name}\n"
            f"File: {file_path}\n"
            f"Issue Message: {message}\n"
            f"Code Snippet:\n```\n{code_snippet or 'N/A'}\n```\n\n"
            "Provide the recommended refactoring fix:"
        )

        try:
            return await self.generate_pr_review(
                diffs=user_prompt,
                violations=[message],
                related_incidents=[],
                score=90.0
            )
        except Exception:
            return f"Refactor '{file_path}' to resolve {rule_name}: extract database loops into batch calls or replace blocking calls with async alternatives."


# Singleton instance
ai_client = AIClient()
