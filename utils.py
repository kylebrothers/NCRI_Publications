"""
Utility functions and helpers
"""

import os
import uuid
import logging
from flask import session

logger = logging.getLogger(__name__)

def get_session_id():
    """Generate or retrieve session ID"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def get_server_files_info(page_name, directories=None):
    """Get information about available server files for display
    
    Args:
        page_name: The name of the current page
        directories: Optional list of directories to load from. If None, loads only from page_name directory
    
    Returns:
        list: File information with source directory noted if loading from multiple directories
    """
    server_files_info = []
    
    # Default to just the page's own directory if not specified
    if directories is None:
        directories = [page_name]
    
    for directory in directories:
        server_dir = f"/app/server_files/{directory}"
        
        logger.info(f"Getting server files info for directory: {directory} from path: {server_dir}")
        
        if not os.path.exists(server_dir):
            logger.info(f"Server files directory does not exist: {server_dir}")
            continue
        
        try:
            files_list = os.listdir(server_dir)
            logger.info(f"Found {len(files_list)} files in {server_dir}: {files_list}")
            
            for filename in files_list:
                try:
                    file_path = os.path.join(server_dir, filename)
                    logger.info(f"Processing file: {file_path}")
                    
                    if not os.path.isfile(file_path):
                        logger.info(f"Skipping {filename} - not a regular file")
                        continue
                    
                    # Get file info
                    file_stat = os.stat(file_path)
                    file_size = file_stat.st_size
                    
                    # Format file size
                    if file_size < 1024:
                        size_str = f"{file_size} B"
                    elif file_size < 1024 * 1024:
                        size_str = f"{file_size / 1024:.1f} KB"
                    else:
                        size_str = f"{file_size / (1024 * 1024):.1f} MB"
                    
                    # Get file type
                    file_ext = os.path.splitext(filename)[1].lower()
                    if file_ext == '.docx':
                        file_type = 'Word Document'
                    elif file_ext == '.pdf':
                        file_type = 'PDF Document'
                    elif file_ext == '.txt':
                        file_type = 'Text File'
                    else:
                        file_type = 'Unknown'
                    
                    # Create display name
                    base_display_name = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ').title()
                    
                    # Add directory prefix if loading from multiple directories and not the page's own directory
                    if len(directories) > 1 and directory != page_name:
                        display_name = f"{directory.title()} - {base_display_name}"
                    else:
                        display_name = base_display_name
                    
                    file_info = {
                        'filename': filename,
                        'display_name': display_name,
                        'file_type': file_type,
                        'size': size_str,
                        'supported': file_ext in ['.docx', '.pdf', '.txt'],
                        'source_directory': directory  # Track which directory this came from
                    }
                    
                    server_files_info.append(file_info)
                    logger.info(f"Added file info: {file_info}")
                    
                except Exception as file_error:
                    logger.error(f"Error processing file {filename}: {file_error}")
                    continue
            
        except Exception as e:
            logger.error(f"Error listing files in directory {server_dir}: {e}")
            continue
    
    # Sort by display name
    server_files_info.sort(key=lambda x: x['display_name'])
    logger.info(f"Successfully processed {len(server_files_info)} files from {len(directories)} directories")
    
    return server_files_info

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def clean_filename(filename):
    """Clean filename for display purposes"""
    return os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ').title()

def get_file_type_display(file_extension):
    """Get human-readable file type from extension"""
    file_types = {
        '.docx': 'Word Document',
        '.pdf': 'PDF Document',
        '.txt': 'Text File',
        '.doc': 'Word Document (Legacy)',
        '.xlsx': 'Excel Spreadsheet',
        '.csv': 'CSV File'
    }
    return file_types.get(file_extension.lower(), 'Unknown')

def is_supported_file(filename):
    """Check if file type is supported"""
    supported_extensions = ['.docx', '.pdf', '.txt']
    file_ext = os.path.splitext(filename)[1].lower()
    return file_ext in supported_extensions

def sanitize_form_key(key):
    """Sanitize form key for display"""
    return key.replace('_', ' ').title()

def truncate_text(text, max_length=500):
    """Truncate text with ellipsis if longer than max_length"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

def count_form_fields(form_data, exclude_keys=None):
    """Count non-empty form fields, excluding specified keys"""
    if exclude_keys is None:
        exclude_keys = ['page_type', 'page_title', 'claude_prompt']
    
    count = 0
    for key, value in form_data.items():
        if key not in exclude_keys and str(value).strip():
            count += 1
    return count
