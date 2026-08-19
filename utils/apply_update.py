"""
Скрипт-обновлятор. Запускается отдельно от основного приложения.
Заменяет файлы, удаляет временные данные и перезапускает приложение.
Использование: python apply_update.py <source_path> <target_dir> <app_script>
"""
import sys
import os
import shutil
import time
import subprocess

def apply_update(source_path, target_dir, app_script):
    print(f"[Updater] Начало обновления...")
    print(f"[Updater] Источник: {source_path}")
    print(f"[Updater] Цель: {target_dir}")
    
    # Ждем 2 секунды, чтобы основное приложение успело закрыться
    time.sleep(2)
    
    try:
        # Копируем все файлы из источника в целевую папку
        # Используем copy2 для сохранения метаданных, но игнорируем ошибки прав доступа
        for item in os.listdir(source_path):
            s = os.path.join(source_path, item)
            d = os.path.join(target_dir, item)
            
            # Не копируем сам скрипт обновлятора и временные папки
            if item == "apply_update.py" or item.startswith(".git"):
                continue
                
            if os.path.isdir(s):
                if os.path.exists(d):
                    shutil.rmtree(d)
                shutil.copytree(s, d)
                print(f"[Updater] Скопирована папка: {item}")
            else:
                if os.path.exists(d):
                    os.remove(d)
                shutil.copy2(s, d)
                print(f"[Updater] Скопирован файл: {item}")
        
        print("[Updater] Файлы успешно обновлены!")
        
        # Перезапуск приложения
        # Определяем, как запустить (python + скрипт или просто exe)
        if app_script.endswith('.py'):
            cmd = [sys.executable, app_script]
        else:
            cmd = [app_script]
            
        print(f"[Updater] Перезапуск приложения: {' '.join(cmd)}")
        subprocess.Popen(cmd, cwd=target_dir)
        
    except Exception as e:
        print(f"[Updater] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        input("Нажмите Enter для выхода...")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Ошибка аргументов! Использование: apply_update.py <source> <target> <script>")
        sys.exit(1)
        
    apply_update(sys.argv[1], sys.argv[2], sys.argv[3])
