"""
Reports Plugin - Report generation and printing functionality.

This plugin encapsulates all report-related functionality:
- PDF report generation
- Print form templates
- Report customization
- Export to various formats

Principles:
- SRP: Only report generation logic
- DIP: Depends on abstractions
- Don't Reinvent: Uses existing libraries (reportlab, etc.)
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from core.plugin_system import IPlugin, PluginMetadata, get_plugin_manager
from core.base import BaseGenerator, BaseService


# =============================================================================
# DOMAIN ENTITIES
# =============================================================================

@dataclass
class ReportTemplate:
    """Report template entity."""
    id: int
    name: str
    description: str
    template_type: str  # 'pdf', 'html', 'docx'
    content: str  # Template content/path
    variables: List[str]
    is_active: bool = True
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class GeneratedReport:
    """Generated report entity."""
    id: int
    template_id: int
    generated_at: datetime
    file_path: str
    file_size: int
    format: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# =============================================================================
# COMMANDS
# =============================================================================

@dataclass
class GenerateReportCommand:
    """Command to generate a report."""
    template_id: int
    data: Dict[str, Any]
    output_path: Optional[str] = None
    format: str = "pdf"


@dataclass
class PrintReportCommand:
    """Command to print a report."""
    report_id: int
    printer_name: Optional[str] = None
    copies: int = 1
    duplex: bool = False


@dataclass
class CreateTemplateCommand:
    """Command to create a new report template."""
    name: str
    description: str
    template_type: str
    content: str
    variables: List[str]


# =============================================================================
# QUERIES
# =============================================================================

@dataclass
class GetTemplateByIdQuery:
    """Query to get template by ID."""
    template_id: int


@dataclass
class GetActiveTemplatesQuery:
    """Query to get all active templates."""
    template_type: Optional[str] = None


@dataclass
class GetReportByIdQuery:
    """Query to get generated report by ID."""
    report_id: int


# =============================================================================
# GENERATORS
# =============================================================================

class IPDFGenerator(BaseGenerator):
    """Interface for PDF generators."""
    
    def generate(self, template: str, data: Dict[str, Any]) -> bytes:
        """Generate PDF from template and data."""
        pass
    
    def save_to_file(self, pdf_bytes: bytes, path: str) -> bool:
        """Save PDF to file."""
        pass
    
    def add_watermark(self, pdf_bytes: bytes, text: str) -> bytes:
        """Add watermark to PDF."""
        pass


class IReportRepository:
    """Interface for report repository."""
    
    def get_template_by_id(self, template_id: int) -> Optional[ReportTemplate]:
        """Get template by ID."""
        pass
    
    def get_active_templates(self, template_type: Optional[str] = None) -> List[ReportTemplate]:
        """Get all active templates."""
        pass
    
    def save_template(self, template: ReportTemplate) -> bool:
        """Save template."""
        pass
    
    def save_report(self, report: GeneratedReport) -> bool:
        """Save generated report record."""
        pass
    
    def get_report_by_id(self, report_id: int) -> Optional[GeneratedReport]:
        """Get generated report by ID."""
        pass


# =============================================================================
# SERVICES
# =============================================================================

class ReportService(BaseService):
    """
    Report application service.
    
    Handles:
    - Report generation workflow
    - Template management
    - Print job coordination
    """
    
    def __init__(self, pdf_generator: IPDFGenerator, report_repository: IReportRepository):
        self._pdf_generator = pdf_generator
        self._repo = report_repository
    
    def generate_report(self, command: GenerateReportCommand) -> Optional[GeneratedReport]:
        """Generate a report from template."""
        try:
            self.logger.info(f"Generating report from template {command.template_id}")
            
            # Get template
            template = self._repo.get_template_by_id(command.template_id)
            if not template:
                self.logger.error(f"Template {command.template_id} not found")
                return None
            
            if not template.is_active:
                self.logger.warning(f"Template {template.name} is not active")
                return None
            
            # Generate PDF
            pdf_bytes = self.safe_execute(
                self._pdf_generator.generate,
                template.content,
                command.data,
                default=None
            )
            
            if not pdf_bytes:
                self.logger.error("Failed to generate PDF")
                return None
            
            # Determine output path
            if command.output_path:
                output_path = command.output_path
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"reports/{template.name}_{timestamp}.{command.format}"
            
            # Save to file
            if not self._pdf_generator.save_to_file(pdf_bytes, output_path):
                self.logger.error(f"Failed to save report to {output_path}")
                return None
            
            # Create report record
            report = GeneratedReport(
                id=0,  # Will be assigned by repository
                template_id=command.template_id,
                generated_at=datetime.now(),
                file_path=output_path,
                file_size=len(pdf_bytes),
                format=command.format,
                metadata={
                    'template_name': template.name,
                    'generated_by': 'system',
                    'data_hash': hash(str(command.data))
                }
            )
            
            # Save report record
            if self._repo.save_report(report):
                self.logger.info(f"Report generated successfully: {output_path}")
                return report
            
            return None
            
        except Exception as e:
            self.logger.exception(f"Error generating report: {e}")
            return None
    
    def print_report(self, command: PrintReportCommand) -> bool:
        """Send report to printer."""
        try:
            self.logger.info(f"Printing report {command.report_id}")
            
            # Get report
            report = self._repo.get_report_by_id(command.report_id)
            if not report:
                self.logger.error(f"Report {command.report_id} not found")
                return False
            
            # TODO: Implement actual printing logic
            # This would use platform-specific printing APIs
            self.logger.info(f"Sending {report.file_path} to printer {command.printer_name or 'default'}")
            
            return True
            
        except Exception as e:
            self.logger.exception(f"Error printing report: {e}")
            return False
    
    def create_template(self, command: CreateTemplateCommand) -> Optional[ReportTemplate]:
        """Create a new report template."""
        try:
            template = ReportTemplate(
                id=0,
                name=command.name,
                description=command.description,
                template_type=command.template_type,
                content=command.content,
                variables=command.variables
            )
            
            if self._repo.save_template(template):
                self.logger.info(f"Template '{template.name}' created successfully")
                return template
            
            return None
            
        except Exception as e:
            self.logger.exception(f"Error creating template: {e}")
            return None
    
    def get_templates(self, template_type: Optional[str] = None) -> List[ReportTemplate]:
        """Get active templates."""
        return self.safe_execute(
            self._repo.get_active_templates,
            template_type,
            default=[]
        )


# =============================================================================
# PLUGIN IMPLEMENTATION
# =============================================================================

class ReportsPlugin(IPlugin):
    """Reports feature plugin."""
    
    def __init__(self):
        self._service: Optional[ReportService] = None
        self._pdf_generator: Optional[IPDFGenerator] = None
        self._repository: Optional[IReportRepository] = None
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="reports",
            version="1.0.0",
            description="Report generation and printing system",
            author="ServiceUp Team",
            dependencies=["orders", "clients"],  # Needs order/client data
            min_core_version="24.0",
            standalone=False
        )
    
    def initialize(self) -> bool:
        """Initialize reports plugin."""
        try:
            self.logger.info("Initializing Reports Plugin")
            
            # TODO: Get dependencies from DI container
            # self._pdf_generator = self._app.get_service(IPDFGenerator)
            # self._repository = self._app.get_repository(IReportRepository)
            # self._service = ReportService(self._pdf_generator, self._repository)
            
            self.logger.info("Reports Plugin initialized successfully")
            return True
            
        except Exception as e:
            self.logger.exception(f"Failed to initialize Reports Plugin: {e}")
            return False
    
    def shutdown(self) -> None:
        """Cleanup reports plugin resources."""
        self.logger.info("Shutting down Reports Plugin")
        self._service = None
        self._pdf_generator = None
        self._repository = None
    
    def get_api(self) -> Optional[ReportService]:
        """Return reports service API."""
        return self._service
    
    def configure(self, config: dict) -> None:
        """Configure reports plugin."""
        self.logger.info(f"Configuring Reports Plugin: {config}")


# =============================================================================
# PLUGIN REGISTRATION
# =============================================================================

def register_plugin():
    """Register the Reports plugin with the plugin manager."""
    plugin_manager = get_plugin_manager()
    plugin = ReportsPlugin()
    plugin_manager.register(plugin)
    return plugin


__all__ = [
    # Entities
    'ReportTemplate',
    'GeneratedReport',
    # Commands
    'GenerateReportCommand',
    'PrintReportCommand',
    'CreateTemplateCommand',
    # Queries
    'GetTemplateByIdQuery',
    'GetActiveTemplatesQuery',
    'GetReportByIdQuery',
    # Interfaces
    'IPDFGenerator',
    'IReportRepository',
    # Service
    'ReportService',
    # Plugin
    'ReportsPlugin',
    'register_plugin',
]
