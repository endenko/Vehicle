"""
Statistics Dashboard Component
Hiển thị thống kê real-time: Số xe đang đỗ, Ra hôm nay, Doanh thu
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
import threading
import time

class StatisticsDashboard:
    """Dashboard thống kê với auto-refresh"""
    
    def __init__(self, parent, stats_callback: Callable = None, bg_color: str = "#34495e"):
        """
        Args:
            parent: Parent tkinter widget
            stats_callback: Function trả về dict với 'parked_count', 'exits_today', 'revenue_today'
            bg_color: Màu nền dashboard
        """
        self.parent = parent
        self.stats_callback = stats_callback
        self.bg_color = bg_color
        self.frame = None
        self.refresh_thread = None
        self.running = True
        
        # Variables
        self.parked_var = tk.StringVar(value="0")
        self.exits_var = tk.StringVar(value="0")
        self.revenue_var = tk.StringVar(value="₫0")
        self.status_var = tk.StringVar(value="⚪ Đang chờ...")
        
        self._build_ui()
    
    def _build_ui(self):
        """Xây dựng UI Dashboard"""
        self.frame = tk.Frame(self.parent, bg=self.bg_color, height=90)
        self.frame.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)
        self.frame.pack_propagate(False)
        
        # Title
        title = tk.Label(
            self.frame, 
            text="📊 BẢNG ĐIỀU KHIỂN THỐNG KÊ",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg="white"
        )
        title.pack(anchor="w", padx=15, pady=(5, 0))
        
        # Stats Grid
        stats_frame = tk.Frame(self.frame, bg=self.bg_color)
        stats_frame.pack(fill=tk.X, padx=15, pady=(5, 5))
        
        # Stat 1: Xe đang đỗ
        self._create_stat_item(stats_frame, 0, "🚗 Đang đỗ:", self.parked_var, "Chiếc")
        
        # Stat 2: Ra hôm nay
        self._create_stat_item(stats_frame, 1, "🚙 Ra hôm nay:", self.exits_var, "Chiếc")
        
        # Stat 3: Doanh thu
        self._create_stat_item(stats_frame, 2, "💰 Doanh thu hôm nay:", self.revenue_var, "")
        
        # Status
        self._create_stat_item(stats_frame, 3, "Status:", self.status_var, "")
    
    def _create_stat_item(self, parent, column, label, var, unit):
        """Tạo một stat item"""
        item_frame = tk.Frame(parent, bg=self.bg_color)
        item_frame.grid(row=0, column=column, padx=15, sticky="w")
        
        label_widget = tk.Label(item_frame, text=label, font=("Arial", 10), bg=self.bg_color, fg="lightgray")
        label_widget.pack(side=tk.LEFT)
        
        value_widget = tk.Label(item_frame, textvariable=var, font=("Arial", 13, "bold"), bg=self.bg_color, fg="yellow")
        value_widget.pack(side=tk.LEFT, padx=(5, 0))
        
        if unit:
            unit_widget = tk.Label(item_frame, text=unit, font=("Arial", 9), bg=self.bg_color, fg="lightgray")
            unit_widget.pack(side=tk.LEFT, padx=(2, 0))
    
    def update_stats(self, stats: dict):
        """Cập nhật thống kê"""
        try:
            parked = stats.get('parked_count', 0)
            exits = stats.get('exits_today', 0)
            revenue = stats.get('revenue_today', 0)
            
            self.parked_var.set(str(parked))
            self.exits_var.set(str(exits))
            self.revenue_var.set(f"₫{revenue:,.0f}" if revenue else "₫0")
            
            # Status màu sắc dựa trên số xe đang đỗ
            if parked == 0:
                self.status_var.set("⚪ Rỗi")
            elif parked < 10:
                self.status_var.set(f"🟢 Bình thường ({parked}/100)")
            elif parked < 50:
                self.status_var.set(f"🟡 Gần đầy ({parked}/100)")
            else:
                self.status_var.set(f"🔴 ĐẦY ({parked}/100)")
        
        except Exception as e:
            print(f"[✗] Lỗi cập nhật dashboard: {e}")
    
    def start_auto_refresh(self, interval: float = 5.0):
        """Bắt đầu tự động refresh thống kê"""
        if self.stats_callback is None:
            return
        
        def refresh_loop():
            while self.running:
                try:
                    stats = self.stats_callback()
                    self.parent.after(0, self.update_stats, stats)
                except Exception as e:
                    print(f"[✗] Lỗi refresh: {e}")
                
                time.sleep(interval)
        
        self.refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
        self.refresh_thread.start()
    
    def stop_auto_refresh(self):
        """Dừng auto refresh"""
        self.running = False
        if self.refresh_thread:
            self.refresh_thread.join(timeout=2)
