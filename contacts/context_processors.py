"""
I expose small UI-wide values through a context processor so base templates can
use them without repeating code in every view.
"""

from __future__ import annotations

from typing import Any


def ui_context(request: Any) -> dict[str, str]:
    """
    I provide reusable UI metadata to all templates in the contacts app.
    """
    return {
        "portfolio_brand_name": "Contact Phone",
        "portfolio_tagline": "",
    }