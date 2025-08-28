#!/usr/bin/env python3
"""
Tests for cache performance monitoring and analytics system.

This module tests the comprehensive cache monitoring functionality including
analytics collection, dashboard reporting, and alert generation.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from inkedup_bot.cache import CacheConfig, IntelligentCache
from inkedup_bot.cache_analytics import (
    CacheAnalytics,
)
from inkedup_bot.cache_dashboard import CacheDashboard


class TestCacheAnalytics(unittest.TestCase):
    """Test cache analytics system functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.analytics = CacheAnalytics(retention_hours=1)
        self.cache_name = "test_cache"

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.analytics.stop_monitoring())

    def test_analytics_initialization(self):
        """Test analytics system initialization."""
        self.assertEqual(self.analytics.retention_hours, 1)
        self.assertIsNotNone(self.analytics.alert_thresholds)
        self.assertEqual(len(self.analytics._events), 0)

    def test_record_cache_hit(self):
        """Test recording cache hit events."""
        self.analytics.record_cache_hit(self.cache_name, "test_key", 5.0, 100)

        self.assertEqual(len(self.analytics._events), 1)
        event = self.analytics._events[0]
        self.assertEqual(event.cache_name, self.cache_name)
        self.assertEqual(event.event_type.value, "hit")
        self.assertEqual(event.key, "test_key")
        self.assertEqual(event.response_time_ms, 5.0)
        self.assertEqual(event.data_size_bytes, 100)

    def test_record_cache_miss(self):
        """Test recording cache miss events."""
        self.analytics.record_cache_miss(self.cache_name, "test_key", 2.0)

        self.assertEqual(len(self.analytics._events), 1)
        event = self.analytics._events[0]
        self.assertEqual(event.cache_name, self.cache_name)
        self.assertEqual(event.event_type.value, "miss")
        self.assertEqual(event.response_time_ms, 2.0)

    def test_record_cache_error(self):
        """Test recording cache error events."""
        error_details = {"error_type": "timeout", "code": 500}
        self.analytics.record_cache_error(self.cache_name, "test_key", error_details)

        self.assertEqual(len(self.analytics._events), 1)
        event = self.analytics._events[0]
        self.assertEqual(event.cache_name, self.cache_name)
        self.assertEqual(event.event_type.value, "error")
        self.assertEqual(event.metadata, error_details)

    def test_get_cache_performance_no_data(self):
        """Test getting performance metrics when no data exists."""
        performance = self.analytics.get_cache_performance("nonexistent_cache")

        self.assertTrue(performance["no_data"])
        self.assertEqual(performance["cache_name"], "nonexistent_cache")

    def test_get_cache_performance_with_data(self):
        """Test getting performance metrics with sample data."""
        # Generate sample events
        self.analytics.record_cache_hit(self.cache_name, "key1", 5.0, 100)
        self.analytics.record_cache_hit(self.cache_name, "key2", 3.0, 200)
        self.analytics.record_cache_miss(self.cache_name, "key3", 10.0)
        self.analytics.record_cache_error(self.cache_name, "key4", {"error": "test"})

        performance = self.analytics.get_cache_performance(self.cache_name)

        self.assertFalse(performance.get("no_data", False))
        self.assertEqual(performance["cache_name"], self.cache_name)
        self.assertEqual(performance["requests"]["hits"], 2)
        self.assertEqual(performance["requests"]["misses"], 1)
        self.assertEqual(performance["requests"]["errors"], 1)
        self.assertEqual(performance["requests"]["total"], 3)  # hits + misses
        self.assertAlmostEqual(performance["rates"]["hit_rate"], 2 / 3, places=2)
        self.assertAlmostEqual(performance["rates"]["miss_rate"], 1 / 3, places=2)

    def test_health_score_calculation(self):
        """Test cache health score calculation."""
        # Perfect performance
        score = self.analytics._calculate_health_score(1.0, 1.0, 0.0)
        self.assertGreater(score, 90)

        # Poor performance
        score = self.analytics._calculate_health_score(0.1, 100.0, 0.5)
        self.assertLess(score, 50)

    def test_get_all_caches_summary(self):
        """Test getting summary for all caches."""
        # Generate data for multiple caches
        self.analytics.record_cache_hit("cache1", "key1", 5.0, 100)
        self.analytics.record_cache_hit("cache2", "key1", 3.0, 150)
        self.analytics.record_cache_miss("cache1", "key2", 8.0)

        summary = self.analytics.get_all_caches_summary()

        self.assertEqual(len(summary["cache_details"]), 2)
        self.assertIn("cache1", summary["cache_details"])
        self.assertIn("cache2", summary["cache_details"])
        self.assertEqual(summary["overall_metrics"]["active_caches"], 2)

    def test_export_performance_report(self):
        """Test exporting performance report to file."""
        # Generate sample data
        self.analytics.record_cache_hit(self.cache_name, "key1", 5.0, 100)
        self.analytics.record_cache_miss(self.cache_name, "key2", 10.0)

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            report_file = f.name

        try:
            report = self.analytics.export_performance_report(report_file)

            # Verify report structure
            self.assertIn("report_metadata", report)
            self.assertIn("performance_summary", report)
            self.assertIn("alerts_summary", report)

            # Verify file was created and contains valid JSON
            self.assertTrue(os.path.exists(report_file))
            with open(report_file) as f:
                loaded_report = json.load(f)
                self.assertEqual(report, loaded_report)

        finally:
            if os.path.exists(report_file):
                os.unlink(report_file)


