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

logger = logging.getLogger(__name__)


class RuleEngine:
    def __init__(self):
        # Initialize Tree-sitter language parsers
        try:
            self.py_lang = tree_sitter.Language(tree_sitter_python.language())
            self.ts_lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
            self.tsx_lang = tree_sitter.Language(tree_sitter_typescript.language_tsx())
            
            # Map extensions
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
                message=f"Circular dependency path detected: {' -> '.join(cycle)}"
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
                    message=f"Layer violation: Module '{edge.source}' ({src_layer}) imports '{edge.target}' ({tgt_layer}) directly, violating architectural boundaries."
                ))

        if len(violations) == 0:
            logger.info("RuleEngine: Layer boundary checks completed successfully! No violations found.")
        return violations

    def check_ast_rules(
        self,
        file_path: str,
        content: str,
        language: str,
        parser_lang: tree_sitter.Language
    ) -> List[RuleViolation]:
        """Parses file contents to run AST-level performance and safety checkers."""
        logger.info(f"RuleEngine: Checking AST rules for '{file_path}' (Language: {language})")
        violations: List[RuleViolation] = []
        code_bytes = content.encode("utf-8")
        
        parser = tree_sitter.Parser(parser_lang)
        tree = parser.parse(code_bytes)

        # Local patterns to look for
        db_patterns = ("db.", "query", "execute", "repo.", "repository.", "prisma.", "find", "save", "insert", "delete", "update")
        blocking_patterns_py = ("time.sleep", "requests.get", "requests.post", "urllib.request", "subprocess.run")
        blocking_patterns_ts = ("fs.readFileSync", "fs.writeFileSync", "execSync", "sleepSync")

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
                                message=f"Performance bottleneck: Database or Repository operation '{call_text}' called inside a loop block."
                            ))

                    # Rule B: Blocking Sync calls in Async Contexts
                    if async_depth > 0:
                        if language == "python":
                            if any(pat in call_text for pat in blocking_patterns_py):
                                logger.warning(f"RuleEngine: [MEDIUM VIOLATION] Blocking call '{call_text}' in async scope in '{file_path}' at line {node.start_point[0] + 1}")
                                violations.append(RuleViolation(
                                    rule_name="Blocking Async Scope",
                                    severity="MEDIUM",
                                    file_path=file_path,
                                    line=node.start_point[0] + 1,
                                    message=f"Concurrency issue: Synchronous blocking call '{call_text}' executed inside an async scope."
                                ))
                        else:  # JS/TS
                            if any(pat in call_text for pat in blocking_patterns_ts):
                                logger.warning(f"RuleEngine: [MEDIUM VIOLATION] Blocking FS/subprocess call '{call_text}' in async scope in '{file_path}' at line {node.start_point[0] + 1}")
                                violations.append(RuleViolation(
                                    rule_name="Blocking Async Scope",
                                    severity="MEDIUM",
                                    file_path=file_path,
                                    line=node.start_point[0] + 1,
                                    message=f"Concurrency issue: Synchronous blocking filesystem/shell call '{call_text}' executed inside an async scope."
                                ))

            # Recursively traverse children
            for child in node.children:
                traverse(child, loop_depth, async_depth)

        traverse(tree.root_node)
        if len(violations) == 0:
            logger.info(f"RuleEngine: AST rule checks completed successfully for '{file_path}'. No violations found.")
        return violations

    def run_review(
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

        # 2. Run AST-based checks on files
        for parsed in parsed_files:
            ext = os.path.splitext(parsed.file_path)[1]
            mapped = self.lang_map.get(ext.lower())
            if not mapped:
                continue

            lang_name, parser_lang = mapped
            full_file_path = os.path.join(clone_path, parsed.file_path)
            
            if os.path.exists(full_file_path):
                try:
                    violations.extend(self.check_ast_rules(
                        file_path=parsed.file_path,
                        content=open(full_file_path, "r", encoding="utf-8", errors="ignore").read(),
                        language=lang_name,
                        parser_lang=parser_lang
                    ))
                except Exception as e:
                    logger.error(f"Failed to scan AST rules on file {parsed.file_path}: {e}")

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
