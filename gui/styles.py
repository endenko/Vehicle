# gui/styles.py
import customtkinter as ctk

class AppStyle:
    """Premium light theme cho toàn bộ GUI School Parking Management."""

    # ── Nền chính ──────────────────────────────────────────────────────────
    APP_BG        = "#EEF2F7"   # Nền tổng thể (xám xanh nhạt)
    BG_DARK       = APP_BG       # Alias để giữ tương thích
    CARD_BG       = "#FFFFFF"   # Card/panel trắng
    CARD_BG_HOVER = "#F7FAFF"
    SURFACE       = "#F3F6FB"   # Input, entry
    BORDER        = "#CBD5E1"
    TEXT_DARK     = "#1F2937"

    # ── Màu nhấn (accent) ──────────────────────────────────────────────────
    PRIMARY       = "#3B5998"   # Header xanh đậm theo ảnh 2
    PRIMARY_DARK  = "#2D4373"
    SUCCESS       = "#10B981"   # Emerald 500
    SUCCESS_DARK  = "#059669"
    WARNING       = "#F59E0B"
    DANGER        = "#EF5C5C"
    DANGER_DARK   = "#D94141"

    # ── Text ───────────────────────────────────────────────────────────────
    TEXT_PRIMARY  = "#0F172A"
    TEXT_SECONDARY= "#475569"
    TEXT_MUTED    = "#64748B"

    # ── Màu trạng thái ─────────────────────────────────────────────────────
    STATUS_OK     = "#10B981"
    STATUS_WARN   = "#F59E0B"
    STATUS_ERR    = "#EF4444"
    STATUS_INFO   = "#38BDF8"

    # ── Fonts ──────────────────────────────────────────────────────────────
    TITLE_FONT    = ("Helvetica", 22, "bold")
    SUBTITLE_FONT = ("Helvetica", 15, "bold")
    BODY_FONT     = ("Helvetica", 13)
    BODY_BOLD     = ("Helvetica", 13, "bold")
    BUTTON_FONT   = ("Helvetica", 14, "bold")
    SMALL_FONT    = ("Helvetica", 11)
    MONO_FONT     = ("Courier", 13, "bold")
    LARGE_PLATE   = ("Courier", 28, "bold")

    @staticmethod
    def apply():
        """Áp dụng light theme cho hệ thống."""
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")