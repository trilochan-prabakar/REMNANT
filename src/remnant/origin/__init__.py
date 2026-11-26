"""Protected origin adapters for REMNANT experiments."""

from remnant.origin.fastapi import FastAPIOriginAdapter, OriginResponse
from remnant.origin.protocols import OriginAdapter

__all__ = ["FastAPIOriginAdapter", "OriginAdapter", "OriginResponse"]
