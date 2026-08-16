"""gui.main_window_parts — ServiceCenterApp разбит на mixin'ы по разделу
ответственности (окно/хром, построение виджетов, таблица заказов, диалоги
заказа, акты, финансы, PWA, периодический бэкап, прочие диалоги), чтобы не
держать один файл на ~2200 строк (см. AUDIT_REPORT_v25.md, Task T).

Тот же приём, что и database/facade/ и gui/dialogs/device_form_parts/ —
множественное наследование, как core/base.py уже собирает BaseService.
gui/main_window.py остаётся единственной точкой импорта (ServiceCenterApp) —
ни один внешний вызов не меняется."""
