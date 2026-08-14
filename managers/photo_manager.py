#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Менеджер фотографий"""

import os
import re
import logging
from datetime import datetime
from PIL import Image
from typing import Optional, List

from config import PHOTOS_DIR, THUMBNAILS_DIR

logger = logging.getLogger(__name__)


class PhotoManager:
    """Класс для управления фотографиями устройств"""
    
    def __init__(self):
        self.photos_dir = PHOTOS_DIR
        self.thumbnails_dir = THUMBNAILS_DIR
        self.create_photos_directory()
    
    def create_photos_directory(self):
        """Создание директорий для фотографий и миниатюр"""
        try:
            if not os.path.exists(self.photos_dir):
                os.makedirs(self.photos_dir)
            if not os.path.exists(self.thumbnails_dir):
                os.makedirs(self.thumbnails_dir)
        except Exception as e:
            logger.error(f"Ошибка создания директорий для фото: {e}", exc_info=True)
    
    def get_client_photos_dir(self, client_name: str, client_phone: str) -> str:
        """Получение пути к директории клиента для фотографий"""
        safe_name = re.sub(r'[^\w\-_]', '', f"{client_name}_{client_phone}")[:50]
        client_dir = os.path.join(self.photos_dir, safe_name)
        if not os.path.exists(client_dir):
            os.makedirs(client_dir)
        return client_dir
    
    def get_client_thumbnails_dir(self, client_name: str, client_phone: str) -> str:
        """Получение пути к директории миниатюр клиента"""
        safe_name = re.sub(r'[^\w\-_]', '', f"{client_name}_{client_phone}")[:50]
        thumb_dir = os.path.join(self.thumbnails_dir, safe_name)
        if not os.path.exists(thumb_dir):
            os.makedirs(thumb_dir)
        return thumb_dir
    
    def _resample_method(self):
        """Возвращает доступный метод ресемплинга для текущей версии Pillow."""
        if hasattr(Image, 'Resampling'):
            return Image.Resampling.LANCZOS
        # ANTIALIAS удалён в Pillow 10+; мягко откатываемся.
        return getattr(Image, 'ANTIALIAS', Image.BICUBIC)
    
    def create_thumbnail(self, image_path: str, size: tuple = (80, 80)) -> Optional[Image.Image]:
        """Создание миниатюры изображения"""
        try:
            img = Image.open(image_path)
            
            img.thumbnail(size, self._resample_method())
            
            thumb = Image.new('RGB', size, (255, 255, 255))
            offset = ((size[0] - img.size[0]) // 2, (size[1] - img.size[1]) // 2)
            thumb.paste(img, offset)
            
            return thumb
        except Exception as e:
            logger.error(f"Ошибка создания миниатюры: {e}", exc_info=True)
            return None
    
    def save_photo(self, source_path: str, client_name: str, client_phone: str,
                   order_number: str, photo_type: str) -> Optional[str]:
        """Сохранение фотографии для устройства"""
        try:
            if not os.path.exists(source_path):
                return None
            
            client_dir = self.get_client_photos_dir(client_name, client_phone)
            thumb_dir = self.get_client_thumbnails_dir(client_name, client_phone)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            ext = os.path.splitext(source_path)[1].lower()
            if not ext:
                ext = '.jpg'
            
            filename = f"order_{order_number}_{photo_type}_{timestamp}{ext}"
            dest_path = os.path.join(client_dir, filename)
            
            img = Image.open(source_path)
            
            max_size = 1200
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, self._resample_method())
            
            img.save(dest_path, optimize=True, quality=85)
            
            thumb = self.create_thumbnail(dest_path, size=(80, 80))
            if thumb:
                thumb_filename = f"thumb_{filename}"
                thumb_path = os.path.join(thumb_dir, thumb_filename)
                thumb.save(thumb_path, optimize=True, quality=70)
            
            return dest_path
        except Exception as e:
            logger.error(f"Ошибка сохранения фото: {e}", exc_info=True)
            return None
    
    def get_order_photos(self, order_number: str, client_name: str, client_phone: str) -> List[str]:
        """Получение фотографий для конкретного заказа"""
        try:
            client_dir = self.get_client_photos_dir(client_name, client_phone)
            if not os.path.exists(client_dir):
                return []
            
            photos = []
            for file in os.listdir(client_dir):
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    if f"order_{order_number}" in file and not file.startswith('thumb_'):
                        photos.append(os.path.join(client_dir, file))
            
            return sorted(photos, reverse=True)
        except Exception as e:
            logger.error(f"Ошибка получения фотографий: {e}", exc_info=True)
            return []
    
    def get_thumbnail(self, photo_path: str) -> Optional[Image.Image]:
        """Получение миниатюры для фотографии"""
        try:
            dir_name = os.path.dirname(photo_path)
            base_name = os.path.basename(photo_path)
            
            thumb_dir = dir_name.replace(self.photos_dir, self.thumbnails_dir)
            thumb_path = os.path.join(thumb_dir, f"thumb_{base_name}")
            
            if os.path.exists(thumb_path):
                return Image.open(thumb_path)
            else:
                return self.create_thumbnail(photo_path, size=(80, 80))
        except Exception as e:
            logger.error(f"Ошибка получения миниатюры: {e}", exc_info=True)
            return None
    
    def delete_photos(self, photo_paths: List[str]) -> bool:
        """Удаление фотографий"""
        try:
            for photo_path in photo_paths:
                if os.path.exists(photo_path):
                    os.remove(photo_path)
                    
                    dir_name = os.path.dirname(photo_path)
                    base_name = os.path.basename(photo_path)
                    thumb_dir = dir_name.replace(self.photos_dir, self.thumbnails_dir)
                    thumb_path = os.path.join(thumb_dir, f"thumb_{base_name}")
                    
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления фотографий: {e}", exc_info=True)
            return False
