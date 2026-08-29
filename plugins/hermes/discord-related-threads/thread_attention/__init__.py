"""Hermes Discord thread-attention feature.

The package is deliberately stdlib-only.  Discord and Hermes objects are
accepted through small duck-typed runtime boundaries so the domain logic can
be tested without a gateway or network connection.
"""

from .config import ThreadAttentionConfig, load_thread_attention_config
from .runtime import ThreadAttentionRuntime

__all__ = [
    "ThreadAttentionConfig",
    "ThreadAttentionRuntime",
    "load_thread_attention_config",
]
