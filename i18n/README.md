# I18N Integration Guide

## Обзор

Модуль интернационализации (i18n) обеспечивает многоязычную поддержку приложения ServiceUP.
Все тексты вынесены в `.ini` файлы для простоты редактирования и перевода.

## Структура файлов

```
i18n/
├── __init__.py          # Публичный API пакета
├── service.py           # Основной сервис I18NService
├── ru_RU.ini            # Русский язык (по умолчанию)
└── en_US.ini            # Английский язык (США)
```

## Формат файлов переводов

Файлы имеют формат INI с секциями:

```ini
[common]
app.name = ServiceUP
app.version = Версия {version}

[buttons]
button.save = Сохранить
button.cancel = Отмена

[order]
order.created = Заказ #{id} успешно создан
```

**Важно:** Ключи должны быть уникальны в пределах всего файла.
Рекомендуемый формат: `section.key = значение`

## Использование

### Базовое использование

```python
from i18n import t, set_language, get_i18n

# Получить перевод
text = t('buttons.button.save')  # "Сохранить"

# С параметрами подстановки
message = t('order.order.created', id=123)  # "Заказ #123 успешно создан"

# Сменить язык
set_language('en_US')
text = t('buttons.button.save')  # "Save"
```

### Через сервис

```python
from i18n import I18NService

i18n = I18NService()

# Получить перевод
text = i18n.get('buttons.button.save')

# Сменить язык
i18n.set_language('en_US')

# Получить доступный язык
name = i18n.get_language_name('ru_RU')  # "Русский"
```

### В GUI коде (CustomTkinter)

```python
from i18n import t

# При создании виджетов
self.btn_save = CTkButton(
    master=self,
    text=t('buttons.button.save'),
    command=self.save_handler
)

# При динамическом обновлении
self.label_status.configure(text=t('status.status.success'))
```

### В обработчиках ошибок

```python
from i18n import t

try:
    # ... код ...
except ValidationError as e:
    show_error(t('error.error.validation'))
except DatabaseError as e:
    show_error(t('error.error.db_connection'))
```

## Доступные языки

| Код      | Название      | Нативное название |
|----------|---------------|-------------------|
| ru_RU    | Russian       | Русский           |
| en_US    | English (US)  | English           |

## Добавление нового языка

1. Создать файл `i18n/xx_XX.ini`
2. Скопировать структуру из существующего файла
3. Перевести все значения
4. Добавить язык в `SUPPORTED_LOCALES` в `service.py`:

```python
SUPPORTED_LOCALES: ClassVar[dict[str, LocaleInfo]] = {
    'ru_RU': LocaleInfo('ru_RU', 'Russian', 'Русский', is_default=True),
    'en_US': LocaleInfo('en_US', 'English (US)', 'English'),
    'xx_XX': LocaleInfo('xx_XX', 'Language', 'Native Name'),
}
```

## Соглашения о ключах

### Формат ключей

- **Полный ключ**: `section.section.key` (рекомендуется)
  - Пример: `order.order.created`
  
- **Короткий ключ**: `section.key` (автоматически дополняется)
  - Пример: `order.created` → ищет `order.order.created`

### Именование секций

- Использовать множественное число для секций: `buttons`, `orders`, `errors`
- Ключи внутри секции: `button.save`, `order.created`, `error.validation`

### Категории ключей

| Секция        | Описание                    | Пример                      |
|---------------|----------------------------|----------------------------|
| common        | Общие тексты приложения     | `common.app.name`          |
| buttons       | Текст кнопок                | `buttons.button.save`      |
| status        | Статусы и сообщения         | `status.status.success`    |
| main          | Главное окно                | `main.main.title`          |
| order         | Заказы                      | `order.order.created`      |
| client        | Клиенты                     | `client.client.name`       |
| device        | Устройства                  | `device.device.type`       |
| finance       | Финансы                     | `finance.finance.income`   |
| reports       | Отчеты                      | `reports.reports.generate` |
| settings      | Настройки                   | `settings.settings.saved`  |
| notification  | Уведомления                 | `notification.notification.sent` |
| license       | Лицензия                    | `license/license.activated` |
| error         | Ошибки                      | `error.error.validation`   |
| confirm       | Подтверждения               | `confirm.confirm.delete`   |
| help          | Помощь                      | `help.help.welcome`        |
| date          | Даты и время                | `date.date.format`         |
| months        | Месяцы                      | `months.month.january`     |
| misc          | Разное                      | `misc.misc.records`        |

## Best Practices

### ✅ Делайте

1. **Используйте полный путь к ключам** для ясности:
   ```python
   t('buttons.button.save')  # ✅ Ясно и понятно
   ```

2. **Группируйте связанные тексты** в одной секции:
   ```ini
   [order]
   order.new = Новый заказ
   order.edit = Редактировать заказ
   order.delete = Удалить заказ
   ```

3. **Используйте параметры подстановки** для динамических значений:
   ```python
   t('order.order.created', id=order_id)
   ```

4. **Кэшируйте часто используемые переводы**:
   ```python
   SAVE_TEXT = t('buttons.button.save')  # Кэшировать
   ```

### ❌ Не делайте

1. **Не хардкодьте тексты** в коде:
   ```python
   # ❌ Плохо
   label = "Сохранить"
   
   # ✅ Хорошо
   label = t('buttons.button.save')
   ```

2. **Не используйте сложные выражения** в переводах:
   ```python
   # ❌ Плохо
   text = t('complex.text') + " " + str(count)
   
   # ✅ Хорошо
   text = t('simple.text', count=count)
   ```

3. **Не меняйте структуру ключей** после релиза:
   Это сломает совместимость и потребует обновления всех переводов.

## Архитектурные принципы

### SOLID

- **SRP (Single Responsibility)**: I18NService отвечает только за переводы
- **OCP (Open/Closed)**: Легко добавить новый язык без изменения кода
- **DIP (Dependency Inversion)**: Зависимость от абстракций (Protocol)

### DRY

- Все тексты в одном месте (SSOT - Single Source of Truth)
- Нет дублирования строк в коде

### Multi-threading

- Потокобезопасная загрузка переводов
- ThreadPoolExecutor для фоновой загрузки
- Lock для защиты общих данных

## Тестирование

```python
def test_i18n():
    from i18n import I18NService, t, set_language
    
    i18n = I18NService()
    
    # Test Russian
    assert i18n.get('buttons.button.save') == 'Сохранить'
    
    # Test English
    i18n.set_language('en_US')
    assert i18n.get('buttons.button.save') == 'Save'
    
    # Test interpolation
    i18n.set_language('ru_RU')
    assert 'Заказ #123' in i18n.get('order.order.created', id=123)
    
    print("✅ All tests passed!")
```

## Миграция существующего кода

### До

```python
# Старый код с хардкодом
label = CTkLabel(master, text="Сохранить")
show_error("Произошла ошибка")
```

### После

```python
# Новый код с i18n
from i18n import t

label = CTkLabel(master, text=t('buttons.button.save'))
show_error(t('error.error.generic'))
```

## Поддержка

При возникновении проблем:
1. Проверьте наличие ключа в `.ini` файле
2. Убедитесь, что язык загружен
3. Проверьте логирование (warning о недостающих ключах)
4. Используйте полный формат ключа: `section.section.key`
