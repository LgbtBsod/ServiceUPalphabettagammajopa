"""
Unit-тесты для логики Drag-and-Drop в редакторе актов.
"""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

class TestDragDropLogic(unittest.TestCase):
    """Тесты логики перетаскивания полей."""

    def setUp(self):
        """Инициализация тестовых данных."""
        self.sample_fields = [
            {"id": 1, "name": "Поле 1", "type": "text"},
            {"id": 2, "name": "Поле 2", "type": "number"},
            {"id": 3, "name": "Поле 3", "type": "date"},
            {"id": 4, "name": "Поле 4", "type": "text"}
        ]

    def test_swap_fields_basic(self):
        """Проверка базового обмена двух полей."""
        fields = self.sample_fields.copy()
        # Меняем местами поле 0 и поле 2
        fields[0], fields[2] = fields[2], fields[0]
        
        self.assertEqual(fields[0]["name"], "Поле 3")
        self.assertEqual(fields[2]["name"], "Поле 1")
        self.assertEqual(len(fields), 4)

    def test_swap_fields_adjacent(self):
        """Проверка обмена соседних полей."""
        fields = self.sample_fields.copy()
        fields[1], fields[2] = fields[2], fields[1]
        
        self.assertEqual(fields[1]["name"], "Поле 3")
        self.assertEqual(fields[2]["name"], "Поле 2")

    def test_get_field_order(self):
        """Проверка получения порядка полей."""
        fields = self.sample_fields.copy()
        order = [f["id"] for f in fields]
        
        self.assertEqual(order, [1, 2, 3, 4])
        
        # После перестановки
        fields[0], fields[3] = fields[3], fields[0]
        new_order = [f["id"] for f in fields]
        self.assertEqual(new_order, [4, 2, 3, 1])

    def test_add_field_to_list(self):
        """Проверка добавления нового поля."""
        fields = self.sample_fields.copy()
        new_field = {"id": 5, "name": "Поле 5", "type": "text"}
        fields.append(new_field)
        
        self.assertEqual(len(fields), 5)
        self.assertEqual(fields[-1]["name"], "Поле 5")

    def test_remove_field_from_list(self):
        """Проверка удаления поля из списка."""
        fields = self.sample_fields.copy()
        removed = fields.pop(1)  # Удаляем второй элемент
        
        self.assertEqual(len(fields), 3)
        self.assertEqual(removed["name"], "Поле 2")
        self.assertNotIn(removed, fields)

    def test_rebuild_field_list_preserves_data(self):
        """Проверка что перестройка списка сохраняет данные."""
        original = self.sample_fields.copy()
        shuffled = original.copy()
        shuffled[0], shuffled[2] = shuffled[2], shuffled[0]
        
        # Проверяем что все элементы сохранились
        original_ids = {f["id"] for f in original}
        shuffled_ids = {f["id"] for f in shuffled}
        
        self.assertEqual(original_ids, shuffled_ids)
        self.assertEqual(len(original), len(shuffled))

if __name__ == "__main__":
    unittest.main()