class TestCacheDashboard(unittest.TestCase):
    """Test cache dashboard functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.dashboard = CacheDashboard()

    def test_dashboard_initialization(self):
        """Test dashboard initialization."""
        self.assertIsNotNone(self.dashboard.analytics)
        self.assertIsNotNone(self.dashboard.integration_manager)

    @patch("inkedup_bot.cache_dashboard.get_cache_analytics")
    def test_get_dashboard_data_structure(self, mock_get_analytics):
        """Test dashboard data structure."""
        # Mock analytics response
        mock_analytics = Mock()
        mock_analytics.get_all_caches_summary.return_value = {
            "overall_metrics": {
                "total_requests": 100,
                "overall_hit_rate": 0.8,
                "overall_error_rate": 0.02,
                "active_caches": 2,
            },
            "cache_details": {},
            "recommendations": [],
        }
        mock_analytics.get_active_alerts.return_value = []
        mock_get_analytics.return_value = mock_analytics

        # Get dashboard data
        dashboard_data = asyncio.run(self.dashboard.get_dashboard_data(refresh=True))

        # Verify structure
        self.assertIn("system_overview", dashboard_data)
        self.assertIn("cache_performance", dashboard_data)
        self.assertIn("alerts", dashboard_data)
        self.assertIn("cache_status", dashboard_data)
        self.assertIn("recommendations", dashboard_data)
        self.assertIn("trends", dashboard_data)

    def test_export_dashboard_data(self):
        """Test exporting dashboard data."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            export_file = f.name

        try:
            result = asyncio.run(self.dashboard.export_dashboard_data(export_file))

            self.assertTrue(result["success"])
            self.assertIn("file_size_bytes", result)
            self.assertTrue(os.path.exists(export_file))

            # Verify exported data is valid JSON
            with open(export_file) as f:
                exported_data = json.load(f)
                self.assertIn("export_metadata", exported_data)
                self.assertIn("dashboard_data", exported_data)

        finally:
            if os.path.exists(export_file):
                os.unlink(export_file)


class TestCacheIntegrationWithAnalytics(unittest.TestCase):
    """Test cache integration with analytics system."""

    def setUp(self):
        """Set up test fixtures."""
        self.analytics = CacheAnalytics(retention_hours=1)
        # Patch the global analytics getter
        self.patcher = patch(
            "inkedup_bot.cache.get_cache_analytics", return_value=self.analytics
        )
        self.patcher.start()

        # Create a test cache
        config = CacheConfig(max_size=100, default_ttl=60, enable_analytics=True)
        self.cache = IntelligentCache("test_analytics_cache", config)

    def tearDown(self):
        """Clean up after tests."""
        self.patcher.stop()
        asyncio.run(self.analytics.stop_monitoring())

    def test_cache_operations_generate_analytics_events(self):
        """Test that cache operations generate analytics events."""
        # Perform cache operations
        asyncio.run(self._perform_cache_operations())

        # Check that events were recorded
        events = list(self.analytics._events)
        self.assertGreater(len(events), 0)

        # Verify event types
        event_types = [event.event_type.value for event in events]
        self.assertIn("hit", event_types)
        self.assertIn("miss", event_types)

    async def _perform_cache_operations(self):
        """Perform a series of cache operations."""
        # Cache miss
        result = await self.cache.get("nonexistent_key")
        self.assertIsNone(result)

        # Cache set and hit
        await self.cache.set("test_key", "test_value", ttl=60)
        result = await self.cache.get("test_key")
        self.assertEqual(result, "test_value")

        # Another cache miss
        result = await self.cache.get("another_nonexistent_key")
        self.assertIsNone(result)

    def test_performance_metrics_collection(self):
        """Test that performance metrics are collected correctly."""
        # Generate cache activity
        asyncio.run(self._generate_cache_activity())

        # Get performance metrics
        performance = self.analytics.get_cache_performance("test_analytics_cache")

        # Verify metrics were collected
        self.assertFalse(performance.get("no_data", False))
        self.assertGreater(performance["requests"]["total"], 0)
        self.assertGreaterEqual(performance["rates"]["hit_rate"], 0.0)
        self.assertLessEqual(performance["rates"]["hit_rate"], 1.0)

    async def _generate_cache_activity(self):
        """Generate cache activity for testing."""
        # Pre-populate some keys
        for i in range(5):
            await self.cache.set(f"key_{i}", f"value_{i}", ttl=60)

        # Mix of hits and misses
        for i in range(10):
            if i < 5:
                # Should be hits
                await self.cache.get(f"key_{i}")
            else:
                # Should be misses
                await self.cache.get(f"missing_key_{i}")


