"""All tools live here — importing this package registers them."""
from __future__ import annotations

from . import install, open_app, open_url, play, routine, search, whatsapp  # noqa: F401
from . import news, websearch  # noqa: F401  Phase 4: research tools, listed last
from . import registry

__all__ = ["registry"]
