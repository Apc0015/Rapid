"""
File validation utilities for secure file upload handling.
"""
import os
import mimetypes
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Mapping of allowed extensions to their expected MIME types
ALLOWED_TYPES = {
    # Documents
    '.pdf': ['application/pdf'],
    '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
    '.txt': ['text/plain'],
    '.md': ['text/markdown', 'text/plain'],
    '.markdown': ['text/markdown', 'text/plain'],
    '.html': ['text/html'],
    '.htm': ['text/html'],
    # Tabular
    '.csv': ['text/csv', 'application/csv', 'text/plain'],
    '.xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
    '.xls': ['application/vnd.ms-excel'],
    '.parquet': ['application/octet-stream'],
    # Structured data
    '.json': ['application/json', 'text/json', 'text/plain'],
    '.xml': ['application/xml', 'text/xml', 'text/plain'],
    # Config / data formats
    '.yaml': ['application/x-yaml', 'text/yaml', 'text/plain'],
    '.yml': ['application/x-yaml', 'text/yaml', 'text/plain'],
    '.toml': ['application/toml', 'text/plain'],
    '.ini': ['text/plain'],
    '.cfg': ['text/plain'],
    '.conf': ['text/plain'],
    # Code files
    '.py': ['text/x-python', 'text/plain'],
    '.js': ['application/javascript', 'text/javascript', 'text/plain'],
    '.ts': ['application/typescript', 'text/plain'],
    '.java': ['text/x-java-source', 'text/plain'],
    '.cpp': ['text/x-c', 'text/plain'],
    '.c': ['text/x-c', 'text/plain'],
    '.go': ['text/plain'],
    '.rs': ['text/plain'],
    '.rb': ['text/plain'],
    '.php': ['text/php', 'text/plain'],
    '.sh': ['application/x-sh', 'text/plain'],
    # Database / Query
    '.sql': ['text/plain'],
    # Notebooks
    '.ipynb': ['application/json', 'text/plain'],
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def validate_file_extension(filename: str) -> Tuple[bool, Optional[str]]:
    """
    Validate file extension.
    
    Returns:
        (is_valid, extension) tuple
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_TYPES:
        return False, None
    return True, ext


def validate_file_size(content: bytes) -> Tuple[bool, int]:
    """
    Validate file size.
    
    Returns:
        (is_valid, size) tuple
    """
    size = len(content)
    return size <= MAX_FILE_SIZE, size


def validate_mime_type(content: bytes, expected_ext: str) -> bool:
    """
    Validate MIME type matches expected extension.
    Uses magic number detection when possible.
    
    Args:
        content: File content bytes
        expected_ext: Expected extension (e.g., '.pdf')
        
    Returns:
        True if MIME type matches expected types for extension
    """
    # Try to detect MIME type from magic numbers
    try:
        import magic
        detected_mime = magic.from_buffer(content, mime=True)
        expected_mimes = ALLOWED_TYPES.get(expected_ext, [])
        
        if detected_mime in expected_mimes:
            return True
        
        # All text-based formats accept text/* MIME types
        _TEXT_BASED_EXTS = {
            '.txt', '.csv', '.md', '.markdown', '.html', '.htm', '.xml',
            '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.rb',
            '.php', '.sh', '.sql',
        }
        if expected_ext in _TEXT_BASED_EXTS:
            if detected_mime.startswith('text/') or detected_mime in (
                'application/json', 'application/javascript',
                'application/x-yaml', 'application/x-sh',
            ):
                return True
        
        logger.warning(
            f"MIME type mismatch: expected {expected_mimes}, got {detected_mime} for {expected_ext}"
        )
        return False
    except ImportError:
        # python-magic not installed, fall back to extension-based validation
        logger.debug("python-magic not installed, skipping MIME type validation")
        return True
    except Exception as e:
        logger.warning(f"MIME type detection failed: {e}")
        return True  # Don't block on validation errors


def validate_upload(filename: str, content: bytes) -> Tuple[bool, str]:
    """
    Comprehensive file upload validation.
    
    Args:
        filename: Original filename
        content: File content bytes
        
    Returns:
        (is_valid, error_message) tuple. error_message is empty if valid.
    """
    # Validate extension
    is_valid_ext, ext = validate_file_extension(filename)
    if not is_valid_ext:
        supported = ', '.join(ALLOWED_TYPES.keys())
        return False, f"Unsupported file type. Supported: {supported}"
    
    # Validate size
    is_valid_size, size = validate_file_size(content)
    if not is_valid_size:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        actual_mb = size / (1024 * 1024)
        return False, f"File too large: {actual_mb:.1f}MB. Maximum: {max_mb}MB"
    
    # Validate MIME type
    is_valid_mime = validate_mime_type(content, ext)
    if not is_valid_mime:
        return False, f"File content does not match extension {ext}. Possible file masquerading."
    
    return True, ""


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other attacks.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Get basename to prevent path traversal
    filename = os.path.basename(filename)
    
    # Remove or replace dangerous characters
    dangerous_chars = ['..', '/', '\\', '\0', '\n', '\r']
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    name, ext = os.path.splitext(filename)
    if len(name) > 200:
        name = name[:200]
    
    return name + ext
