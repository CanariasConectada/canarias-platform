"""
Logger dedicado para debug de login y asignación de compañía.
Escribe tanto al logger de Odoo como a archivo para facilitar debugging.
"""
import logging
import os
from datetime import datetime

# Logger principal
logger = logging.getLogger('microsite_zones.login_company')

# Handler para archivo dedicado
LOG_DIR = '/home/odoo/logs'
LOG_FILE = os.path.join(LOG_DIR, 'login_company_debug.log')

def _ensure_log_dir():
    """Asegura que el directorio de logs existe."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)

class LoginCompanyDebugLogger:
    """Logger dedicado para seguimiento del flujo de login y compañía."""
    
    PREFIX = "[LOGIN_COMPANY]"
    
    def __init__(self):
        self._file_handler = None
        self._setup_file_handler()
    
    def _setup_file_handler(self):
        """Configura el handler de archivo si no está configurado."""
        try:
            _ensure_log_dir()
            # Crear handler de archivo (append mode)
            self._file_handler = logging.FileHandler(LOG_FILE, mode='a')
            self._file_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            self._file_handler.setFormatter(formatter)
            logger.addHandler(self._file_handler)
            logger.setLevel(logging.DEBUG)
        except Exception as e:
            logger.warning(f"{self.PREFIX} No se pudo configurar archivo de log: {e}")
    
    def log(self, level, message, **kwargs):
        """Loguea un mensaje con el prefijo y datos adicionales."""
        full_message = f"{self.PREFIX} {message}"
        if kwargs:
            data_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            full_message += f" | DATA: {data_str}"
        
        getattr(logger, level)(full_message)
        
        # También escribir directamente al archivo como respaldo
        try:
            with open(LOG_FILE, 'a') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"{timestamp} - {level.upper()} - {full_message}\n")
        except Exception:
            pass  # Ignorar errores de escritura a archivo
    
    def debug(self, message, **kwargs):
        self.log('debug', message, **kwargs)
    
    def info(self, message, **kwargs):
        self.log('info', message, **kwargs)
    
    def warning(self, message, **kwargs):
        self.log('warning', message, **kwargs)
    
    def error(self, message, **kwargs):
        self.log('error', message, **kwargs)

# Instancia global
debug_logger = LoginCompanyDebugLogger()
