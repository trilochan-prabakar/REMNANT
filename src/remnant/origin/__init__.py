"""Protected origin adapters for REMNANT experiments."""

from remnant.origin.fastapi import FastAPIOriginAdapter, OriginResponse
from remnant.origin.network import LoopbackHTTPOriginAdapter
from remnant.origin.protocols import OriginAdapter

__all__ = ["FastAPIOriginAdapter", "LoopbackHTTPOriginAdapter", "OriginAdapter", "OriginResponse"]
