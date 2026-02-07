"""
Logging Configuration for Agent System
Provides structured, in-depth logging for debugging and monitoring agent behavior.
"""

import logging
import sys
from datetime import datetime
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Add component/phase info if available
        component = getattr(record, 'component', 'SYSTEM')
        phase = getattr(record, 'phase', '')
        
        # Format the base message
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        
        if phase:
            prefix = f"{color}[{timestamp}] [{record.levelname}] [{component}] [{phase}]{reset}"
        else:
            prefix = f"{color}[{timestamp}] [{record.levelname}] [{component}]{reset}"
        
        record.msg = f"{prefix} {record.msg}"
        return super().format(record)


def get_logger(
    name: str,
    component: Optional[str] = None,
    level: int = logging.DEBUG
) -> logging.Logger:
    """
    Get a configured logger for a specific component.
    
    Args:
        name: Logger name (typically __name__)
        component: Component identifier (e.g., 'POSTGRES_TOOLS', 'SUPERVISOR')
        level: Logging level
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        logger.setLevel(level)
        
        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColoredFormatter('%(message)s'))
        logger.addHandler(console_handler)
    
    # Create a custom adapter that adds component info
    class ComponentAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            kwargs.setdefault('extra', {})
            kwargs['extra']['component'] = self.extra.get('component', 'SYSTEM')
            kwargs['extra']['phase'] = self.extra.get('phase', '')
            return msg, kwargs
    
    return ComponentAdapter(logger, {'component': component or name.upper()})


class PhaseLogger:
    """
    Context manager for logging agent execution phases.
    Automatically logs phase start/end with timing.
    """
    
    def __init__(self, logger: logging.Logger, phase_name: str):
        self.logger = logger
        self.phase_name = phase_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        if hasattr(self.logger, 'extra'):
            self.logger.extra['phase'] = self.phase_name
        self.logger.info(f"▶ Starting phase: {self.phase_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type:
            self.logger.error(f"✗ Phase failed: {self.phase_name} ({duration:.2f}s) - {exc_val}")
        else:
            self.logger.info(f"✓ Phase complete: {self.phase_name} ({duration:.2f}s)")
        
        if hasattr(self.logger, 'extra'):
            self.logger.extra['phase'] = ''
        
        return False  # Don't suppress exceptions


def log_tool_call(logger: logging.Logger, tool_name: str, args: dict, result: any = None, error: Exception = None):
    """Log a tool invocation with its arguments and result."""
    if error:
        logger.error(f"🔧 Tool '{tool_name}' FAILED with args={args}: {error}")
    elif result is not None:
        # Truncate long results for readability
        result_str = str(result)
        if len(result_str) > 200:
            result_str = result_str[:200] + "..."
        logger.debug(f"🔧 Tool '{tool_name}' called with args={args} → {result_str}")
    else:
        logger.debug(f"🔧 Tool '{tool_name}' called with args={args}")


def log_agent_decision(logger: logging.Logger, agent_name: str, decision: str, context: dict = None):
    """Log an agent's decision-making step."""
    if context:
        logger.info(f"🤖 [{agent_name}] Decision: {decision} | Context: {context}")
    else:
        logger.info(f"🤖 [{agent_name}] Decision: {decision}")


def log_llm_call(logger: logging.Logger, model: str, prompt_preview: str, response_preview: str = None):
    """Log an LLM API call with prompt and response previews."""
    prompt_short = prompt_preview[:100] + "..." if len(prompt_preview) > 100 else prompt_preview
    logger.debug(f"🧠 LLM Call ({model}): {prompt_short}")
    
    if response_preview:
        response_short = response_preview[:150] + "..." if len(response_preview) > 150 else response_preview
        logger.debug(f"🧠 LLM Response: {response_short}")
