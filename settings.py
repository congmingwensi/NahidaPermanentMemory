"""Configuration loaded from this directory's .env or process environment."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

MEMORY_DIR = Path(__file__).resolve().parent
HISTORY_TOPIC_LIMIT = 5


@dataclass(frozen=True)
class MemorySettings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str = field(repr=False)
    openai_api_key: str = field(repr=False)
    neo4j_database: str = "neo4j"
    embedding_model: str = "text-embedding-3-small"
    openai_base_url: str | None = None
    topic_threshold: float = 0.75
    entry_threshold: float = 0.6
    merge_model: str = "gpt-6-luna"

    @classmethod
    def from_env(cls):
        values = {**dotenv_values(MEMORY_DIR / ".env"), **os.environ}
        password = values.get("NAHIDA_NEO4J_PASSWORD")
        api_key = values.get("OPENAI_API_KEY")
        if not password or not api_key:
            raise ValueError("Set NAHIDA_NEO4J_PASSWORD and OPENAI_API_KEY in .env or environment")
        return cls(
            neo4j_uri=values.get("NAHIDA_NEO4J_URI") or "bolt://localhost:7687",
            neo4j_user=values.get("NAHIDA_NEO4J_USER") or "neo4j",
            neo4j_password=password,
            neo4j_database=values.get("NAHIDA_NEO4J_DATABASE") or "neo4j",
            openai_api_key=api_key,
            openai_base_url=values.get("OPENAI_BASE_URL") or "https://api.openai.com/v1",
            embedding_model=values.get("EMBEDDING_MODEL") or "text-embedding-3-small",
            merge_model=values.get("MODEL") or "gpt-6-luna",
        )