class TestAlertSystem(unittest.TestCase):
    """Test cache alert system."""

    def setUp(self):
        """Set up test fixtures."""
        # Custom alert thresholds for testing
        alert_thresholds = {
            "hit_rate_low": 0.9,  # Very high threshold to trigger alerts
            "response_time_high_ms": 1.0,  # Very low threshold
            "error_rate_high": 0.01,  # 1% error rate threshold
        }
        self.analytics = CacheAnalytics(
            retention_hours=1, alert_thresholds=alert_thresholds
        )
        self.alerts_received = []

        # Add callback to capture alerts
        def capture_alert(alert):
            self.alerts_received.append(alert)

        self.analytics.add_alert_callback(capture_alert)

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.analytics.stop_monitoring())

    def test_low_hit_rate_alert(self):
        """Test that low hit rate triggers alert."""
        # Generate mostly cache misses to trigger low hit rate alert
        for i in range(10):
            if i < 1:  # Only 1 hit out of 10 requests = 10% hit rate
                self.analytics.record_cache_hit("test_cache", f"key_{i}", 5.0, 100)
            else:
                self.analytics.record_cache_miss("test_cache", f"key_{i}", 10.0)

        # Trigger alert check
        asyncio.run(self.analytics._check_performance_thresholds())

        # Should trigger low hit rate alert (10% < 90% threshold)
        low_hit_rate_alerts = [
            alert
            for alert in self.analytics.get_active_alerts()
            if alert.alert_type == "low_hit_rate"
        ]
        self.assertGreater(len(low_hit_rate_alerts), 0)

    def test_high_error_rate_alert(self):
        """Test that high error rate triggers alert."""
        # Generate requests with high error rate
        for i in range(10):
            if i < 8:  # 80% normal operations
                self.analytics.record_cache_hit("test_cache", f"key_{i}", 5.0, 100)
            else:  # 20% errors (> 1% threshold)
                self.analytics.record_cache_error(
                    "test_cache", f"key_{i}", {"error": "test"}
                )

        # Trigger alert check
        asyncio.run(self.analytics._check_performance_thresholds())

        # Should trigger high error rate alert
        error_rate_alerts = [
            alert
            for alert in self.analytics.get_active_alerts()
            if alert.alert_type == "high_error_rate"
        ]
        self.assertGreater(len(error_rate_alerts), 0)

    def test_alert_callback_execution(self):
        """Test that alert callbacks are executed."""
        # Generate condition that triggers alert
        for i in range(5):
            self.analytics.record_cache_error(
                "test_cache", f"key_{i}", {"error": "test"}
            )

        # Trigger alert check
        asyncio.run(self.analytics._check_performance_thresholds())

        # Check that callback was executed
        self.assertGreater(len(self.alerts_received), 0)


class TestPerformanceUnderLoad(unittest.TestCase):
    """Test cache analytics performance under load."""

    def setUp(self):
        """Set up test fixtures."""
        self.analytics = CacheAnalytics(retention_hours=1)

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.analytics.stop_monitoring())

    def test_high_volume_event_processing(self):
        """Test analytics system can handle high volume of events."""
        import time

        start_time = time.time()
        num_events = 1000

        # Generate high volume of events
        for i in range(num_events):
            if i % 2 == 0:
                self.analytics.record_cache_hit("load_test_cache", f"key_{i}", 5.0, 100)
            else:
                self.analytics.record_cache_miss("load_test_cache", f"key_{i}", 8.0)

        end_time = time.time()
        processing_time = end_time - start_time

        # Verify all events were processed
        self.assertEqual(len(self.analytics._events), num_events)

        # Verify processing was reasonably fast (less than 1 second for 1000 events)
        self.assertLess(processing_time, 1.0)

        # Verify performance metrics are accurate
        performance = self.analytics.get_cache_performance("load_test_cache")
        self.assertEqual(performance["requests"]["total"], num_events)
        self.assertAlmostEqual(performance["rates"]["hit_rate"], 0.5, places=2)


if __name__ == "__main__":
    # Run all tests
    unittest.main(verbosity=2)
