"""
PDF Builder with Drag-and-Drop Field Editor

SRP: Handles PDF report generation with customizable field order.
Uses ReportLab for PDF generation.
Provides builder pattern for flexible PDF creation.

Features:
- Drag-and-drop field ordering (GUI integration ready)
- Live preview generation
- Template-based rendering
- Multi-threaded PDF generation
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from enum import Enum
from pathlib import Path
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import black, white, HexColor
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


class FieldType(str, Enum):
    """Available field types for PDF forms - SSOT"""
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    MONEY = "money"
    IMAGE = "image"
    TABLE = "table"
    QR_CODE = "qr_code"
    SIGNATURE = "signature"
    CUSTOM = "custom"


@dataclass
class PDFField:
    """Represents a single field in PDF form"""
    name: str
    label: str
    field_type: FieldType
    value: Any = None
    order: int = 0
    visible: bool = True
    style_kwargs: dict = field(default_factory=dict)
    
    def render(self, styles: dict) -> list:
        """Render field as ReportLab flowables"""
        if not self.visible or self.value is None:
            return []
        
        flowables = []
        
        # Format value based on type
        formatted_value = self._format_value()
        
        # Create label
        label_style = styles.get('FieldLabel', styles['Normal'])
        flowables.append(Paragraph(f"<b>{self.label}:</b>", label_style))
        
        # Create value
        value_style = styles.get('FieldValue', styles['Normal'])
        flowables.append(Paragraph(formatted_value, value_style))
        flowables.append(Spacer(1, 5 * mm))
        
        return flowables
    
    def _format_value(self) -> str:
        """Format value based on field type"""
        if self.value is None:
            return ""
        
        if self.field_type == FieldType.MONEY:
            return f"{float(self.value):,.2f} ₽"
        elif self.field_type == FieldType.DATE:
            if isinstance(self.value, datetime):
                return self.value.strftime("%d.%m.%Y %H:%M")
            return str(self.value)
        elif self.field_type ==FieldType.NUMBER:
            return f"{float(self.value):,.2f}"
        else:
            return str(self.value)


@dataclass
class PDFSection:
    """Represents a section in PDF document"""
    title: str
    fields: list[PDFField] = field(default_factory=list)
    order: int = 0
    
    def add_field(self, field: PDFField):
        """Add field to section"""
        self.fields.append(field)
        self.fields.sort(key=lambda f: f.order)
    
    def render(self, styles: dict) -> list:
        """Render section as ReportLab flowables"""
        flowables = []
        
        # Section title
        title_style = styles.get('SectionTitle', styles['Heading2'])
        flowables.append(Paragraph(self.title, title_style))
        flowables.append(Spacer(1, 5 * mm))
        
        # Render fields
        for field in self.fields:
            flowables.extend(field.render(styles))
        
        flowables.append(Spacer(1, 10 * mm))
        return flowables


class PDFBuilder:
    """
    Builder pattern for PDF documents.
    
    Allows flexible construction of PDF reports with:
    - Custom field ordering
    - Section management
    - Style customization
    - Preview generation
    """
    
    def __init__(self, filename: str, title: str = "Report"):
        self.filename = filename
        self.title = title
        self.sections: list[PDFSection] = []
        self.styles = self._create_styles()
        self.metadata: dict = {}
        self.footer_text: str = ""
    
    def _create_styles(self) -> dict:
        """Create default paragraph styles"""
        styles = getSampleStyleSheet()
        
        # Custom styles
        styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=HexColor('#2c3e50'),
            spaceAfter=12,
            alignment=TA_CENTER,
        ))
        
        styles.add(ParagraphStyle(
            name='FieldLabel',
            parent=styles['Normal'],
            fontSize=10,
            textColor=HexColor('#7f8c8d'),
            spaceAfter=3,
        ))
        
        styles.add(ParagraphStyle(
            name='FieldValue',
            parent=styles['Normal'],
            fontSize=11,
            textColor=black,
            spaceAfter=5,
        ))
        
        styles.add(ParagraphStyle(
            name='TableHeader',
            parent=styles['Normal'],
            fontSize=10,
            textColor=white,
            alignment=TA_CENTER,
        ))
        
        styles.add(ParagraphStyle(
            name='TableCell',
            parent=styles['Normal'],
            fontSize=9,
            textColor=black,
        ))
        
        return styles
    
    def add_section(self, section: PDFSection) -> 'PDFBuilder':
        """Add section to document"""
        self.sections.append(section)
        self.sections.sort(key=lambda s: s.order)
        return self
    
    def add_metadata(self, key: str, value: str) -> 'PDFBuilder':
        """Add PDF metadata"""
        self.metadata[key] = value
        return self
    
    def set_footer(self, text: str) -> 'PDFBuilder':
        """Set footer text"""
        self.footer_text = text
        return self
    
    def reorder_fields(self, section_index: int, field_order: list[int]) -> 'PDFBuilder':
        """
        Reorder fields in section (for DnD functionality).
        
        Args:
            section_index: Index of section to reorder
            field_order: List of field indices in new order
        """
        if 0 <= section_index < len(self.sections):
            section = self.sections[section_index]
            reordered_fields = [section.fields[i] for i in field_order if 0 <= i < len(section.fields)]
            section.fields = reordered_fields
            
            # Update order property
            for idx, field in enumerate(section.fields):
                field.order = idx
        
        return self
    
    def build(self) -> bytes:
        """
        Build PDF document.
        
        Returns:
            PDF content as bytes
        """
        from io import BytesIO
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            title=self.title,
        )
        
        # Add metadata
        for key, value in self.metadata.items():
            setattr(doc, key, value)
        
        # Build content
        content = []
        
        # Title
        title_style = self.styles.get('SectionTitle', self.styles['Heading1'])
        content.append(Paragraph(self.title, title_style))
        content.append(Spacer(1, 15 * mm))
        
        # Sections
        for section in self.sections:
            content.extend(section.render(self.styles))
        
        # Build PDF
        doc.build(content)
        
        return buffer.getvalue()
    
    async def build_async(self) -> bytes:
        """Build PDF asynchronously using thread pool"""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            return await loop.run_in_executor(executor, self.build)
    
    def save(self, path: Optional[str] = None) -> Path:
        """Save PDF to file"""
        pdf_path = Path(path or self.filename)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        
        content = self.build()
        pdf_path.write_bytes(content)
        
        return pdf_path
    
    def generate_preview(self) -> bytes:
        """Generate preview PDF (same as build, but for GUI preview)"""
        return self.build()


class ActBuilder(PDFBuilder):
    """
    Specialized builder for service acts/completion certificates.
    
    Pre-configured with standard sections for service reports.
    """
    
    def __init__(self, order_id: str, client_name: str):
        super().__init__(
            filename=f"act_{order_id}.pdf",
            title=f"Акт выполненных работ #{order_id}",
        )
        
        self.order_id = order_id
        self.client_name = client_name
        
        # Add standard sections
        self._add_standard_sections()
    
    def _add_standard_sections(self):
        """Add standard sections for service act"""
        # Client Information
        client_section = PDFSection(title="Информация о клиенте", order=1)
        client_section.add_field(PDFField(
            name="client_name",
            label="Клиент",
            field_type=FieldType.TEXT,
            value=self.client_name,
            order=1,
        ))
        client_section.add_field(PDFField(
            name="order_id",
            label="Номер заказа",
            field_type=FieldType.TEXT,
            value=self.order_id,
            order=2,
        ))
        self.add_section(client_section)
        
        # Device Information
        device_section = PDFSection(title="Устройство", order=2)
        device_section.add_field(PDFField(
            name="device_model",
            label="Модель",
            field_type=FieldType.TEXT,
            order=1,
        ))
        device_section.add_field(PDFField(
            name="device_serial",
            label="Серийный номер",
            field_type=FieldType.TEXT,
            order=2,
        ))
        device_section.add_field(PDFField(
            name="device_issue",
            label="Неисправность",
            field_type=FieldType.TEXT,
            order=3,
        ))
        self.add_section(device_section)
        
        # Work Performed
        work_section = PDFSection(title="Выполненные работы", order=3)
        work_section.add_field(PDFField(
            name="work_list",
            label="Работы",
            field_type=FieldType.TABLE,
            order=1,
        ))
        self.add_section(work_section)
        
        # Parts Used
        parts_section = PDFSection(title="Использованные запчасти", order=4)
        parts_section.add_field(PDFField(
            name="parts_list",
            label="Запчасти",
            field_type=FieldType.TABLE,
            order=1,
        ))
        self.add_section(parts_section)
        
        # Total Cost
        total_section = PDFSection(title="Стоимость работ", order=5)
        total_section.add_field(PDFField(
            name="labor_cost",
            label="Стоимость работ",
            field_type=FieldType.MONEY,
            order=1,
        ))
        total_section.add_field(PDFField(
            name="parts_cost",
            label="Стоимость запчастей",
            field_type=FieldType.MONEY,
            order=2,
        ))
        total_section.add_field(PDFField(
            name="total_cost",
            label="Итого",
            field_type=FieldType.MONEY,
            order=3,
        ))
        self.add_section(total_section)
        
        # Signatures
        signature_section = PDFSection(title="Подписи сторон", order=6)
        signature_section.add_field(PDFField(
            name="service_signature",
            label="От сервиса",
            field_type=FieldType.SIGNATURE,
            order=1,
        ))
        signature_section.add_field(PDFField(
            name="client_signature",
            label="От клиента",
            field_type=FieldType.SIGNATURE,
            order=2,
        ))
        self.add_section(signature_section)


# Factory function
def create_act_builder(order_id: str, client_name: str) -> ActBuilder:
    """Create pre-configured act builder"""
    return ActBuilder(order_id, client_name)
