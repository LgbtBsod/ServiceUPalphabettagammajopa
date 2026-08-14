#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Генератор отчетов и актов"""

import os
import re
from datetime import datetime
from typing import Dict, Any, Optional

from config import REPORTS_DIR
from utils.formatters import format_order_number_for_display, format_date, format_phone, format_price


class ReportGenerator:
    """Класс для генерации отчетов и актов"""
    
    def __init__(self):
        self.reports_dir = REPORTS_DIR
        self.create_reports_directory()
    
    def create_reports_directory(self):
        """Создание директории для отчетов"""
        try:
            if not os.path.exists(self.reports_dir):
                os.makedirs(self.reports_dir)
        except Exception as e:
            print(f"Ошибка создания директории: {e}")
            self.reports_dir = "."
    
    def generate_receipt_act(self, device: Dict[str, Any]) -> Optional[str]:
        """Генерация акта приема"""
        try:
            order_number = str(device.get('order_number', '')).strip()
            client_name = str(device.get('client_name', '')).strip()
            phone = str(device.get('phone', '')).strip()
            device_type = str(device.get('device_type', '')).strip()
            brand = str(device.get('brand', '')).strip()
            model = str(device.get('model', '')).strip()
            serial = str(device.get('serial_number', 'не указан')).strip()
            appearance = str(device.get('appearance', 'не указан')).strip()
            completeness = str(device.get('completeness', 'не указана')).strip()
            defect = str(device.get('defect', '')).strip()
            total_price = str(device.get('total_price', '')).strip()
            prepayment = str(device.get('prepayment', '')).strip()
            priority = str(device.get('priority', 'Обычный')).strip()
            warranty = str(device.get('warranty', 'без гарантии')).strip()
            
            safe_order = re.sub(r'[^\w\-_]', '', order_number)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.reports_dir, f"receipt_act_{safe_order}_{timestamp}.txt")
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("╔" + "═" * 68 + "╗\n")
                f.write("║" + " " * 20 + "АКТ ПРИЕМА ОБОРУДОВАНИЯ В РЕМОНТ" + " " * 19 + "║\n")
                f.write("╠" + "═" * 68 + "╣\n\n")
                
                f.write(f"  Заказ №: {format_order_number_for_display(order_number)}\n")
                f.write(f"  Дата приема: {format_date(device.get('receipt_date', ''))}\n\n")
                
                f.write("  ИНФОРМАЦИЯ О КЛИЕНТЕ:\n")
                f.write("  " + "─" * 40 + "\n")
                f.write(f"  Клиент: {client_name}\n")
                f.write(f"  Телефон: {format_phone(phone)}\n\n")
                
                f.write("  ИНФОРМАЦИЯ ОБ ОБОРУДОВАНИИ:\n")
                f.write("  " + "─" * 40 + "\n")
                f.write(f"  Тип: {device_type}\n")
                f.write(f"  Бренд: {brand}\n")
                f.write(f"  Модель: {model}\n")
                f.write(f"  S/N: {serial}\n")
                f.write(f"  Внешний вид: {appearance}\n")
                f.write(f"  Комплектация: {completeness}\n\n")
                
                f.write("  ИНФОРМАЦИЯ О РЕМОНТЕ:\n")
                f.write("  " + "─" * 40 + "\n")
                f.write(f"  Неисправность: {defect}\n\n")
                
                f.write("  ФИНАНСОВАЯ ИНФОРМАЦИЯ:\n")
                f.write("  " + "─" * 40 + "\n")
                f.write(f"  Предварительная стоимость: {format_price(total_price)}\n")
                f.write(f"  Предоплата: {format_price(prepayment) if prepayment else '0 ₽'}\n")
                f.write(f"  Приоритет: {priority}\n")
                f.write(f"  Гарантия: {warranty}\n\n")
                
                f.write("╠" + "═" * 68 + "╣\n")
                f.write("║" + " " * 24 + "УСЛОВИЯ РЕМОНТА" + " " * 25 + "║\n")
                f.write("╠" + "═" * 68 + "╣\n\n")
                
                f.write("  1. Срок выполнения ремонта составляет от 3 до 14 рабочих дней\n")
                f.write("     в зависимости от сложности и наличия запчастей.\n\n")
                f.write("  2. В случае необходимости замены комплектующих, стоимость\n")
                f.write("     может быть скорректирована после согласования с клиентом.\n\n")
                f.write("  3. Сервисный центр несет ответственность за сохранность\n")
                f.write("     оборудования на время ремонта.\n\n")
                f.write("  4. В случае отказа от ремонта после диагностики,\n")
                f.write("     клиент оплачивает стоимость диагностических работ.\n\n")
                f.write("  5. Гарантия на выполненные работы составляет 30 дней\n")
                f.write("     с момента выдачи устройства.\n\n")
                f.write("  6. Устройство должно быть получено в течение 30 дней\n")
                f.write("     после уведомления о готовности. По истечении этого срока\n")
                f.write("     сервисный центр не несет ответственности за сохранность.\n\n")
                f.write("  7. С условиями ремонта ознакомлен и согласен:\n\n")
                
                f.write("╠" + "═" * 68 + "╣\n")
                f.write("║" + " " * 25 + "ПОДПИСИ СТОРОН" + " " * 25 + "║\n")
                f.write("╠" + "═" * 68 + "╣\n\n")
                f.write("  Мастер: ____________________          Клиент: ____________________\n")
                f.write("          (подпись)                            (подпись)\n\n")
                f.write(f"  Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
                f.write("╚" + "═" * 68 + "╝\n")
            
            return filename
        except Exception as e:
            print(f"❌ Ошибка создания акта приема: {e}")
            return None
    
    def generate_completion_act(self, device: Dict[str, Any]) -> Optional[str]:
        """Генерация акта выполненных работ"""
        try:
            order_number = str(device.get('order_number', '')).strip()
            client_name = str(device.get('client_name', '')).strip()
            phone = str(device.get('phone', '')).strip()
            brand = str(device.get('brand', '')).strip()
            model = str(device.get('model', '')).strip()
            device_type = str(device.get('device_type', '')).strip()
            serial = str(device.get('serial_number', 'не указан')).strip()
            completed_work = str(device.get('completed_work', '—')).strip()
            total_price = str(device.get('total_price', '')).strip()
            prepayment = str(device.get('prepayment', '')).strip()
            warranty = str(device.get('warranty', 'без гарантии')).strip()
            
            safe_order = re.sub(r'[^\w\-_]', '', order_number)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.reports_dir, f"completion_act_{safe_order}_{timestamp}.txt")
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("╔" + "═" * 68 + "╗\n")
                f.write("║" + " " * 18 + "АКТ ВЫПОЛНЕННЫХ РАБОТ" + " " * 19 + "║\n")
                f.write("╠" + "═" * 68 + "╣\n\n")
                
                f.write(f"  Заказ №: {format_order_number_for_display(order_number)}\n")
                f.write(f"  Дата выдачи: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
                
                f.write("  ИНФОРМАЦИЯ О КЛИЕНТЕ:\n")
                f.write("  " + "─" * 40 + "\n")
                f.write(f"  Клиент: {client_name}\n")
                f.write(f"  Телефон: {format_phone(phone)}\n\n")
                
                f.write("  ИНФОРМАЦИЯ ОБ ОБОРУДОВАНИИ:\n")
                f.write("  " + "─" * 40 + "\n")
                f.write(f"  Устройство: {brand} {model}\n")
                f.write(f"  Тип: {device_type}\n")
                f.write(f"  S/N: {serial}\n")
                f.write(f"  Дата приема: {format_date(device.get('receipt_date', ''))}\n\n")
                
                f.write("  ВЫПОЛНЕННЫЕ РАБОТЫ:\n")
                f.write("  " + "─" * 40 + "\n")
                f.write(f"  {completed_work}\n\n")
                
                f.write("  ФИНАНСОВАЯ ИНФОРМАЦИЯ:\n")
                f.write("  " + "─" * 40 + "\n")
                f.write(f"  Общая стоимость: {format_price(total_price)}\n")
                f.write(f"  Предоплата: {format_price(prepayment) if prepayment else '0 ₽'}\n")
                try:
                    remaining = float(total_price) - float(prepayment) if total_price and prepayment else float(total_price)
                    f.write(f"  К оплате: {format_price(str(remaining))}\n\n")
                except (ValueError, TypeError):
                    f.write(f"  К оплате: {format_price(total_price)}\n\n")
                
                f.write(f"  ГАРАНТИЯ: {warranty}\n\n")
                
                f.write("╠" + "═" * 68 + "╣\n")
                f.write("║" + " " * 24 + "УСЛОВИЯ ГАРАНТИИ" + " " * 25 + "║\n")
                f.write("╠" + "═" * 68 + "╣\n\n")
                
                f.write("  1. Гарантия распространяется на выполненные работы\n")
                f.write("     и установленные комплектующие.\n\n")
                f.write("  2. Гарантия не распространяется на механические\n")
                f.write("     повреждения и залитие после ремонта.\n\n")
                f.write("  3. Претензии по качеству принимаются в течение\n")
                f.write("     гарантийного срока при наличии данного акта.\n\n")
                
                f.write("╠" + "═" * 68 + "╣\n")
                f.write("║" + " " * 25 + "ПОДПИСИ СТОРОН" + " " * 25 + "║\n")
                f.write("╠" + "═" * 68 + "╣\n\n")
                f.write("  Мастер: ____________________          Клиент: ____________________\n")
                f.write("          (подпись)                            (подпись)\n\n")
                f.write(f"  Дата получения: {datetime.now().strftime('%d.%m.%Y')}          Телефон: {format_phone(phone)}\n")
                f.write("╚" + "═" * 68 + "╝\n")
            
            return filename
        except Exception as e:
            print(f"❌ Ошибка создания акта выполненных работ: {e}")
            return None
