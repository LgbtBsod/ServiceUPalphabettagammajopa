#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Просмотрщик фотографий"""

import os
import customtkinter as ctk
from tkinter import ttk
from PIL import Image, ImageTk

from gui.widgets.premium import PremiumCard, PremiumLabel


class PhotoViewerWindow(ctk.CTkToplevel):
    """Окно просмотра фотографий"""
    
    def __init__(self, parent, photo_manager, photos: list, colors: dict, title: str = "Просмотр фотографий", settings=None):
        super().__init__(parent)
        self.parent = parent
        self.photo_manager = photo_manager
        self.photos = photos
        self.colors = colors
        self.settings = settings  # опционально, для сохранения геометрии
        self.current_index = 0
        self.photo_label = None
        self.thumbnails_frame = None
        self.thumbnail_buttons = []

        self.title(title)
        from utils.window_state import restore_window_geometry
        restore_window_geometry(self.settings, "photo_viewer", self,
                                default_w=900, default_h=600, min_w=600, min_h=400)

        self.transient(parent)
        self.grab_set()

        # Сохраняем геометрию при закрытии
        self.protocol("WM_DELETE_WINDOW", self._close_with_geometry)

        self.create_widgets()

        if self.photos:
            self.load_current_photo()

    def _close_with_geometry(self):
        """Сохраняет геометрию окна в config и закрывает его."""
        try:
            from utils.window_state import save_window_geometry
            save_window_geometry(self.settings, "photo_viewer", self)
        except Exception:
            pass
        self.destroy()
    
    def create_widgets(self):
        """Создание виджетов"""
        main_container = ctk.CTkFrame(self, fg_color=self.colors['bg_primary'])
        main_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        info_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        info_frame.pack(fill="x", pady=(0, 5))
        
        self.counter_label = PremiumLabel(
            info_frame,
            text=f"Фото {self.current_index + 1} из {len(self.photos)}" if self.photos else "Нет фото",
            colors=self.colors,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.counter_label.pack(side="left", padx=5)
        
        photo_card = PremiumCard(main_container, self.colors)
        photo_card.pack(fill="both", expand=True, padx=5, pady=5)
        
        canvas_frame = ctk.CTkFrame(photo_card, fg_color="transparent")
        canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        canvas = ctk.CTkCanvas(canvas_frame, bg=self.colors['bg_secondary'], highlightthickness=0)
        vsb = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
        
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        self.photo_frame = ctk.CTkFrame(canvas, fg_color="transparent")
        canvas_window = canvas.create_window((0, 0), window=self.photo_frame, anchor="nw")
        
        self.photo_label = ctk.CTkLabel(
            self.photo_frame,
            text="",
            image=None,
            fg_color="transparent"
        )
        self.photo_label.pack()
        
        def configure_canvas(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)
        
        self.photo_frame.bind("<Configure>", configure_canvas)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        
        if len(self.photos) > 1:
            thumbnails_card = PremiumCard(main_container, self.colors)
            thumbnails_card.pack(fill="x", padx=5, pady=5)
            
            thumbnails_label = PremiumLabel(
                thumbnails_card,
                text="Миниатюры:",
                colors=self.colors,
                font=ctk.CTkFont(size=12, weight="bold")
            )
            thumbnails_label.pack(anchor="w", padx=10, pady=(5, 2))
            
            self.thumbnails_frame = ctk.CTkFrame(thumbnails_card, fg_color="transparent")
            self.thumbnails_frame.pack(fill="x", padx=10, pady=(0, 5))
            
            self.create_thumbnails()
        
        nav_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        nav_frame.pack(fill="x", pady=(5, 0))
        
        prev_btn = ctk.CTkButton(
            nav_frame,
            text="◀",
            command=self.show_previous,
            width=60,
            height=30,
            corner_radius=6,
            fg_color=self.colors['bg_tertiary'],
            text_color=self.colors['text_primary'],
            hover_color=self.colors['hover']
        )
        prev_btn.pack(side="left", padx=2)
        
        next_btn = ctk.CTkButton(
            nav_frame,
            text="▶",
            command=self.show_next,
            width=60,
            height=30,
            corner_radius=6,
            fg_color=self.colors['bg_tertiary'],
            text_color=self.colors['text_primary'],
            hover_color=self.colors['hover']
        )
        next_btn.pack(side="left", padx=2)
        
        close_btn = ctk.CTkButton(
            nav_frame,
            text="✖",
            command=self.destroy,
            width=60,
            height=30,
            corner_radius=6,
            fg_color=self.colors['bg_tertiary'],
            text_color=self.colors['text_primary'],
            hover_color=self.colors['hover']
        )
        close_btn.pack(side="right", padx=2)
    
    def create_thumbnails(self):
        """Создание миниатюр"""
        for i, photo_path in enumerate(self.photos):
            try:
                if self.photo_manager:
                    thumb = self.photo_manager.get_thumbnail(photo_path)
                else:
                    thumb = Image.open(photo_path)
                    thumb.thumbnail((50, 50), Image.Resampling.LANCZOS)
                
                if thumb:
                    if not isinstance(thumb, Image.Image):
                        thumb = Image.open(photo_path)
                        thumb.thumbnail((50, 50), Image.Resampling.LANCZOS)
                    
                    photo_img = ImageTk.PhotoImage(thumb)
                    
                    btn = ctk.CTkButton(
                        self.thumbnails_frame,
                        text="",
                        image=photo_img,
                        width=50,
                        height=50,
                        corner_radius=4,
                        fg_color="transparent",
                        hover_color=self.colors['hover'],
                        command=lambda idx=i: self.jump_to_photo(idx)
                    )
                    btn.image = photo_img
                    btn.pack(side="left", padx=1)
                    self.thumbnail_buttons.append(btn)
            except Exception as e:
                print(f"Ошибка создания миниатюры: {e}")
    
    def load_current_photo(self):
        """Загрузка текущего фото"""
        if not self.photos or self.current_index >= len(self.photos):
            return
        
        try:
            photo_path = self.photos[self.current_index]
            if not os.path.exists(photo_path):
                self.photo_label.configure(text="❌ Файл не найден", image=None)
                return
            
            img = Image.open(photo_path)
            display_size = (700, 500)
            img.thumbnail(display_size, Image.Resampling.LANCZOS)
            
            photo_img = ImageTk.PhotoImage(img)
            self.photo_label.configure(image=photo_img, text="")
            self.photo_label.image = photo_img
            
            self.counter_label.configure(text=f"Фото {self.current_index + 1} из {len(self.photos)}")
            self.highlight_current_thumbnail()
            
        except Exception as e:
            print(f"Ошибка загрузки фото: {e}")
            self.photo_label.configure(text="❌ Ошибка загрузки изображения", image=None)
    
    def highlight_current_thumbnail(self):
        """Подсветка текущей миниатюры"""
        for i, btn in enumerate(self.thumbnail_buttons):
            if i == self.current_index:
                btn.configure(border_width=2, border_color=self.colors['accent'])
            else:
                btn.configure(border_width=0)
    
    def jump_to_photo(self, index: int):
        """Переход к фото по индексу"""
        if 0 <= index < len(self.photos):
            self.current_index = index
            self.load_current_photo()
    
    def show_previous(self):
        """Предыдущее фото"""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_photo()
    
    def show_next(self):
        """Следующее фото"""
        if self.current_index < len(self.photos) - 1:
            self.current_index += 1
            self.load_current_photo()
