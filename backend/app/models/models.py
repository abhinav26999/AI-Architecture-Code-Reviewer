from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class CodeSnippetEmbedding(Base):
    __tablename__ = "code_snippets"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String(512), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=True)  # 768 dimensions for nomic-embed-text or Gemini
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HistoricalIncident(Base):
    __tablename__ = "historical_incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=True)
    metadata_json = Column(JSON, nullable=True)  # Renamed to metadata_json to avoid SQLAlchemy base conflicts
    created_at = Column(DateTime(timezone=True), server_default=func.now())
