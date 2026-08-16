"""gui.dialogs.device_form_parts — DeviceFormDialog разбит на mixin'ы по
разделу ответственности (блокировки, виджеты, фото, акты, сохранение),
чтобы не держать один файл на ~2000 строк (см. AUDIT_REPORT_v25.md, Task T).

Тот же приём, что и database/facade/ — множественное наследование, как
core/base.py уже собирает BaseService. gui/dialogs/device_form.py остаётся
единственной точкой импорта (DeviceFormDialog, _SCALAR_FIELD_NAMES) — ни
один внешний вызов не меняется."""
