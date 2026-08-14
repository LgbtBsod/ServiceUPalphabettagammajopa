"""
UI Widgets: Skeleton Loader и Busy Indicator.
Заменяет статический splash screen на современные индикаторы загрузки.
Реализует принципы отзывчивого UI (Responsive Design).
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional, Callable, List, Tuple
from dataclasses import dataclass
import math

try:
    import customtkinter as ctk
except ImportError:
    # Fallback на стандартный tkinter если customtkinter не установлен
    ctk = None  # type: ignore

from shared.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class LoadingStage:
    """Этап загрузки для скелетона."""
    name: str
    description: str
    is_complete: bool = False


class SkeletonFrame(ctk.CTkFrame if ctk else tk.Frame):  # type: ignore
    """
    Скелетон-загрузка для отображения прогресса инициализации.
    Показывает список этапов с анимацией выполнения.
    """
    
    def __init__(
        self, 
        master, 
        title: str = "Загрузка приложения",
        stages: Optional[List[LoadingStage]] = None,
        width: int = 400,
        height: int = 300,
        **kwargs
    ) -> None:
        super().__init__(master, **kwargs)
        
        self.stages = stages or []
        self.current_stage_index = 0
        self.animation_counter = 0
        self.is_animating = False
        
        # Настройка внешнего вида
        if ctk:
            self.configure(fg_color="#2b2b2b")
        else:
            self.configure(bg="#2b2b2b")
        
        # Заголовок
        self.title_label = ctk.CTkLabel(  # type: ignore
            self, 
            text=title,
            font=ctk.CTkFont(size=18, weight="bold") if ctk else ("Arial", 18, "bold"),
            text_color="#ffffff" if ctk else "#ffffff"
        )
        self.title_label.pack(pady=(20, 10))
        
        # Контейнер для этапов
        self.stages_frame = ctk.CTkFrame(self, fg_color="transparent") if ctk else tk.Frame(self, bg="#2b2b2b")
        self.stages_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Прогресс бар
        if ctk:
            self.progress_bar = ctk.CTkProgressBar(
                self, 
                mode="determinate",
                progress_color="#3b8ed0",
                fg_color="#3a3a3a"
            )
            self.progress_bar.pack(padx=20, pady=(10, 5), fill=tk.X)
            self.progress_bar.set(0)
        else:
            # Fallback: простой Canvas для прогресс бара
            self.progress_canvas = tk.Canvas(self, height=10, bg="#3a3a3a", highlightthickness=0)
            self.progress_canvas.pack(padx=20, pady=(10, 5), fill=tk.X)
            self.progress_fill = self.progress_canvas.create_rectangle(0, 0, 0, 10, fill="#3b8ed0", outline="")
        
        # Метка процента
        self.percent_label = ctk.CTkLabel(  # type: ignore
            self,
            text="0%",
            font=ctk.CTkFont(size=12) if ctk else ("Arial", 12),
            text_color="#aaaaaa" if ctk else "#aaaaaa"
        )
        self.percent_label.pack(pady=(0, 20))
        
        # Инициализация этапов
        self._create_stage_widgets()
        
    def _create_stage_widgets(self) -> None:
        """Создание виджетов для каждого этапа."""
        for widget in self.stages_frame.winfo_children():
            widget.destroy()
            
        for i, stage in enumerate(self.stages):
            frame = ctk.CTkFrame(self.stages_frame, fg_color="transparent") if ctk else tk.Frame(self.stages_frame, bg="#2b2b2b")
            frame.pack(fill=tk.X, pady=2)
            
            # Индикатор статуса (кружок)
            status_color = "#3b8ed0" if not stage.is_complete else "#27ae60"
            if ctk:
                status_label = ctk.CTkLabel(
                    frame,
                    text="●",
                    text_color=status_color,
                    font=ctk.CTkFont(size=14)
                )
            else:
                status_label = tk.Label(frame, text="●", fg=status_color, bg="#2b2b2b", font=("Arial", 14))
            status_label.pack(side=tk.LEFT, padx=(0, 10))
            
            # Название этапа
            name_color = "#ffffff" if i == self.current_stage_index else "#888888"
            if ctk:
                name_label = ctk.CTkLabel(
                    frame,
                    text=stage.name,
                    text_color=name_color,
                    font=ctk.CTkFont(size=13, weight="bold" if i == self.current_stage_index else "normal"),
                    anchor="w"
                )
            else:
                name_label = tk.Label(frame, text=stage.name, fg=name_color, bg="#2b2b2b", 
                                     font=("Arial", 13, "bold" if i == self.current_stage_index else "normal"),
                                     anchor="w")
            name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            setattr(self, f"status_label_{i}", status_label)
            setattr(self, f"name_label_{i}", name_label)
    
    def update_progress(self, current: int, total: int, stage_name: str, details: Optional[str] = None) -> None:
        """Обновление прогресса загрузки."""
        percentage = (current / total * 100) if total > 0 else 0
        
        # Обновление прогресс бара
        if ctk:
            self.progress_bar.set(percentage / 100)
        else:
            width = int(self.progress_canvas.winfo_width() * percentage / 100)
            self.progress_canvas.coords(self.progress_fill, 0, 0, width, 10)
        
        # Обновление метки процента
        self.percent_label.configure(text=f"{int(percentage)}%")
        
        # Обновление текущего этапа
        if stage_name and self.stages:
            for i, stage in enumerate(self.stages):
                if stage.name == stage_name:
                    self.current_stage_index = i
                    stage.is_complete = True
                    break
        
        # Перерисовка этапов
        self._create_stage_widgets()
        
        logger.debug(f"Skeleton progress: {percentage:.1f}% - {stage_name}")
    
    def start_animation(self) -> None:
        """Запуск анимации (опционально)."""
        self.is_animating = True
        # Здесь можно добавить пульсацию или другие эффекты
    
    def stop_animation(self) -> None:
        """Остановка анимации."""
        self.is_animating = False


class BusyIndicator(ctk.CTkCanvas if ctk else tk.Canvas):  # type: ignore
    """
    Анимированный индикатор занятости (spinner).
    Используется для блокирующих операций в UI.
    """
    
    def __init__(
        self,
        master,
        size: int = 40,
        color: str = "#3b8ed0",
        bg_color: str = "transparent",
        line_width: int = 4,
        speed: int = 50,  # мс между кадрами
        **kwargs
    ) -> None:
        super().__init__(
            master,
            width=size,
            height=size,
            bg=bg_color if bg_color != "transparent" else "#2b2b2b",
            highlightthickness=0,
            **kwargs
        )
        
        self.size = size
        self.color = color
        self.line_width = line_width
        self.speed = speed
        self.angle = 0
        self.is_spinning = False
        self.animation_id: Optional[str] = None
        
        self._draw_spinner()
    
    def _draw_spinner(self) -> None:
        """Отрисовка кадра спиннера."""
        self.delete("all")
        
        center = self.size // 2
        radius = self.size // 2 - self.line_width
        
        # Рисуем дугу
        start_angle = self.angle
        end_angle = self.angle + 90  # Дуга в 90 градусов
        
        self.create_arc(
            center - radius, center - radius,
            center + radius, center + radius,
            start=start_angle,
            extent=90,
            style=tk.ARC,
            outline=self.color,
            width=self.line_width
        )
    
    def _animate(self) -> None:
        """Кадр анимации."""
        if not self.is_spinning:
            return
            
        self.angle = (self.angle + 15) % 360
        self._draw_spinner()
        
        self.animation_id = self.after(self.speed, self._animate)
    
    def start(self) -> None:
        """Запуск анимации."""
        if not self.is_spinning:
            self.is_spinning = True
            self._animate()
            logger.debug("Busy indicator started")
    
    def stop(self) -> None:
        """Остановка анимации."""
        if self.is_spinning:
            self.is_spinning = False
            if self.animation_id:
                self.after_cancel(self.animation_id)
                self.animation_id = None
            self.delete("all")  # Очистка canvas
            logger.debug("Busy indicator stopped")


class LoadingOverlay(ctk.CTkToplevel if ctk else tk.Toplevel):  # type: ignore
    """
    Модальное окно загрузки с скелетоном и спиннером.
    Блокирует взаимодействие с основным окном во время загрузки.
    """
    
    def __init__(
        self,
        parent,
        title: str = "Загрузка",
        stages: Optional[List[LoadingStage]] = None,
        show_busy_indicator: bool = True,
        **kwargs
    ) -> None:
        super().__init__(parent, **kwargs)
        
        self.title(title)
        self.resizable(False, False)
        
        # Центрирование окна
        self.geometry("450x350")
        self.transient(parent)
        self.grab_set()  # Модальность
        
        # Создание скелетона
        self.skeleton = SkeletonFrame(self, title=title, stages=stages)
        self.skeleton.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Спиннер (опционально)
        if show_busy_indicator:
            self.busy_indicator = BusyIndicator(self, size=30)
            self.busy_indicator.pack(pady=(0, 15))
            self.busy_indicator.start()
        else:
            self.busy_indicator = None
    
    def update_progress(self, current: int, total: int, stage: str, details: Optional[str] = None) -> None:
        """Обновление прогресса загрузки."""
        self.skeleton.update_progress(current, total, stage, details)
    
    def destroy(self) -> None:
        """Закрытие окна с остановкой анимаций."""
        if self.busy_indicator:
            self.busy_indicator.stop()
        super().destroy()


# Пример использования
if __name__ == "__main__":
    if ctk:
        ctk.set_appearance_mode("dark")
        app = ctk.CTk()
        app.title("Skeleton Demo")
        app.geometry("500x400")
        
        stages = [
            LoadingStage("Конфигурация", "Загрузка настроек"),
            LoadingStage("Логи", "Инициализация системы логирования"),
            LoadingStage("Переводы", "Загрузка языковых пакетов"),
            LoadingStage("База данных", "Подключение к SQLite"),
            LoadingStage("Сервисы", "Инициализация бизнес-логики"),
        ]
        
        def simulate_loading():
            overlay = LoadingOverlay(app, stages=stages)
            
            def load():
                for i, stage in enumerate(stages, 1):
                    overlay.update_progress(i, len(stages), stage.name, stage.description)
                    app.after(500)  # Имитация работы
                app.after(300, overlay.destroy)
            
            app.after(100, load)
        
        btn = ctk.CTkButton(app, text="Показать загрузку", command=simulate_loading)
        btn.pack(expand=True)
        
        app.mainloop()
    else:
        print("customtkinter not installed, using fallback mode")
