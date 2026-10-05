import hashlib
import math
import re
from typing import Protocol


class EmbeddingProvider(Protocol):
    dimension: int

    async def embed(self, text: str) -> list[float]: ...


class HashEmbeddingProvider:
    dimension = 64

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[\w\u0900-\u097F]+", text.lower())

        for token in tokens:
            digest = hashlib.blake2b(
                token.encode("utf-8"),
                digest_size=8,
            ).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimension
            sign = -1.0 if (value >> 8) & 1 else 1.0
            vector[index] += sign

        norm = math.sqrt(sum(item * item for item in vector))
        if norm == 0:
            return vector
        return [item / norm for item in vector]
