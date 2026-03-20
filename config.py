"""Agent Platform — Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── Primary LLM (GPU) ────────────────────────────────────
    llm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "meta-llama/Llama-3.1-8B-Instruct"
    llm_hardware: str = "XPU"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.1

    # ── Secondary LLM (CPU) ──────────────────────────────────
    secondary_llm_base_url: str = "http://localhost:8001/v1"
    secondary_llm_model: str = "Qwen/Qwen2.5-3B-Instruct"
    secondary_llm_hardware: str = "Xeon"
    secondary_llm_modules: str = "classify,extract_entities"

    # ── Retrieval ────────────────────────────────────────────
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    vector_index_dir: str = "data/index"
    lexical_index_dir: str = "data/lexical"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_top_k: int = 10
    retrieval_top_n: int = 50

    # ── API ──────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8081
    api_key: str = ""
    cors_origins: str = "*"

    # ── Database ─────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///agent_platform.db"

    # ── Search providers ─────────────────────────────────────
    tavily_api_key: str = ""
    serper_api_key: str = ""

    # ── Security ─────────────────────────────────────────────
    require_auth: bool = False
    jwt_secret: str = "change-me-in-production"
    approval_timeout_s: int = 300
    pii_redaction_enabled: bool = True

    # ── Observability ────────────────────────────────────────
    log_level: str = "INFO"
    metrics_enabled: bool = True
    audit_enabled: bool = True

    # ── Agent tuning ─────────────────────────────────────────
    agent_max_iterations: int = 15
    supervisor_max_rounds: int = 5
    max_sub_agents: int = 4
    max_context_tokens: int = 8192

    # ── Derived helpers ──────────────────────────────────────
    @property
    def secondary_modules_set(self) -> set[str]:
        return {m.strip() for m in self.secondary_llm_modules.split(",") if m.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
