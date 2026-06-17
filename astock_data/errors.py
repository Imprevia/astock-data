class AStockDataError(Exception):
    """Base exception for all astock-data package errors."""


class TickerResolutionError(AStockDataError):
    """Raised when a stock ticker cannot be resolved safely."""


class AmbiguousTickerError(TickerResolutionError):
    """Raised when a ticker query matches multiple possible instruments."""


class InvalidTickerError(TickerResolutionError):
    """Raised when a ticker is malformed or outside supported markets."""


class DataSourceError(AStockDataError):
    """Raised when an upstream market data source fails unexpectedly."""


class RateLimitError(DataSourceError):
    """Raised when a data source rejects or throttles a request."""


class NoDataError(DataSourceError):
    """Raised when a data source returns no usable records."""


class MarketValidationError(AStockDataError):
    """Raised when market-specific validation rules reject an operation."""


class CacheError(AStockDataError):
    """Raised when cache reads, writes, or invalidation fail."""
