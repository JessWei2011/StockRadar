from __future__ import annotations

import unittest

from stock_radar.toast_notifications import OncePerEventDispatcher, ToastMessage, candidate_event_to_toast


class RecordingSink:
    def __init__(self) -> None:
        self.messages: list[ToastMessage] = []

    def show(self, message: ToastMessage) -> None:
        self.messages.append(message)


class ToastNotificationTests(unittest.TestCase):
    def test_candidate_entry_toast_exposes_price_evidence(self) -> None:
        message = candidate_event_to_toast("3324", {"timestamp": "2026-08-28T09:46:00+08:00", "kind": "ENTRY_CANDIDATE_TRIGGERED", "close": 1125, "breakout_level": 1120, "invalidation_price": 1120, "volume_ratio": 6.67, "vwap": 1108.9})
        self.assertIn("放量突破候選", message.title)
        self.assertIn("量比 6.67x", message.body)

    def test_candidate_invalidation_toast_exposes_invalidation_price(self) -> None:
        message = candidate_event_to_toast("3324", {"timestamp": "2026-08-28T10:07:00+08:00", "kind": "EXIT_CANDIDATE_TRIGGERED", "close": 1115, "breakout_level": 1120, "invalidation_price": 1120, "volume_ratio": .52, "vwap": 1112.84})
        self.assertIn("突破候選失效", message.title)
        self.assertIn("失效價 1120.0", message.body)

    def test_dispatcher_sends_each_event_once(self) -> None:
        sink = RecordingSink()
        dispatcher = OncePerEventDispatcher(sink)
        message = ToastMessage("a", "title", "body")
        self.assertTrue(dispatcher.dispatch(message))
        self.assertFalse(dispatcher.dispatch(message))
        self.assertEqual([message], sink.messages)
