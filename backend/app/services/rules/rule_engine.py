import os
import json
import logging
import tree_sitter
import tree_sitter_python
import tree_sitter_typescript
from typing import List, Dict, Any, Optional
from app.schemas.graph import DependencyGraphResponse
from app.schemas.parser import ParsedFile
from app.schemas.rules import RuleViolation, ArchitectureReviewResponse
from app.services.ai.ai_client import ai_client

logger = logging.getLogger(__name__)


class RuleEngine:
    def __init__(self):
        # Initialize Tree-sitter language parsers
        try:
            self.py_lang = tree_sitter.Language(tree_sitter_python.language())
            self.ts_lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
            self.tsx_lang = tree_sitter.Language(tree_sitter_typescript.language_tsx())
            
            # Map extensions to (language_name, tree_sitter_parser)
            self.lang_map = {
                ".py": ("python", self.py_lang),
                ".js": ("javascript", self.tsx_lang),
                ".jsx": ("javascript", self.tsx_lang),
                ".ts": ("typescript", self.ts_lang),
                ".tsx": ("typescript", self.tsx_lang),
                ".mjs": ("javascript", self.tsx_lang),
                ".cjs": ("javascript", self.tsx_lang)
            }
        except Exception as e:
            logger.error(f"Failed to load Tree-sitter languages in RuleEngine: {e}")
            raise

        # Load per-language pattern files from lang_patterns/ directory
        self.lang_patterns: Dict[str, dict] = {}
        self._load_lang_patterns()

        # Extension -> language name mapping for all supported languages
        self.ext_to_lang: Dict[str, str] = {
            ".py": "python",
            ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
            ".ts": "typescript", ".tsx": "typescript",
            ".dart": "dart",
            ".java": "java",
            ".kt": "kotlin", ".kts": "kotlin",
            ".swift": "swift",
            ".go": "go",
            ".rs": "rust",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
            ".c": "c",
            ".h": "c", ".hpp": "cpp",
            ".scala": "scala",
            ".ex": "elixir", ".exs": "elixir",
            ".vue": "javascript",
            ".svelte": "javascript",
            ".r": "r", ".R": "r",
            ".lua": "lua",
            ".groovy": "groovy",
        }

    def _load_lang_patterns(self):
        """Loads all per-language pattern JSON files from the lang_patterns/ directory."""
        dir_path = os.path.dirname(os.path.realpath(__file__))
        patterns_dir = os.path.abspath(os.path.join(dir_path, "..", "..", "core", "lang_patterns"))
        if not os.path.isdir(patterns_dir):
            logger.warning(f"RuleEngine: lang_patterns directory not found at {patterns_dir}. Using built-in defaults.")
            return
        for fname in os.listdir(patterns_dir):
            if fname.endswith(".json"):
                lang_name = fname.replace(".json", "")
                try:
                    with open(os.path.join(patterns_dir, fname), "r") as f:
                        self.lang_patterns[lang_name] = json.load(f)
                    logger.info(f"RuleEngine: Loaded pattern file '{fname}' for language '{lang_name}'.")
                except Exception as e:
                    logger.error(f"RuleEngine: Failed to load lang pattern '{fname}': {e}")

    def _get_lang_patterns(self, lang_name: str) -> dict:
        """Returns pattern dict for a given language, falling back to a universal default."""
        p = self.lang_patterns.get(lang_name, {})
        if p:
            return p
        # Universal fallback patterns covering common patterns across all languages
        return {
            "loop_keywords": ["for (", "for(", "for ", "while (", "while(", "forEach(", ".map(", "for {", "foreach ", "do {"],
            "db_patterns": [
                "db.", "query", "execute", "repo.", "repository.", "fetch(",
                "http.", "find", "save", "insert", "update", "select", "delete",
                "client.get", "client.post", "client.put", "request."
            ],
            "blocking_patterns": [
                "sleep(", "Thread.sleep", "Sync(", "readFileSync", "delay(",
                "time.sleep", "block_on(", "join("
            ]
        }

    def load_profile(self, clone_path: str) -> dict:
        """
        Dynamically detects framework configuration by checking files in clone_path
        and loads corresponding JSON profiles.
        """
        sentinels = {
            "pubspec.yaml": "flutter.json",
            "package.json": "express.json",
            "requirements.txt": "fastapi.json",
            "pyproject.toml": "fastapi.json"
        }
        
        selected_profile_name = "default.json"
        if clone_path and os.path.exists(clone_path):
            for file_name, profile_name in sentinels.items():
                target_path = os.path.join(clone_path, file_name)
                subfolders = ["", "backend", "frontend", "app"]
                found = False
                for sub in subfolders:
                    check_path = os.path.join(clone_path, sub, file_name) if sub else target_path
                    if os.path.exists(check_path):
                        selected_profile_name = profile_name
                        found = True
                        break
                if found:
                    break

        logger.info(f"RuleEngine: Detected framework configuration. Loading profile: '{selected_profile_name}'")

        dir_path = os.path.dirname(os.path.realpath(__file__))
        profile_path = os.path.abspath(os.path.join(dir_path, "..", "..", "core", "profiles", selected_profile_name))
        
        try:
            with open(profile_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"RuleEngine: Failed to load profile '{selected_profile_name}': {e}. Falling back to default.")
            return {
                "layers": {
                    "controller": ["controller", "route"],
                    "service": ["service"],
                    "repository": ["repository", "model", "db"]
                },
                "rules": {
                    "controller": {
                        "forbidden_imports": ["repository"]
                    },
                    "repository": {
                        "forbidden_imports": ["service", "controller"]
                    },
                    "service": {
                        "forbidden_imports": ["controller"]
                    }
                }
            }

    def get_layer(self, file_path: str, profile: dict) -> str:
        """Classifies a file path into its logical architecture layer using dynamic profile patterns."""
        path_lower = file_path.lower().replace("\\", "/")
        parts = path_lower.split("/")
        
        for layer_name, matchers in profile.get("layers", {}).items():
            for matcher in matchers:
                for part in parts:
                    if part == matcher.lower():
                        return layer_name
                    # Check dot and underscore separators (e.g. user.controller.ts)
                    subparts = part.replace("_", ".").split(".")
                    if matcher.lower() in subparts:
                        return layer_name
        return "other"

    def check_layer_boundaries(self, graph: DependencyGraphResponse, profile: dict) -> List[RuleViolation]:
        """Validates directed imports in the graph against forbidden layering rules defined in the active profile."""
        logger.info("RuleEngine: Checking layer boundary imports on Dependency Graph...")
        violations: List[RuleViolation] = []

        # Find circular dependencies
        for cycle in graph.circular_dependencies:
            logger.warning(f"RuleEngine: [CRITICAL VIOLATION] Circular dependency cycle: {' -> '.join(cycle)}")
            violations.append(RuleViolation(
                rule_name="Circular Dependency",
                severity="CRITICAL",
                file_path=cycle[0],
                line=1,
                message=f"Circular dependency path detected: {' -> '.join(cycle)}",
                suggested_fix="Refactor shared dependencies into a separate common module or inject interfaces to break the circular import cycle."
            ))

        # Check layer violations per edge
        rules = profile.get("rules", {})
        for edge in graph.edges:
            src_layer = self.get_layer(edge.source, profile)
            tgt_layer = self.get_layer(edge.target, profile)
            
            forbidden = rules.get(src_layer, {}).get("forbidden_imports", [])
            if tgt_layer in forbidden:
                logger.warning(f"RuleEngine: [CRITICAL VIOLATION] Layer Boundary Error - Module '{edge.source}' ({src_layer}) imports '{edge.target}' ({tgt_layer}) directly.")
                violations.append(RuleViolation(
                    rule_name="Layer Boundary Check",
                    severity="CRITICAL",
                    file_path=edge.source,
                    line=1,
                    message=f"Layer violation: Module '{edge.source}' ({src_layer}) imports '{edge.target}' ({tgt_layer}) directly, violating architectural boundaries.",
                    suggested_fix=f"Remove direct import of {tgt_layer} from {src_layer}. Route requests through the intermediate Service layer to preserve strict layer isolation."
                ))

        if len(violations) == 0:
            logger.info("RuleEngine: Layer boundary checks completed successfully! No violations found.")
        return violations

    async def check_ast_rules(
        self,
        file_path: str,
        content: str,
        language: str,
        parser_lang: Optional[tree_sitter.Language]
    ) -> List[RuleViolation]:
        """Parses file contents to run AST-level performance and safety checkers (uses Tree-sitter or AI fallback)."""
        # If parser_lang is not available (e.g. Dart, Java, Go, Kotlin, Swift, C#),
        # run high-speed language-aware pattern scanner (0ms latency)
        if not parser_lang:
            logger.info(f"RuleEngine: Running high-speed pattern scanner for '{file_path}' (Language: {language})")
            violations: List[RuleViolation] = []
            lines = content.splitlines()
            in_loop = False
            in_async = False
            brace_depth = 0
            loop_brace_depth = -1

            # Load language-specific patterns from lang_patterns/
            pat = self._get_lang_patterns(language)
            loop_keywords: list = pat.get("loop_keywords", [])
            db_patterns: tuple = tuple(pat.get("db_patterns", []))
            blocking_patterns: tuple = tuple(pat.get("blocking_patterns", []))
            async_keywords = ["async ", "async{", "Future<", "Task<", "Promise<", "async def", "async fn", "asyncio"]

            for idx, line in enumerate(lines, 1):
                clean_line = line.strip()

                # Track brace depth for loop scope detection
                brace_depth += clean_line.count("{") - clean_line.count("}")

                # Detect loop start
                if any(k in clean_line for k in loop_keywords):
                    in_loop = True
                    loop_brace_depth = brace_depth

                # Detect loop end (brace-based scope exit)
                if in_loop and brace_depth < loop_brace_depth:
                    in_loop = False
                    loop_brace_depth = -1

                # Detect async scope
                if any(k in clean_line for k in async_keywords):
                    in_async = True

                # Rule A: N+1 Query / HTTP Operation in Loops
                if in_loop and any(pat in clean_line.lower() for pat in db_patterns):
                    violations.append(RuleViolation(
                        rule_name="N+1 Query Detector",
                        severity="HIGH",
                        file_path=file_path,
                        line=idx,
                        message=f"Performance bottleneck: {language.capitalize()} — query/HTTP operation inside loop: '{clean_line[:80]}'",
                        suggested_fix="Extract the operation outside the loop. Collect all needed IDs first, then batch fetch/save in a single call."
                    ))

                # Rule B: Blocking Call in Async Scope
                if in_async and any(pat in clean_line for pat in blocking_patterns):
                    violations.append(RuleViolation(
                        rule_name="Blocking Async Scope",
                        severity="MEDIUM",
                        file_path=file_path,
                        line=idx,
                        message=f"Concurrency issue: {language.capitalize()} — synchronous blocking call inside async scope: '{clean_line[:80]}'",
                        suggested_fix="Replace the blocking call with its non-blocking async counterpart for this language/framework."
                    ))

            if len(violations) == 0:
                logger.info(f"RuleEngine: Pattern checks completed for '{file_path}'. No violations found.")
            return violations

        logger.info(f"RuleEngine: Checking AST rules for '{file_path}' (Language: {language})")
        violations: List[RuleViolation] = []
        code_bytes = content.encode("utf-8")
        
        parser = tree_sitter.Parser(parser_lang)
        tree = parser.parse(code_bytes)

        # Load language-specific patterns for AST scanner
        pat = self._get_lang_patterns(language)
        db_patterns: tuple = tuple(pat.get("db_patterns", [
            "db.", "query", "execute", "repo.", "repository.", "prisma.",
            "find", "save", "insert", "delete", "update"
        ]))
        blocking_patterns_lang: tuple = tuple(pat.get("blocking_patterns", [
            "time.sleep", "requests.get", "fs.readFileSync", "execSync", "subprocess.run"
        ]))

        def traverse(node: tree_sitter.Node, loop_depth: int = 0, async_depth: int = 0):
            # Check loop nodes
            is_loop = False
            if node.type in ("for_statement", "while_statement", "for_in_statement", "do_statement", "for_each_statement"):
                is_loop = True
                loop_depth += 1

            # Check async function scopes
            is_async = False
            if node.type == "function_definition":  # Python
                for c in node.children:
                    if c.type == "async":
                        is_async = True
                if is_async:
                    async_depth += 1
            elif node.type in ("function_declaration", "arrow_function", "method_definition"):  # TS/JS
                # Check for async modifier keyword
                for c in node.children:
                    if c.type == "async":
                        is_async = True
                if is_async:
                    async_depth += 1

            # Check calls
            if node.type in ("call", "call_expression"):
                func_node = node.child_by_field_name("function")
                if not func_node and node.children:
                    func_node = node.children[0]

                if func_node:
                    call_text = code_bytes[func_node.start_byte:func_node.end_byte].decode("utf-8", errors="ignore")
                    
                    # Rule A: N+1 Database Operation in Loops
                    if loop_depth > 0:
                        if any(pat in call_text.lower() for pat in db_patterns):
                            logger.warning(f"RuleEngine: [HIGH VIOLATION] N+1 Query in '{file_path}' at line {node.start_point[0] + 1}: call '{call_text}'")
                            violations.append(RuleViolation(
                                rule_name="N+1 Query Detector",
                                severity="HIGH",
                                file_path=file_path,
                                line=node.start_point[0] + 1,
                                message=f"Performance bottleneck: Database or Repository operation '{call_text}' called inside a loop block.",
                                suggested_fix=f"Extract '{call_text}' outside the loop block. Collect IDs and use bulk fetch/batch operations before iterating."
                            ))

                    # Rule B: Blocking Sync calls in Async Contexts (language-aware)
                    if async_depth > 0:
                        if any(pat in call_text for pat in blocking_patterns_lang):
                            logger.warning(f"RuleEngine: [MEDIUM VIOLATION] Blocking call '{call_text}' in async scope in '{file_path}' at line {node.start_point[0] + 1}")
                            violations.append(RuleViolation(
                                rule_name="Blocking Async Scope",
                                severity="MEDIUM",
                                file_path=file_path,
                                line=node.start_point[0] + 1,
                                message=f"Concurrency issue: Synchronous blocking call '{call_text}' executed inside an async scope.",
                                suggested_fix=f"Replace '{call_text}' with its non-blocking async counterpart for {language} (e.g. asyncio.sleep / httpx for Python, fs.promises / execa for Node.js)."
                            ))

            # Recursively traverse children
            for child in node.children:
                traverse(child, loop_depth, async_depth)

        traverse(tree.root_node)
        if len(violations) == 0:
            logger.info(f"RuleEngine: AST rule checks completed successfully for '{file_path}'. No violations found.")
        return violations

    async def run_review(
        self,
        owner: str,
        repo: str,
        parsed_files: List[ParsedFile],
        graph: DependencyGraphResponse,
        clone_path: str
    ) -> ArchitectureReviewResponse:
        """Runs the rule engine review over all files and computes the final architecture score."""
        profile = self.load_profile(clone_path)
        logger.info(f"RuleEngine: Starting architecture scan for repository '{owner}/{repo}'...")
        violations: List[RuleViolation] = []

        # 1. Run Graph-based boundary checks
        violations.extend(self.check_layer_boundaries(graph, profile))

        # 2. Run AST-based checks on files (all languages supported)
        for parsed in parsed_files:
            ext = os.path.splitext(parsed.file_path)[1].lower()
            mapped = self.lang_map.get(ext)

            if not mapped:
                # Use ext_to_lang for broader language name coverage (Dart, Go, Kotlin, etc.)
                lang_name = self.ext_to_lang.get(ext, ext.replace(".", ""))
                parser_lang = None
            else:
                lang_name, parser_lang = mapped

            full_file_path = os.path.join(clone_path, parsed.file_path)
            
            if os.path.exists(full_file_path):
                violations.extend(await self.check_ast_rules(
                    file_path=parsed.file_path,
                    content=open(full_file_path, "r", encoding="utf-8", errors="ignore").read(),
                    language=lang_name,
                    parser_lang=parser_lang
                ))

        # 3. Calculate architectural health score
        score = 100.0
        for v in violations:
            if v.severity == "CRITICAL":
                score -= 15
            elif v.severity == "HIGH":
                score -= 10
            elif v.severity == "MEDIUM":
                score -= 5
            else:
                score -= 2

        score = max(0.0, score)
        if len(violations) == 0:
            logger.info(f"RuleEngine: Excellent code quality! Repository '{owner}/{repo}' passed all architectural rule checks successfully.")
        logger.info(f"RuleEngine: Completed review for '{owner}/{repo}'. Score: {score}/100. Total violations found: {len(violations)}")

        return ArchitectureReviewResponse(
            owner=owner,
            repo=repo,
            score=round(score, 1),
            violations=violations
        )


# Singleton instance
rule_engine = RuleEngine()
