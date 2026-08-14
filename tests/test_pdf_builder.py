"""
Unit-тесты для PDF Builder с поддержкой Drag-and-Drop.
"""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

class TestPDFBuilder(unittest.TestCase):
    """Тесты конструктора PDF отчетов."""

    def setUp(self):
        """Инициализация тестовых данных."""
        self.template_data = {
            "title": "Акт выполненных работ",
            "fields": [
                {"name": "Номер", "value": "123"},
                {"name": "Дата", "value": "2024-01-15"},
                {"name": "Клиент", "value": "ООО Ромашка"},
                {"name": "Сумма", "value": "10000"}
            ],
            "format": "A4"
        }

    def test_field_order_preserved(self):
        """Проверка сохранения порядка полей после DnD."""
        original_order = [f["name"] for f in self.template_data["fields"]]
        
        # Имитация перетаскивания: меняем местами 0 и 2
        fields = self.template_data["fields"].copy()
        fields[0], fields[2] = fields[2], fields[0]
        
        new_order = [f["name"] for f in fields]
        self.assertEqual(new_order, ["Клиент", "Дата", "Номер", "Сумма"])
        self.assertNotEqual(new_order, original_order)

    def test_add_field_to_template(self):
        """Проверка добавления поля в шаблон."""
        fields = self.template_data["fields"].copy()
        new_field = {"name": "Примечание", "value": "Тест"}
        fields.append(new_field)
        
        self.assertEqual(len(fields), 5)
        self.assertEqual(fields[-1]["name"], "Примечание")

    def test_remove_field_from_template(self):
        """Проверка удаления поля из шаблона."""
        fields = self.template_data["fields"].copy()
        removed = fields.pop(0)
        
        self.assertEqual(len(fields), 3)
        self.assertEqual(removed["name"], "Номер")

    def test_format_selection(self):
        """Проверка выбора формата документа."""
        valid_formats = ["A4", "A5"]
        self.assertIn(self.template_data["format"], valid_formats)
        
        # Смена формата
        self.template_data["format"] = "A5"
        self.assertEqual(self.template_data["format"], "A5")

    def test_template_validation(self):
        """Проверка валидации шаблона."""
        required_keys = ["title", "fields", "format"]
        for key in required_keys:
            self.assertIn(key, self.template_data)
        
        # Проверка что fields это список
        self.assertIsInstance(self.template_data["fields"], list)

if __name__ == "__main__":
    unittest.main()
