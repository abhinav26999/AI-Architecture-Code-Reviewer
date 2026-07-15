from pydantic import BaseModel
from typing import List, Optional, Dict


class ImportSymbol(BaseModel):
    name: str
    alias: Optional[str] = None


class ImportMetadata(BaseModel):
    source: str
    symbols: List[ImportSymbol] = []
    alias: Optional[str] = None
    line: int


class FunctionMetadata(BaseModel):
    name: str
    start_line: int
    end_line: int
    parameters: List[str] = []
    calls: List[str] = []
    is_async: bool = False
    docstring: Optional[str] = None


class ClassMetadata(BaseModel):
    name: str
    bases: List[str] = []
    start_line: int
    end_line: int
    methods: List[FunctionMetadata] = []
    docstring: Optional[str] = None


class ParsedFile(BaseModel):
    file_path: str
    language: str  # python, javascript, typescript
    imports: List[ImportMetadata] = []
    classes: List[ClassMetadata] = []
    functions: List[FunctionMetadata] = []  # Top-level functions


class ParserTestRequest(BaseModel):
    code: str
    language: str  # python, javascript, typescript


class ParseRepoRequest(BaseModel):
    owner: str
    repo: str
    installation_id: Optional[int] = None
    branch: Optional[str] = None


class ParseRepoResponse(BaseModel):
    owner: str
    repo: str
    total_files: int
    parsed_files: List[ParsedFile]
    parsing_errors: Dict[str, str] = {}
