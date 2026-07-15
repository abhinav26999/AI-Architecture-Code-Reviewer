from pydantic import BaseModel
from typing import List, Dict, Any


class NodeMetrics(BaseModel):
    afferent_coupling: int  # Ca: number of modules importing this module
    efferent_coupling: int  # Ce: number of modules this module imports
    instability: float       # I = Ce / (Ca + Ce)


class GraphNode(BaseModel):
    file_path: str
    language: str
    metrics: NodeMetrics


class GraphEdge(BaseModel):
    source: str  # The file doing the importing
    target: str  # The file being imported


class DependencyGraphResponse(BaseModel):
    owner: str
    repo: str
    total_files: int
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    circular_dependencies: List[List[str]]
    average_instability: float
