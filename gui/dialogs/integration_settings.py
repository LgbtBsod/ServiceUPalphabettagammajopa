"""
Integration Settings Dialog

GUI for configuring notification integrations:
- Telegram Bot
- WhatsApp Business
- VK Messages
- Email (SMTP)
- Bluetooth Call Forwarding
"""

import tkinter as tk
from typing import Optional, Dict, Any, Callable
import customtkinter as ctk
from tkinter import messagebox

from services.notifications import NotificationChannel
from services.bluetooth import get_bluetooth_service


class IntegrationSettingsDialog(ctk.CTkToplevel):
    """Dialog for configuring integration settings."""
    
    def __init__(
        self,
        parent: ctk.CTk,
        title: str = "Интеграции",
        on_save: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        super().__init__(parent)
        
        self.title(title)
        self.geometry("700x600")
        self.resizable(False, False)
        self.on_save_callback = on_save
        
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)  # Content area
        
        self._create_header()
        self._create_tabs()
        self._create_footer()
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
    
    def _create_header(self):
        """Create dialog header."""
        header_frame = ctk.CTkFrame(self, height=60)
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        header_frame.grid_propagate(False)
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="Настройки интеграций",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=20)
        
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Настройте подключение ботов, почты и телефонии",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        subtitle_label.pack()
    
    def _create_tabs(self):
        """Create tabbed interface for different integration types."""
        self.tabview = ctk.CTkTabview(self, width=660, height=480)
        self.tabview.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        
        # Add tabs
        self.tabview.add("Telegram")
        self.tabview.add("WhatsApp")
        self.tabview.add("VKontakte")
        self.tabview.add("Email")
        self.tabview.add("Bluetooth")
        
        # Setup each tab
        self._setup_telegram_tab()
        self._setup_whatsapp_tab()
        self._setup_vk_tab()
        self._setup_email_tab()
        self._setup_bluetooth_tab()
    
    def _setup_telegram_tab(self):
        """Setup Telegram bot configuration tab."""
        tab = self.tabview.tab("Telegram")
        
        # Enable checkbox
        self.telegram_enabled = ctk.CTkCheckBox(
            tab,
            text="Включить Telegram уведомления",
            font=ctk.CTkFont(size=14)
        )
        self.telegram_enabled.grid(row=0, column=0, padx=30, pady=(20, 10), sticky="w")
        
        # Bot token
        ctk.CTkLabel(tab, text="Token бота:", font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.telegram_token = ctk.CTkEntry(tab, width=550, placeholder_text="BotFather token")
        self.telegram_token.grid(row=2, column=0, padx=30, pady=5, sticky="w")
        
        # Chat ID
        ctk.CTkLabel(tab, text="Chat ID (получить через @userinfobot):", font=ctk.CTkFont(size=13)).grid(
            row=3, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.telegram_chat_id = ctk.CTkEntry(tab, width=550, placeholder_text="Numeric chat ID")
        self.telegram_chat_id.grid(row=4, column=0, padx=30, pady=5, sticky="w")
        
        # Test button
        test_btn = ctk.CTkButton(
            tab,
            text="🧪 Тестировать подключение",
            width=200,
            command=self._test_telegram
        )
        test_btn.grid(row=5, column=0, padx=30, pady=20, sticky="w")
        
        # Info label
        info_label = ctk.CTkLabel(
            tab,
            text="💡 Как получить токен:\n1. Откройте @BotFather в Telegram\n2. Отправьте /newbot\n3. Следуйте инструкциям\n4. Скопируйте полученный токен",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="left"
        )
        info_label.grid(row=6, column=0, padx=30, pady=10, sticky="w")
    
    def _setup_whatsapp_tab(self):
        """Setup WhatsApp Business configuration tab."""
        tab = self.tabview.tab("WhatsApp")
        
        self.whatsapp_enabled = ctk.CTkCheckBox(
            tab,
            text="Включить WhatsApp уведомления",
            font=ctk.CTkFont(size=14)
        )
        self.whatsapp_enabled.grid(row=0, column=0, padx=30, pady=(20, 10), sticky="w")
        
        # API Key
        ctk.CTkLabel(tab, text="API Key (Twilio/360dialog):", font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.whatsapp_api_key = ctk.CTkEntry(tab, width=550, placeholder_text="API key from provider")
        self.whatsapp_api_key.grid(row=2, column=0, padx=30, pady=5, sticky="w")
        
        # Phone Number ID
        ctk.CTkLabel(tab, text="Phone Number ID:", font=ctk.CTkFont(size=13)).grid(
            row=3, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.whatsapp_phone_id = ctk.CTkEntry(tab, width=550, placeholder_text="Business phone number ID")
        self.whatsapp_phone_id.grid(row=4, column=0, padx=30, pady=5, sticky="w")
        
        # Info
        info_label = ctk.CTkLabel(
            tab,
            text="💡 Требуется аккаунт WhatsApp Business API\nПоддерживаемые провайдеры: Twilio, 360dialog, MessageBird",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        info_label.grid(row=5, column=0, padx=30, pady=20, sticky="w")
    
    def _setup_vk_tab(self):
        """Setup VKontakte configuration tab."""
        tab = self.tabview.tab("VKontakte")
        
        self.vk_enabled = ctk.CTkCheckBox(
            tab,
            text="Включить VK уведомления",
            font=ctk.CTkFont(size=14)
        )
        self.vk_enabled.grid(row=0, column=0, padx=30, pady=(20, 10), sticky="w")
        
        # Service Key
        ctk.CTkLabel(tab, text="Service Key (из настроек сообщества):", font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.vk_service_key = ctk.CTkEntry(tab, width=550, placeholder_text="vk1.a....")
        self.vk_service_key.grid(row=2, column=0, padx=30, pady=5, sticky="w")
        
        # Group ID
        ctk.CTkLabel(tab, text="Group ID (сообщество):", font=ctk.CTkFont(size=13)).grid(
            row=3, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.vk_group_id = ctk.CTkEntry(tab, width=550, placeholder_text="Numeric group ID")
        self.vk_group_id.grid(row=4, column=0, padx=30, pady=5, sticky="w")
    
    def _setup_email_tab(self):
        """Setup Email (SMTP) configuration tab."""
        tab = self.tabview.tab("Email")
        
        self.email_enabled = ctk.CTkCheckBox(
            tab,
            text="Включить Email уведомления",
            font=ctk.CTkFont(size=14)
        )
        self.email_enabled.grid(row=0, column=0, padx=30, pady=(20, 10), sticky="w")
        
        # SMTP Server
        ctk.CTkLabel(tab, text="SMTP сервер:", font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.email_smtp_server = ctk.CTkEntry(tab, width=550, placeholder_text="smtp.gmail.com")
        self.email_smtp_server.grid(row=2, column=0, padx=30, pady=5, sticky="w")
        
        # Port
        ctk.CTkLabel(tab, text="Порт:", font=ctk.CTkFont(size=13)).grid(
            row=3, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.email_port = ctk.CTkEntry(tab, width=200, placeholder_text="587")
        self.email_port.grid(row=3, column=0, padx=300, pady=5, sticky="w")
        
        # Email
        ctk.CTkLabel(tab, text="Email отправителя:", font=ctk.CTkFont(size=13)).grid(
            row=4, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.email_from = ctk.CTkEntry(tab, width=550, placeholder_text="your@email.com")
        self.email_from.grid(row=5, column=0, padx=30, pady=5, sticky="w")
        
        # Password
        ctk.CTkLabel(tab, text="Пароль приложения:", font=ctk.CTkFont(size=13)).grid(
            row=6, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        self.email_password = ctk.CTkEntry(tab, width=550, show="*", placeholder_text="App password")
        self.email_password.grid(row=7, column=0, padx=30, pady=5, sticky="w")
        
        # Info
        info_label = ctk.CTkLabel(
            tab,
            text="💡 Для Gmail используйте 'Пароль приложений'\nНастройки → Безопасность → Двухфакторная аутентификация → Пароли приложений",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        info_label.grid(row=8, column=0, padx=30, pady=10, sticky="w")
    
    def _setup_bluetooth_tab(self):
        """Setup Bluetooth call forwarding configuration tab."""
        tab = self.tabview.tab("Bluetooth")
        
        self.bluetooth_enabled = ctk.CTkCheckBox(
            tab,
            text="Включить переадресацию звонков через Bluetooth",
            font=ctk.CTkFont(size=14)
        )
        self.bluetooth_enabled.grid(row=0, column=0, padx=30, pady=(20, 10), sticky="w")
        
        # Status frame
        status_frame = ctk.CTkFrame(tab, fg_color="transparent")
        status_frame.grid(row=1, column=0, padx=30, pady=10, sticky="w")
        
        self.bt_status_label = ctk.CTkLabel(
            status_frame,
            text="❌ Не подключено",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="red"
        )
        self.bt_status_label.pack(side="left")
        
        # Scan button
        self.scan_btn = ctk.CTkButton(
            tab,
            text="🔍 Поиск устройств",
            width=200,
            command=self._scan_bluetooth_devices
        )
        self.scan_btn.grid(row=2, column=0, padx=30, pady=10, sticky="w")
        
        # Device selection
        ctk.CTkLabel(tab, text="Выберите устройство:", font=ctk.CTkFont(size=13)).grid(
            row=3, column=0, padx=30, pady=(10, 5), sticky="w"
        )
        
        self.bt_device_var = ctk.StringVar(value="Нет устройств")
        self.bt_device_combo = ctk.CTkOptionMenu(
            tab,
            variable=self.bt_device_var,
            values=["Нет устройств"],
            width=550,
            state="disabled"
        )
        self.bt_device_combo.grid(row=4, column=0, padx=30, pady=5, sticky="w")
        
        # Connect button
        self.connect_btn = ctk.CTkButton(
            tab,
            text="📱 Подключиться",
            width=200,
            state="disabled",
            command=self._connect_bluetooth_device
        )
        self.connect_btn.grid(row=5, column=0, padx=30, pady=10, sticky="w")
        
        # Features info
        features_frame = ctk.CTkFrame(tab, fg_color=("gray90", "gray10"))
        features_frame.grid(row=6, column=0, padx=30, pady=20, sticky="ew")
        
        features_title = ctk.CTkLabel(
            features_frame,
            text="🎧 Возможности после подключения:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        features_title.pack(padx=10, pady=(10, 5), anchor="w")
        
        features_list = [
            "• Ответ на звонки с компьютера",
            "• Использование ПК как гарнитуры",
            "• Исходящие звонки через телефон",
            "• Отображение информации о звонящем",
            "• Управление звонком (mute, hangup)"
        ]
        
        for feature in features_list:
            ctk.CTkLabel(
                features_frame,
                text=feature,
                font=ctk.CTkFont(size=11),
                text_color="gray"
            ).pack(padx=20, pady=2, anchor="w")
        
        # Store bluetooth service
        self.bt_service = get_bluetooth_service()
        self.bt_devices = []
    
    def _create_footer(self):
        """Create dialog footer with action buttons."""
        footer_frame = ctk.CTkFrame(self, height=60, fg_color="transparent")
        footer_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 20))
        footer_frame.grid_propagate(False)
        
        # Buttons frame
        btn_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        btn_frame.pack(expand=True)
        
        # Cancel button
        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Отмена",
            width=120,
            fg_color="transparent",
            border_width=2,
            command=self.destroy
        )
        cancel_btn.pack(side="left", padx=10)
        
        # Save button
        save_btn = ctk.CTkButton(
            btn_frame,
            text="💾 Сохранить",
            width=150,
            command=self._save_settings
        )
        save_btn.pack(side="right", padx=10)
    
    def _test_telegram(self):
        """Test Telegram connection."""
        token = self.telegram_token.get().strip()
        chat_id = self.telegram_chat_id.get().strip()
        
        if not token or not chat_id:
            messagebox.showwarning("Предупреждение", "Заполните Token и Chat ID")
            return
        
        messagebox.showinfo(
            "Тестирование",
            "Отправка тестового сообщения...\n\n(В production здесь будет реальный запрос к Telegram API)"
        )
    
    def _scan_bluetooth_devices(self):
        """Scan for Bluetooth devices."""
        self.scan_btn.configure(state="disabled", text="Поиск...")
        
        async def scan():
            import asyncio
            devices = await self.bt_service.scan_devices(timeout=3)
            self.bt_devices = devices
            
            if devices:
                device_names = [f"{d.name} ({d.address})" for d in devices]
                self.bt_device_var.set(device_names[0])
                self.bt_device_combo.configure(values=device_names, state="normal")
                self.connect_btn.configure(state="normal")
                self.bt_status_label.configure(
                    text=f"✅ Найдено устройств: {len(devices)}",
                    text_color="green"
                )
            else:
                self.bt_status_label.configure(
                    text="❌ Устройства не найдены",
                    text_color="red"
                )
            
            self.scan_btn.configure(state="normal", text="🔍 Поиск устройств")
        
        # Run async in background
        import threading
        thread = threading.Thread(target=lambda: asyncio.run(scan()))
        thread.start()
    
    def _connect_bluetooth_device(self):
        """Connect to selected Bluetooth device."""
        selected = self.bt_device_var.get()
        if not selected or selected == "Нет устройств":
            return
        
        # Extract address from selection
        address = selected.split("(")[-1].rstrip(")")
        
        async def connect():
            import asyncio
            try:
                device = await self.bt_service.connect_device(address)
                self.bt_status_label.configure(
                    text=f"✅ Подключено: {device.name}",
                    text_color="green"
                )
                self.connect_btn.configure(text="✓ Подключено", state="disabled")
                
                messagebox.showinfo(
                    "Успешно",
                    f"Устройство {device.name} подключено!\n\n"
                    "Теперь вы можете:\n"
                    "• Принимать звонки на компьютере\n"
                    "• Использовать ПК как гарнитуру\n"
                    "• Совершать исходящие звонки"
                )
            except Exception as e:
                messagebox.showerror("Ошибка подключения", str(e))
        
        import threading
        thread = threading.Thread(target=lambda: asyncio.run(connect()))
        thread.start()
    
    def _save_settings(self):
        """Collect and save all settings."""
        settings = {
            "telegram": {
                "enabled": self.telegram_enabled.get(),
                "token": self.telegram_token.get().strip(),
                "chat_id": self.telegram_chat_id.get().strip()
            },
            "whatsapp": {
                "enabled": self.whatsapp_enabled.get(),
                "api_key": self.whatsapp_api_key.get().strip(),
                "phone_id": self.whatsapp_phone_id.get().strip()
            },
            "vk": {
                "enabled": self.vk_enabled.get(),
                "service_key": self.vk_service_key.get().strip(),
                "group_id": self.vk_group_id.get().strip()
            },
            "email": {
                "enabled": self.email_enabled.get(),
                "smtp_server": self.email_smtp_server.get().strip(),
                "port": int(self.email_port.get().strip() or 587),
                "from_email": self.email_from.get().strip(),
                "password": self.email_password.get()
            },
            "bluetooth": {
                "enabled": self.bluetooth_enabled.get(),
                "connected_device": self.bt_device_var.get() if self.bt_device_var.get() != "Нет устройств" else None
            }
        }
        
        if self.on_save_callback:
            self.on_save_callback(settings)
        
        messagebox.showinfo("Сохранено", "Настройки интеграций успешно сохранены!")
        self.destroy()


def show_integration_settings(
    parent: ctk.CTk,
    on_save: Optional[Callable[[Dict[str, Any]], None]] = None
):
    """Show integration settings dialog."""
    dialog = IntegrationSettingsDialog(parent, on_save=on_save)
    dialog.transient(parent)
    dialog.grab_set()
