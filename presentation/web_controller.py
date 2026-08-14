"""
Web контроллер для отдачи дашборда в формате JSON (REST API).
Принципы:
- SRP: Отвечает только за HTTP транспорт и сериализацию.
- DRY: Использует тот же сервис DashboardService, что и GUI.
- Don't Reinvent the Wheel: Стандартный формат JSON для веба.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json

from application.dashboard_service import DashboardService


class DashboardAPIHandler(BaseHTTPRequestHandler):
    """HTTP обработчик для REST API дашбордов."""
    
    # Инъекция зависимости через класс (для простоты примера)
    service: DashboardService | None = None

    def do_GET(self):
        """Обработка GET запросов."""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path != "/api/dashboard":
            self.send_error(404, "Not Found")
            return

        # Парсинг query параметров
        query_params = parse_qs(parsed_path.query)
        
        try:
            # Вызов общего сервиса (того же, что использует GUI)
            result = self.service.get_dashboard_data(
                date_from=query_params.get("date_from", [None])[0],
                date_to=query_params.get("date_to", [None])[0],
                status=query_params.get("status", [None])[0],
                priority=query_params.get("priority", [None])[0],
                client_id=int(query_params.get("client_id", [None])[0]) if query_params.get("client_id") else None
            )
            
            # Сериализация DTO в JSON
            response_body = result.to_json()
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(response_body.encode("utf-8"))
            
        except ValueError as e:
            self.send_error(400, f"Invalid parameters: {e}")
        except Exception as e:
            self.send_error(500, f"Internal error: {e}")

    def log_message(self, format, *args):
        """Переопределение логирования для чистоты вывода."""
        print(f"[API] {args[0]}")


def run_web_server(service: DashboardService, port: int = 8000):
    """Запуск простого HTTP сервера для демонстрации."""
    DashboardAPIHandler.service = service
    
    server_address = ("", port)
    httpd = HTTPServer(server_address, DashboardAPIHandler)
    
    print(f"Dashboard API запущен на http://localhost:{port}/api/dashboard")
    print("Пример запроса: curl http://localhost:8000/api/dashboard?status=new")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
