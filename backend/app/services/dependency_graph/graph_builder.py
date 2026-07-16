import os
import logging
import networkx as nx
from typing import List, Dict, Any, Optional, Set, Tuple
from app.schemas.parser import ParsedFile
from app.schemas.graph import DependencyGraphResponse, GraphNode, GraphEdge, NodeMetrics

logger = logging.getLogger(__name__)


class DependencyGraphBuilder:
    def resolve_ts_import(self, source_file: str, import_src: str, all_files_set: Set[str]) -> Optional[str]:
        """Resolves TypeScript/JavaScript import sources to physical file paths in the codebase."""
        # 1. Handle Next.js/React aliases (e.g. '@/lib/api' -> 'src/lib/api')
        if import_src.startswith("@/"):
            target = import_src.replace("@/", "src/", 1)
        elif import_src.startswith("."):
            # 2. Resolve relative imports
            src_dir = os.path.dirname(source_file)
            target = os.path.normpath(os.path.join(src_dir, import_src))
        else:
            # External package/library (out of graph scope)
            return None

        # Clean double slashes on Windows/Unix
        target = target.replace("\\", "/")

        # 3. Check for direct file match with extension
        for ext in (".ts", ".tsx", ".js", ".jsx", ".d.ts"):
            test_path = target + ext
            if test_path in all_files_set:
                return test_path

        # 4. Check for folder index file matches (e.g. 'utils' -> 'utils/index.ts')
        for index_suffix in ("/index.ts", "/index.tsx", "/index.js", "/index.jsx"):
            test_path = target + index_suffix
            if test_path in all_files_set:
                return test_path

        return None

    def resolve_py_import(self, source_file: str, import_src: str, all_files_set: Set[str]) -> Optional[str]:
        """Resolves Python dot-notation absolute and relative imports to file paths in the codebase."""
        if import_src.startswith("."):
            # 1. Relative import (e.g. '..services.user' or '.models')
            stripped = import_src.lstrip(".")
            num_dots = len(import_src) - len(stripped)
            
            source_parts = source_file.split("/")
            # Go up folder levels based on number of dots
            if len(source_parts) > num_dots:
                parent_dir = "/".join(source_parts[:-num_dots])
                suffix_path = stripped.replace(".", "/")
                base_path = f"{parent_dir}/{suffix_path}" if parent_dir else suffix_path
            else:
                base_path = stripped.replace(".", "/")
        else:
            # 2. Absolute import (e.g. 'app.core.config')
            base_path = import_src.replace(".", "/")

        # Clean path separators
        base_path = os.path.normpath(base_path).replace("\\", "/")

        # 3. Check combinations from specific to broad (since from x.y import z could mean file is x/y.py)
        parts = base_path.split("/")
        for i in range(len(parts), 0, -1):
            test_path = "/".join(parts[:i])
            
            # Case A: Check direct python file (.py)
            file_test = test_path + ".py"
            if file_test in all_files_set:
                return file_test
                
            # Case B: Check package init file (__init__.py)
            init_test = test_path + "/__init__.py"
            if init_test in all_files_set:
                return init_test

        return None

    def build_graph(self, owner: str, repo: str, parsed_files: List[ParsedFile]) -> DependencyGraphResponse:
        """
        Builds a directed dependency graph using NetworkX, computes
        coupling metrics for each file, and detects circular dependency cycles.
        """
        all_files_set = {f.file_path for f in parsed_files}
        
        # Initialize directed graph
        G = nx.DiGraph()
        G.add_nodes_from(all_files_set)

        # Map files by path for easy language identification
        file_lang_map = {f.file_path: f.language for f in parsed_files}

        # Populate graph edges (directed connections: source imports target)
        for parsed_file in parsed_files:
            source = parsed_file.file_path
            lang = parsed_file.language
            
            for imp in parsed_file.imports:
                target_resolved = None
                
                # Check TS vs Python resolving rules
                if lang == "python":
                    target_resolved = self.resolve_py_import(source, imp.source, all_files_set)
                else:
                    target_resolved = self.resolve_ts_import(source, imp.source, all_files_set)
                
                # Add edge if the target file resides within our scanned workspace codebase
                if target_resolved and target_resolved in all_files_set and target_resolved != source:
                    G.add_edge(source, target_resolved)

        # 1. Circular Dependencies (Cycle Detection)
        #nx.simple_cycles returns lists of cycle paths, e.g. [A, B, A]
        cycles = list(nx.simple_cycles(G))

        # 2. Node Metrics calculation
        nodes_list: List[GraphNode] = []
        total_instability = 0.0
        active_nodes_count = 0

        for node in all_files_set:
            # Afferent Coupling (Ca): In-degree (how many files import this node)
            ca = G.in_degree(node)
            
            # Efferent Coupling (Ce): Out-degree (how many files this node imports)
            ce = G.out_degree(node)
            
            # Instability (I) = Ce / (Ca + Ce)
            if (ca + ce) > 0:
                instability = float(ce) / (ca + ce)
                total_instability += instability
                active_nodes_count += 1
            else:
                instability = 0.0

            nodes_list.append(
                GraphNode(
                    file_path=node,
                    language=file_lang_map.get(node, "unknown"),
                    metrics=NodeMetrics(
                        afferent_coupling=ca,
                        efferent_coupling=ce,
                        instability=round(instability, 3)
                    )
                )
            )

        # 3. Assemble Edge Schemas
        edges_list = [
            GraphEdge(source=u, target=v)
            for u, v in G.edges()
        ]

        average_instability = (
            round(total_instability / active_nodes_count, 3)
            if active_nodes_count > 0
            else 0.0
        )

        return DependencyGraphResponse(
            owner=owner,
            repo=repo,
            total_files=len(all_files_set),
            nodes=nodes_list,
            edges=edges_list,
            circular_dependencies=cycles,
            average_instability=average_instability
        )


# Singleton instance
graph_builder = DependencyGraphBuilder()
