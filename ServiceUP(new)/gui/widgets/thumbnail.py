#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Виджет миниатюры фотографии"""

import os
import customtkinter as ctk
from PIL import Image, ImageTk


class ThumbnailWidget(ctk.CTkFrame):
    """Виджет для отображения миниатюры фото с возможностью удаления"""
    
    def __init__(self, master, photo_manager, photo_path, colors, 
                 on_delete=None, on_click=None, **kwargs):
        super().__init__(master, **kwargs)
        self.photo_manager = photo_manager
        self.photo_path = photo_path
        self.colors = colors
        self.on_delete = on_delete
        self.on_click = on_click
        
        self.configure(
            fg_color=colors['bg_tertiary'],
            corner_radius=6,
            border_width=1,
            border_color=colors['border']
        )
        
        self.create_widgets()
    
    def create_widgets(self):
        """Создание виджетов"""
        thumb_container = ctk.CTkFrame(self, fg_color="transparent", width=70, height=70)
        thumb_container.pack(padx=3, pady=(3, 1))
        thumb_container.pack_propagate(False)
        
        if self.photo_manager:
            thumb = self.photo_manager.get_thumbnail(self.photo_path)
        else:
            thumb = Image.open(self.photo_path)
            thumb.thumbnail((60, 60), Image.Resampling.LANCZOS)
        
        if thumb:
            if not isinstance(thumb, Image.Image):
                thumb = Image.open(self.photo_path)
                thumb.thumbnail((60, 60), Image.Resampling.LANCZOS)
            
            photo_img = ImageTk.PhotoImage(thumb)
            
            thumb_label = ctk.CTkLabel(
                thumb_container,
                text="",
                image=photo_img,
                fg_color="transparent"
            )
            thumb_label.image = photo_img
            thumb_label.pack(expand=True)
            
            if self.on_click:
                thumb_label.bind("<Button-1>", lambda e: self.on_click(self.photo_path))
        
        if self.on_delete:
            delete_btn = ctk.CTkButton(
                self,
                text="✖",
                width=16,
                height=16,
                corner_radius=3,
                fg_color=self.colors.get('error', '#d13438'),
                hover_color=self.colors.get('error', '#b32d30'),
                font=ctk.CTkFont(size=9, weight="bold"),
                command=self.delete_photo
            )
            delete_btn.place(relx=1.0, x=-3, y=3, anchor="ne")
    
    def delete_photo(self):
        """Удаление фотографии"""
        if self.on_delete:
            self.on_delete(self.photo_path)
