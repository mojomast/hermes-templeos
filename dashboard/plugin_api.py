"""Dashboard entry that Hermes mounts at /api/plugins/templeos/.

Thin re-export of templeos.api.router. The pane must call these routes
through ctx.rest only.
"""

from __future__ import annotations

from templeos.api import router

__all__ = ["router"]
