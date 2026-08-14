"""
Презентационный слой для GUI (Tkinter/PyQt).
Принципы:
- Single Responsibility: Отвечает только за ОТРИСОВКУ, не за получение данных.
- Dependency Inversion: Принимает готовый DTO (DashboardResponse), не лезет в БД.
- Don't Reinvent the Wheel: Используем стандартные возможности виджетов для отображения JSON-данных.
"""
import tkinter as tk
from tkinter import ttk
from typing import Callable

from application.dtos import DashboardResponse, DashboardWidget


class DashboardGUIView:
    """
    Представление дашборда для Desktop GUI.
    Получает данные через callback (от контроллера) и рендерит их.
    """
    
    def __init__(self, root: tk.Tk, on_refresh: Callable[[], DashboardResponse]):
        self.root = root
        self.on_refresh = on_refresh  # Callback для получения данных
        self.current_data: DashboardResponse | None = None
        
        self._init_ui()

    def _init_ui(self):
        """Инициализация интерфейса."""
        self.root.title("Аналитический Дашборд")
        self.root.geometry("1200x800")
        
        # Панель фильтров (упрощенно)
        filter_frame = ttk.LabelFrame(self.root, text="Фильтры", padding=10)
        filter_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(filter_frame, text="Обновить", command=self.refresh_data).pack(side=tk.RIGHT)
        
        # Область виджетов
        self.canvas_frame = ttk.Frame(self.root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Скроллбар для длинного контента
        self.canvas = tk.Canvas(self.canvas_frame)
        scrollbar = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_data(self):
        """Запрос данных у контроллера и перерисовка."""
        try:
            self.current_data = self.on_refresh()
            self._render_dashboard(self.current_data)
        except Exception as e:
            self._show_error(f"Ошибка загрузки данных: {e}")

    def _render_dashboard(self, data: DashboardResponse):
        """Очистка и отрисовка виджетов из DTO."""
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
            
        # Заголовок с датой генерации
        ttk.Label(
            self.scrollable_frame, 
            text=f"Дашборд сформирован: {data.generated_at}",
            font=("Arial", 12, "bold")
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # Рендер каждого виджета
        for dw in data.widgets:
            self._render_widget(dw)

    def _render_widget(self, widget_data: DashboardWidget):
        """Рендер отдельного виджета в зависимости от типа."""
        frame = ttk.LabelFrame(self.scrollable_frame, text=widget_data.title, padding=10)
        frame.pack(fill=tk.X, pady=5)
        
        if widget_data.widget_type == "kpi_card":
            self._render_kpi(frame, widget_data.data)
        elif widget_data.widget_type in ("chart_bar", "chart_line"):
            self._render_chart_placeholder(frame, widget_data)
        elif widget_data.widget_type == "table":
            self._render_table(frame, widget_data.data)
        else:
            ttk.Label(frame, text=f"Неизвестный тип виджета: {widget_data.widget_type}").pack()

    def _render_kpi(self, parent, data: list[dict]):
        """Отрисовка KPI карточек."""
        kpi_frame = ttk.Frame(parent)
        kpi_frame.pack(fill=tk.X)
        
        for item in data:
            card = ttk.LabelFrame(kpi_frame, text=item["label"], padding=5)
            card.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.BOTH)
            ttk.Label(
                card, 
                text=str(item["value"]), 
                font=("Arial", 16, "bold"),
                foreground="#2196F3"
            ).pack()

    def _render_chart_placeholder(self, parent, widget_data: DashboardWidget):
        """
        Заглушка для графика. 
        В реальном проекте здесь можно использовать matplotlib嵌入 или canvas для рисования.
        Пока выводим текстовое представление данных.
        """
        info_text = "\n".join([f"{p['label'] if isinstance(p, dict) else p.label}: {p['value'] if isinstance(p, dict) else p.value}" for p in widget_data.data[:5]])
        if len(widget_data.data) > 5:
            info_text += f"\n... и еще {len(widget_data.data) - 5} записей"
            
        ttk.Label(parent, text=info_text, justify=tk.LEFT).pack(anchor=tk.W)
        ttk.Label(parent, text="(Здесь мог быть график)", foreground="gray").pack()

    def _render_table(self, parent, data: list[dict]):
        """Отрисовка таблицы."""
        if not data:
            return
            
        cols = list(data[0].keys())
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=min(len(data), 10))
        
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=100)
            
        for row in data:
            tree.insert("", tk.END, values=list(row.values()))
            
        tree.pack(fill=tk.X)

    def _show_error(self, message: str):
        """Вывод сообщения об ошибке."""
        error_label = ttk.Label(self.scrollable_frame, text=message, foreground="red")
        error_label.pack(pady=20)
