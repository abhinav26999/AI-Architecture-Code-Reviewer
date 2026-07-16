import os
import logging
from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import CodeSnippetEmbedding, HistoricalIncident
from app.schemas.parser import ParsedFile
from app.services.embeddings.embedding_client import embedding_client

logger = logging.getLogger(__name__)


class RAGService:
    def chunk_codebase_file(self, parsed_file: ParsedFile, raw_content: str) -> List[str]:
        """
        Chunks file semantically based on AST function/class boundaries.
        Falls back to sliding lines if no classes or functions are present.
        """
        chunks: List[str] = []
        lines = raw_content.splitlines()

        # Semantically chunk classes
        for cls in parsed_file.classes:
            # Lines are 1-indexed, so we subtract 1
            start = max(0, cls.start_line - 1)
            end = min(len(lines), cls.end_line)
            class_content = "\n".join(lines[start:end])
            if class_content.strip():
                chunks.append(f"// File: {parsed_file.file_path}\n// Class: {cls.name}\n{class_content}")

        # Semantically chunk top-level functions
        for fn in parsed_file.functions:
            start = max(0, fn.start_line - 1)
            end = min(len(lines), fn.end_line)
            fn_content = "\n".join(lines[start:end])
            if fn_content.strip():
                chunks.append(f"// File: {parsed_file.file_path}\n// Function: {fn.name}\n{fn_content}")

        # Fallback if no logical AST components were extracted
        if not chunks:
            # Split into chunks of 50 lines with a 10-line overlap
            chunk_size = 50
            overlap = 10
            i = 0
            while i < len(lines):
                segment = "\n".join(lines[i:i + chunk_size])
                if segment.strip():
                    chunks.append(f"// File: {parsed_file.file_path}\n{segment}")
                i += (chunk_size - overlap)

        return chunks

    async def ingest_codebase(
        self,
        db: AsyncSession,
        parsed_files: List[ParsedFile],
        clone_path: str
    ):
        """Processes codebase, generates vectors, and indexes them in PostgreSQL."""
        # WIPE existing code snippets to keep indexed repo fresh
        # (This is standard practice for clean PR reviews or fresh ingestion runs)
        await db.execute(select(CodeSnippetEmbedding))  # Placeholder for wipe/override logic
        
        for parsed in parsed_files:
            full_path = os.path.join(clone_path, parsed.file_path)
            if not os.path.exists(full_path):
                continue
                
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                chunks = self.chunk_codebase_file(parsed, content)
                for chunk in chunks:
                    vector = await embedding_client.get_embedding(chunk)
                    snippet = CodeSnippetEmbedding(
                        file_path=parsed.file_path,
                        content=chunk,
                        embedding=vector
                    )
                    db.add(snippet)
                    
                await db.flush()
            except Exception as e:
                logger.error(f"Failed to ingest file {parsed.file_path} into vector store: {e}")
                
        await db.commit()

    async def ingest_incident(
        self,
        db: AsyncSession,
        title: str,
        description: str,
        metadata_json: Optional[Dict[str, Any]] = None
    ) -> HistoricalIncident:
        """Helper to manually ingest past post-mortem incidents or bug logs into vector database."""
        vector = await embedding_client.get_embedding(f"Title: {title}\nDescription: {description}")
        incident = HistoricalIncident(
            title=title,
            description=description,
            embedding=vector,
            metadata_json=metadata_json
        )
        db.add(incident)
        await db.commit()
        await db.refresh(incident)
        return incident

    async def search_similar_code(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 5
    ) -> List[CodeSnippetEmbedding]:
        """Queries codebase snippets matching semantically via cosine distance."""
        vector = await embedding_client.get_embedding(query)
        # cosine_distance is defined in pgvector.sqlalchemy
        stmt = select(CodeSnippetEmbedding).order_by(
            CodeSnippetEmbedding.embedding.cosine_distance(vector)
        ).limit(limit)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def search_similar_incidents(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 3
    ) -> List[HistoricalIncident]:
        """Queries historical bugs or tickets matching semantically via cosine distance."""
        vector = await embedding_client.get_embedding(query)
        stmt = select(HistoricalIncident).order_by(
            HistoricalIncident.embedding.cosine_distance(vector)
        ).limit(limit)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())


# Singleton instance
rag_service = RAGService()
