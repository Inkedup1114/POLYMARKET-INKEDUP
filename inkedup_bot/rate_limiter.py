"""
Comprehensive rate limiting system for API protection.

This module provides configurable rate limiting with exponential backoff,
request queuing, and intelligent error handling to prevent API abuse and
ensure reliable operation under load.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EndpointType(str, Enum):
    """API endpoint categories for differentiated rate limiting."""

    MARKET_DATA = "market_data"  # Market info, order books
    ORDER_MANAGEMENT = "order_management"  # Place, cancel orders
    POSITION_QUERIES = "position_queries"  # Account positions, balances
    AUTHENTICATION = "authentication"  # Login, auth endpoints
    WEBSOCKET = "websocket"  # WebSocket connections
    GENERAL = "general"  # All other endpoints


@dataclass
class RateLimitConfig:
    """Configuration for endpoint-specific rate limiting."""

    # Request limits
    requests_per_second: float = 10.0
    requests_per_minute: float = 100.0
    requests_per_hour: float = 1000.0
    burst_limit: int = 20  # Maximum burst requests

    # Queue configuration
    max_queue_size: int = 100
    queue_timeout_seconds: float = 30.0

    # Backoff configuration
    backoff_base: float = 1.0
    backoff_max: float = 60.0
    backoff_multiplier: float = 2.0
    backoff_jitter: bool = True

    # Error handling
    max_retries: int = 3
    retry_on_rate_limit: bool = True
    fail_fast_on_queue_full: bool = False


@dataclass
class RateLimitStatus:
    """Current rate limiting status information."""

    endpoint_type: EndpointType
    requests_made: int
    remaining_requests: int
    reset_time: float
    queue_size: int
    is_limited: bool
    backoff_until: float | None = None


class TokenBucket:
    """Token bucket algorithm implementation for rate limiting."""

    def __init__(self, capacity: float, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum number of tokens (burst limit)
            refill_rate: Rate at which tokens are added (per second)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_refill

            # Add tokens based on time passed
            self.tokens = min(
                self.capacity, self.tokens + (time_passed * self.refill_rate)
            )
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    async def tokens_available(self) -> float:
        """Get current token count."""
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_refill

            return min(self.capacity, self.tokens + (time_passed * self.refill_rate))

    async def time_until_tokens(self, tokens: int = 1) -> float:
        """Get time until specified tokens will be available."""
        async with self._lock:
            available = await self.tokens_available()
            if available >= tokens:
                return 0.0

            needed = tokens - available
            return needed / self.refill_rate


class ExponentialBackoff:
    """Exponential backoff calculator with jitter support."""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter: bool = True,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
        self.attempt = 0

    def next_delay(self) -> float:
        """Calculate next backoff delay."""
        delay = min(self.max_delay, self.base_delay * (self.multiplier**self.attempt))

        if self.jitter:
            import random

            delay = delay * (0.5 + random.random() * 0.5)  # 50-100% of calculated delay

        self.attempt += 1
        return delay

    def reset(self):
        """Reset backoff attempt counter."""
        self.attempt = 0


class RequestQueue:
    """FIFO queue for managing pending requests with timeouts."""

    def __init__(self, max_size: int = 100, timeout: float = 30.0):
        self.max_size = max_size
        self.timeout = timeout
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._pending_requests: dict[str, float] = {}  # request_id -> timestamp

    async def enqueue(self, request_id: str, priority: int = 0) -> bool:
        """
        Add request to queue.

        Args:
            request_id: Unique request identifier
            priority: Request priority (higher = more important)

        Returns:
            True if enqueued successfully, False if queue is full
        """
        try:
            # Check if queue is full
            if self._queue.full():
                logger.warning(f"Request queue full, rejecting request {request_id}")
                return False

            await self._queue.put((priority, time.time(), request_id))
            self._pending_requests[request_id] = time.time()

            logger.debug(f"Enqueued request {request_id}, queue size: {self.size()}")
            return True

        except asyncio.QueueFull:
            logger.warning(f"Failed to enqueue request {request_id}: queue full")
            return False

    async def dequeue(self) -> str | None:
        """
        Get next request from queue.

        Returns:
            Request ID if available, None if queue is empty or timed out
        """
        try:
            # Wait for next item with timeout
            priority, enqueue_time, request_id = await asyncio.wait_for(
                self._queue.get(), timeout=self.timeout
            )

            # Check if request has timed out
            if time.time() - enqueue_time > self.timeout:
                logger.warning(f"Request {request_id} timed out in queue")
                self._pending_requests.pop(request_id, None)
                return None

            self._pending_requests.pop(request_id, None)
            logger.debug(f"Dequeued request {request_id}, queue size: {self.size()}")

            return request_id

        except TimeoutError:
            logger.debug("Queue dequeue timed out")
            return None

    def size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    def is_full(self) -> bool:
        """Check if queue is full."""
        return self._queue.full()

    def cleanup_expired(self):
        """Remove expired requests from tracking."""
        current_time = time.time()
        expired = [
            req_id
            for req_id, timestamp in self._pending_requests.items()
            if current_time - timestamp > self.timeout
        ]
        for req_id in expired:
            self._pending_requests.pop(req_id, None)
            logger.debug(f"Cleaned up expired request {req_id}")


class EndpointRateLimiter:
    """Rate limiter for a specific endpoint type."""

    def __init__(self, endpoint_type: EndpointType, config: RateLimitConfig):
        self.endpoint_type = endpoint_type
        self.config = config

        # Token buckets for different time windows
        self.second_bucket = TokenBucket(
            capacity=config.burst_limit, refill_rate=config.requests_per_second
        )
        self.minute_bucket = TokenBucket(
            capacity=config.requests_per_minute,
            refill_rate=config.requests_per_minute / 60.0,
        )
        self.hour_bucket = TokenBucket(
            capacity=config.requests_per_hour,
            refill_rate=config.requests_per_hour / 3600.0,
        )

        # Request queue and backoff
        self.request_queue = RequestQueue(
            max_size=config.max_queue_size, timeout=config.queue_timeout_seconds
        )
        self.backoff = ExponentialBackoff(
            base_delay=config.backoff_base,
            max_delay=config.backoff_max,
            multiplier=config.backoff_multiplier,
            jitter=config.backoff_jitter,
        )

        # State tracking
        self.total_requests = 0
        self.successful_requests = 0
        self.rate_limited_requests = 0
        self.queued_requests = 0
        self.last_request_time = 0.0
        self.backoff_until = 0.0

        # Metrics
        self._metrics_lock = asyncio.Lock()

    async def acquire(self, request_id: str, priority: int = 0) -> bool:
        """
        Acquire permission to make a request.

        Args:
            request_id: Unique request identifier
            priority: Request priority

        Returns:
            True if request can proceed, False if should be queued/rejected
        """
        current_time = time.time()

        # Check if we're in backoff period
        if current_time < self.backoff_until:
            remaining = self.backoff_until - current_time
            logger.debug(
                f"Request {request_id} blocked by backoff for {remaining:.2f}s"
            )
            return False

        # Try to consume tokens from all buckets
        can_proceed = await self._check_all_buckets()

        if can_proceed:
            async with self._metrics_lock:
                self.total_requests += 1
                self.successful_requests += 1
                self.last_request_time = current_time
                self.backoff.reset()  # Reset backoff on success

            logger.debug(f"Request {request_id} approved immediately")
            return True

        # Request needs to be queued or rejected
        async with self._metrics_lock:
            self.total_requests += 1
            self.rate_limited_requests += 1

        # Try to queue the request
        if self.config.fail_fast_on_queue_full and self.request_queue.is_full():
            logger.warning(
                f"Request {request_id} rejected: queue full and fail-fast enabled"
            )
            return False

        queued = await self.request_queue.enqueue(request_id, priority)
        if queued:
            async with self._metrics_lock:
                self.queued_requests += 1
            logger.debug(f"Request {request_id} queued for later processing")

        return False

    async def _check_all_buckets(self) -> bool:
        """Check if all token buckets allow the request."""
        # All buckets must have tokens available
        return (
            await self.second_bucket.consume(1)
            and await self.minute_bucket.consume(1)
            and await self.hour_bucket.consume(1)
        )

    async def process_queue(self):
        """Process queued requests when rate limits allow."""
        while True:
            try:
                # Wait until we can process requests
                await self._wait_for_capacity()

                # Process next request in queue
                request_id = await self.request_queue.dequeue()
                if request_id:
                    # Try to acquire for the queued request
                    can_proceed = await self._check_all_buckets()

                    if can_proceed:
                        async with self._metrics_lock:
                            self.successful_requests += 1
                            self.last_request_time = time.time()

                        logger.debug(f"Processed queued request {request_id}")
                        # Notify that request can proceed (implementation specific)
                        # This would typically involve a callback or event
                    else:
                        # Re-queue if still can't process
                        await self.request_queue.enqueue(request_id, 0)
                        logger.debug(f"Re-queued request {request_id}")

                # Small delay to prevent busy loop
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in queue processor for {self.endpoint_type}: {e}")
                await asyncio.sleep(1.0)

    async def _wait_for_capacity(self):
        """Wait until rate limits allow processing."""
        max_wait = max(
            await self.second_bucket.time_until_tokens(1),
            await self.minute_bucket.time_until_tokens(1),
            await self.hour_bucket.time_until_tokens(1),
        )

        if max_wait > 0:
            logger.debug(f"Waiting {max_wait:.2f}s for rate limit capacity")
            await asyncio.sleep(max_wait)

    async def handle_rate_limit_error(
        self, error_details: dict[str, Any] | None = None
    ):
        """
        Handle rate limit error from API response.

        Args:
            error_details: Optional error details from API response
        """
        async with self._metrics_lock:
            self.rate_limited_requests += 1

        # Calculate backoff delay
        delay = self.backoff.next_delay()
        self.backoff_until = time.time() + delay

        # Extract retry-after header if available
        if error_details and "retry_after" in error_details:
            try:
                retry_after = float(error_details["retry_after"])
                self.backoff_until = max(self.backoff_until, time.time() + retry_after)
                delay = max(delay, retry_after)
            except (ValueError, TypeError):
                pass

        logger.warning(
            f"Rate limited on {self.endpoint_type}, backing off for {delay:.2f}s"
        )

    async def get_status(self) -> RateLimitStatus:
        """Get current rate limiting status."""
        current_time = time.time()

        # Calculate remaining requests (most restrictive bucket)
        second_tokens = await self.second_bucket.tokens_available()
        minute_tokens = await self.minute_bucket.tokens_available()
        hour_tokens = await self.hour_bucket.tokens_available()

        remaining = min(second_tokens, minute_tokens, hour_tokens)

        return RateLimitStatus(
            endpoint_type=self.endpoint_type,
            requests_made=self.total_requests,
            remaining_requests=int(remaining),
            reset_time=current_time + (1.0 / self.config.requests_per_second),
            queue_size=self.request_queue.size(),
            is_limited=current_time < self.backoff_until,
            backoff_until=(
                self.backoff_until if self.backoff_until > current_time else None
            ),
        )


class APIRateLimiter:
    """
    Comprehensive rate limiting system for all API endpoints.

    Manages rate limiting across different endpoint types with configurable
    limits, exponential backoff, request queuing, and intelligent error handling.
    """

    def __init__(self, default_config: RateLimitConfig | None = None):
        """
        Initialize the API rate limiter.

        Args:
            default_config: Default configuration for all endpoint types
        """
        self.default_config = default_config or RateLimitConfig()
        self.endpoint_limiters: dict[EndpointType, EndpointRateLimiter] = {}
        self.endpoint_configs: dict[EndpointType, RateLimitConfig] = {}

        # Global metrics
        self.total_requests = 0
        self.total_rate_limited = 0
        self.start_time = time.time()

        # Background tasks
        self._queue_processors: list[asyncio.Task] = []
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

    def configure_endpoint(self, endpoint_type: EndpointType, config: RateLimitConfig):
        """Configure rate limiting for specific endpoint type."""
        self.endpoint_configs[endpoint_type] = config

        # Update existing limiter if it exists
        if endpoint_type in self.endpoint_limiters:
            self.endpoint_limiters[endpoint_type] = EndpointRateLimiter(
                endpoint_type, config
            )

    def _get_limiter(self, endpoint_type: EndpointType) -> EndpointRateLimiter:
        """Get or create rate limiter for endpoint type."""
        if endpoint_type not in self.endpoint_limiters:
            config = self.endpoint_configs.get(endpoint_type, self.default_config)
            self.endpoint_limiters[endpoint_type] = EndpointRateLimiter(
                endpoint_type, config
            )

        return self.endpoint_limiters[endpoint_type]

    async def start(self):
        """Start the rate limiter background tasks."""
        if self._running:
            return

        self._running = True

        # Start queue processors for each endpoint type
        for endpoint_type in EndpointType:
            limiter = self._get_limiter(endpoint_type)
            task = asyncio.create_task(limiter.process_queue())
            task.set_name(f"rate_limiter_queue_{endpoint_type.value}")
            self._queue_processors.append(task)

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._cleanup_task.set_name("rate_limiter_cleanup")

        logger.info("API rate limiter started")

    async def stop(self):
        """Stop the rate limiter background tasks."""
        if not self._running:
            return

        self._running = False

        # Cancel all tasks
        for task in self._queue_processors:
            task.cancel()

        if self._cleanup_task:
            self._cleanup_task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(
            *self._queue_processors, self._cleanup_task, return_exceptions=True
        )

        self._queue_processors.clear()
        self._cleanup_task = None

        logger.info("API rate limiter stopped")

    async def _cleanup_loop(self):
        """Background task to clean up expired requests."""
        while self._running:
            try:
                for limiter in self.endpoint_limiters.values():
                    limiter.request_queue.cleanup_expired()

                await asyncio.sleep(60.0)  # Run cleanup every minute

            except Exception as e:
                logger.error(f"Error in rate limiter cleanup: {e}")
                await asyncio.sleep(60.0)

    async def acquire(
        self,
        endpoint_type: EndpointType,
        request_id: str | None = None,
        priority: int = 0,
    ) -> bool:
        """
        Request permission to make an API call.

        Args:
            endpoint_type: Type of API endpoint
            request_id: Unique request identifier
            priority: Request priority (higher = more important)

        Returns:
            True if request can proceed immediately, False if rate limited
        """
        if request_id is None:
            import uuid

            request_id = str(uuid.uuid4())

        limiter = self._get_limiter(endpoint_type)
        result = await limiter.acquire(request_id, priority)

        self.total_requests += 1
        if not result:
            self.total_rate_limited += 1

        return result

    async def handle_rate_limit_response(
        self,
        endpoint_type: EndpointType,
        response_details: dict[str, Any] | None = None,
    ):
        """
        Handle rate limit error response from API.

        Args:
            endpoint_type: Type of API endpoint that was rate limited
            response_details: Response details including retry-after headers
        """
        limiter = self._get_limiter(endpoint_type)
        await limiter.handle_rate_limit_error(response_details)

    async def get_status(
        self, endpoint_type: EndpointType | None = None
    ) -> dict[EndpointType, RateLimitStatus]:
        """
        Get rate limiting status.

        Args:
            endpoint_type: Specific endpoint type, or None for all

        Returns:
            Dictionary of rate limiting status by endpoint type
        """
        if endpoint_type:
            limiter = self._get_limiter(endpoint_type)
            return {endpoint_type: await limiter.get_status()}

        status = {}
        for et in EndpointType:
            if et in self.endpoint_limiters:
                limiter = self.endpoint_limiters[et]
                status[et] = await limiter.get_status()

        return status

    async def get_global_stats(self) -> dict[str, Any]:
        """Get global rate limiting statistics."""
        uptime = time.time() - self.start_time

        return {
            "uptime_seconds": uptime,
            "total_requests": self.total_requests,
            "total_rate_limited": self.total_rate_limited,
            "rate_limit_percentage": (
                (self.total_rate_limited / self.total_requests * 100)
                if self.total_requests > 0
                else 0.0
            ),
            "requests_per_second": self.total_requests / uptime if uptime > 0 else 0.0,
            "endpoint_count": len(self.endpoint_limiters),
            "is_running": self._running,
        }
