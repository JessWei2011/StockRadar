"""Send one explicitly labelled local Windows notification for validation."""
from __future__ import annotations

from .toast_notifications import ToastMessage, WindowsToastSink


def main() -> None:
    WindowsToastSink().show(
        ToastMessage(
            event_key="manual-toast-test",
            title="StockRadar｜通知測試",
            body="Windows Toast 已啟用；正式通知只會在候選成立或失效時發送。",
        )
    )
    print("WINDOWS_TOAST_TEST_SENT")


if __name__ == "__main__":
    main()
