"""
DTOs для передачи данных между слоями.
Используем Pydantic для валидации и легкой сериализации в JSON.
Принцип: SSOT для структуры ответа дашборда.
"""
from pydantic import BaseModel, Field
from typing import Any
from datetime import date
from decimal import Decimal


class MetricPoint(BaseModel):
    """Одна точка данных для графика (например, время + значение)."""
    label: str = Field(..., description="Метка оси X (дата, категория)")
    value: Decimal = Field(..., description="Числовое значение")
    meta: dict[str, Any] = Field(default_factory=dict, description="Дополнительные данные для тултипов")


class DashboardWidget(BaseModel):
    """Отдельный виджет дашборда (график, карточка, таблица)."""
    widget_id: str
    title: str
    widget_type: str = Field(..., description="chart_bar, chart_line, kpi_card, table")
    data: list[MetricPoint] | list[dict[str, Any]]
    config: dict[str, Any] = Field(default_factory=dict, description="Настройки цветов, осей и т.д.")


class DashboardResponse(BaseModel):
    """
    Полный контракт ответа дашборда.
    Это наш 'JSON Interface'. Любой потребитель (GUI, Web, File) работает с этой схемой.
    """
    generated_at: date
    filters_applied: dict[str, Any]
    widgets: list[DashboardWidget]
    summary: dict[str, Any] = Field(default_factory=dict, description="Общие итоги")

    def to_json(self, indent: int = 2) -> str:
        """Быстрая сериализация в JSON строку."""
        return self.model_dump_json(indent=indent)
