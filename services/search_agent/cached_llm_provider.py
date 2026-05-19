"""
Redis-backed LLM response cache for the NEXUS Search Agent.

CachedLLMProvider wraps any LLMProvider implementation and caches responses
in Redis under the key llm:cache:{sha256(model+system+user)}.

Cache key: llm:cache:{sha256}
TTL: config.settings.llm_cache_ttl_seconds (default 3600)

On Redis failure: logs WARNING, falls through to live LLM call — never raises.

Usage:
    from llm_provider import get_llm_provider
    from claude_client import CachedLLMProvider

    provider = CachedLLMProvider(base_provider=get_llm_provider(), redis_client=redis)
    response = await provider.complete(system="...", user="...")
    # response.cache_hit is True on second identical call
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import redis.asyncio as aioredis
import structlog

from llm_provider import LLMProvider, LLMResponse

logger = structlog.get_logger(__name__)

_CACHE_KEY_PREFIX = "llm:cache:"


@dataclass
class CachedLLMResponse(LLMResponse):
    """
    LLMResponse extended with a cache_hit flag.

    Attributes:
        cache_hit: True if the response was served from Redis cache.
    """

    cache_hit: bool = False


class CachedLLMProvider:
    """
    LLMProvider decorator that caches responses in Redis.

    Wraps any LLMProvider implementation. On cache hit, returns the cached
    response without calling the underlying provider. On cache miss, calls
    the provider and stores the result.

    Redis failures are silently caught — the provider is always called as fallback.

    Attributes:
        _provider: The underlying LLMProvider (Claude, Gemini, or Ollama).
        _redis: Async Redis client.
        _ttl: Cache TTL in seconds.
        _model: Model name included in cache key for isolation.
    """

    def __init__(
        self,
        base_provider: LLMProvider,
        redis_client: aioredis.Redis,
        model: str,
        ttl_seconds: int = 3600,
    ) -> None:
        """
        Initialise the cached provider.

        Args:
            base_provider: The underlying LLMProvider to wrap.
            redis_client: Async Redis client from app.state.redis.
            model: Model identifier string — included in cache key.
            ttl_seconds: Redis TTL for cached responses (default 3600).
        """
        self._provider = base_provider
        self._redis = redis_client
        self._model = model
        self._ttl = ttl_seconds

    def _make_cache_key(self, system: str, user: str) -> str:
        """
        Generate a deterministic Redis cache key from model + prompts.

        SHA-256 of the concatenation ensures collisions are astronomically
        unlikely even across different system/user prompt combinations.

        Args:
            system: System prompt string.
            user: User message string.

        Returns:
            Redis key string in the form llm:cache:{hex_digest}.
        """
        payload = json.dumps({"model": self._model, "system": system, "user": user}, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{_CACHE_KEY_PREFIX}{digest}"

    async def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> CachedLLMResponse:
        """
        Return a cached or live LLM response.

        Checks Redis for a cached response first. On hit, deserialises and returns
        CachedLLMResponse(cache_hit=True). On miss, calls the underlying provider,
        stores the result, and returns CachedLLMResponse(cache_hit=False).

        Args:
            system: System prompt.
            user: User message.
            json_mode: Passed through to the underlying provider.

        Returns:
            CachedLLMResponse with cache_hit flag set.
        """
        cache_key = self._make_cache_key(system, user)

        # Cache read
        try:
            cached_raw = await self._redis.get(cache_key)
            if cached_raw:
                data = json.loads(cached_raw)
                logger.debug("llm_cache.hit", cache_key=cache_key)
                return CachedLLMResponse(
                    content=data["content"],
                    prompt_tokens=data["prompt_tokens"],
                    completion_tokens=data["completion_tokens"],
                    cache_hit=True,
                )
        except Exception as exc:
            logger.warning("llm_cache.read_error", cache_key=cache_key, error=str(exc))

        # Cache miss — call provider
        response = await self._provider.complete(system=system, user=user, json_mode=json_mode)

        # Cache write
        try:
            payload = json.dumps({
                "content": response.content,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
            })
            await self._redis.set(cache_key, payload, ex=self._ttl)
            logger.debug("llm_cache.written", cache_key=cache_key, ttl=self._ttl)
        except Exception as exc:
            logger.warning("llm_cache.write_error", cache_key=cache_key, error=str(exc))

        return CachedLLMResponse(
            content=response.content,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cache_hit=False,
        )