"""
Enhanced Rich-based Logging
===========================

Replaces standard logging with Rich for:
- Colored, formatted console output
- Better progress tracking
- Structured log display
- Live progress bars

Phase 1: High Impact / Quick Wins
"""

import logging
import sys
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TaskProgressColumn
except ImportError:
    raise ImportError("Rich not installed. Run: pip install rich")


class RichLogger:
    """
    Enhanced logger using Rich for better output formatting.
    
    Features:
    - Colored log levels
    - Structured console output
    - Progress bars
    - Tables
    - Panels for important messages
    """
    
    def __init__(self, name: str = "ClawGold", log_file: Optional[str] = None):
        self.name = name
        self.console = Console()
        
        # Configure logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Add Rich handler
        rich_handler = RichHandler(
            console=self.console,
            show_time=True,
            show_level=True,
            show_path=True,
            markup=True,
            rich_tracebacks=True,
        )
        
        # Format: [time] [level] [module] message
        formatter = logging.Formatter(
            fmt="%(name)s",
            datefmt="[%X]"
        )
        rich_handler.setFormatter(formatter)
        self.logger.addHandler(rich_handler)
        
        # Optional file handler for persistence
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
    
    def debug(self, message: str):
        """Log debug message."""
        self.logger.debug(f"[DEBUG] {message}")
    
    def info(self, message: str):
        """Log info message."""
        self.logger.info(f"[INFO] {message}")
    
    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(f"[WARN] {message}")
    
    def error(self, message: str):
        """Log error message."""
        self.logger.error(f"[ERROR] {message}")
    
    def critical(self, message: str):
        """Log critical message."""
        self.logger.critical(f"[CRITICAL] {message}")
    
    def success(self, message: str):
        """Log success message (green)."""
        self.console.print(f"[green][OK] {message}[/green]")
    
    def failure(self, message: str):
        """Log failure message (red)."""
        self.console.print(f"[red][FAIL] {message}[/red]")
    
    def panel(self, message: str, title: str = "", style: str = "blue"):
        """Display a panel with message."""
        panel = Panel(message, title=title, style=style)
        self.console.print(panel)
    
    def table(self, data: list, columns: list, title: str = ""):
        """Display a table."""
        table = Table(title=title)
        
        for col in columns:
            table.add_column(col, style="cyan")
        
        for row in data:
            table.add_row(*[str(v) for v in row])
        
        self.console.print(table)
    
    def progress(self, total: int, description: str = "", transient: bool = True):
        """Create a progress bar context manager."""
        return Progress(
            SpinnerColumn(),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
            transient=transient,
        ) if total > 0 else None


# Global logger instance
_logger: Optional[RichLogger] = None


def get_logger(name: str = __name__) -> logging.Logger:
    """Get or create a Rich logger."""
    global _logger
    if _logger is None:
        _logger = RichLogger(name="ClawGold", log_file="logs/clawgold.log")
    return _logger.logger


def get_rich_logger(name: str = __name__) -> RichLogger:
    """Get the Rich logger instance for advanced features."""
    global _logger
    if _logger is None:
        _logger = RichLogger(name=name, log_file="logs/clawgold.log")
    return _logger
