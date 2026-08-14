"""
Module Call Wrapper - Пример файла-обертки для модуля

Этот файл демонстрирует паттерн file-wrapper для модульной архитектуры v24.2:
1. Файл-обертка импортирует всё из реализации (plugins/* или modules/*_impl)
2. Реестр автоматически находит файлы module_*.py и загружает их
3. Модуль получает логгер, исключения и DI через базовый класс

Как создать новый модуль:

1. Создайте файл-обертку: modules/module_myfeature.py
   from plugins.myfeature import MyFeatureModule
   __all__ = ['MyFeatureModule']

2. Создайте папку реализации: plugins/myfeature/
   __init__.py      - экспортирует MyFeatureModule
   service.py       - бизнес-логика
   exceptions.py    - исключения модуля
   config.yaml      - конфигурация (опционально)

3. В plugins/myfeature/__init__.py:
   from core.module_registry import ModuleBase
   
   class MyFeatureModule(ModuleBase):
       name = "myfeature"
       version = "1.0.0"
       
       def on_init(self):
           self.log.info(f"{self.name} initialized")

Примечание: Этот файл (_module_call.py) НЕ является рабочим модулем,
это только пример и документация. Для создания рабочего модуля
создайте файл с именем module_*.py
"""

# Этот файл не содержит рабочей логики - это только документация
# Для создания модуля следуйте инструкции выше

__all__ = []  # Пустой список, так как это только пример

