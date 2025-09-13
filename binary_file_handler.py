"""
Binary file handler for serving files from server_files directory
"""

import os
import logging
from flask import send_file, abort
from werkzeug.utils import safe_join

logger = logging.getLogger(__name__)

def serve_binary_file(page_name, filename):
    """
    Serve a binary file from the server_files directory
    
    Args:
        page_name: The page directory name
        filename: The requested filename
        
    Returns:
        Flask response with file content or 404 error
    """
    try:
        # URL decode the filename (handle spaces and special characters)
        from urllib.parse import unquote
        filename = unquote(filename)
        
        # Construct safe path to file
        base_path = "/app/server_files"
        file_path = safe_join(base_path, page_name, filename)
        
        # Security check - ensure path is within server_files
        if not file_path or not file_path.startswith(base_path):
            logger.warning(f"Invalid file path attempted: {page_name}/{filename}")
            abort(403)
        
        # Check if file exists
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            abort(404)
        
        # Check if it's a file (not directory)
        if not os.path.isfile(file_path):
            logger.warning(f"Path is not a file: {file_path}")
            abort(404)
        
        # Determine MIME type based on extension
        mime_types = {
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.pdf': 'application/pdf',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.txt': 'text/plain',
            '.csv': 'text/csv'
        }
        
        file_ext = os.path.splitext(filename)[1].lower()
        mime_type = mime_types.get(file_ext, 'application/octet-stream')
        
        logger.info(f"Serving binary file: {file_path} as {mime_type}")
        
        # Send file with appropriate headers
        return send_file(
            file_path,
            mimetype=mime_type,
            as_attachment=False,  # Display in browser if possible
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Error serving binary file {page_name}/{filename}: {e}")
        abort(500)

def list_binary_files(page_name, extensions=None):
    """
    List available binary files for a page
    
    Args:
        page_name: The page directory name
        extensions: List of file extensions to filter (e.g., ['.docx', '.pdf'])
        
    Returns:
        List of dictionaries with file information
    """
    files_list = []
    server_dir = f"/app/server_files/{page_name}"
    
    if not os.path.exists(server_dir):
        return files_list
    
    try:
        for filename in os.listdir(server_dir):
            file_path = os.path.join(server_dir, filename)
            
            if not os.path.isfile(file_path):
                continue
            
            # Filter by extension if specified
            if extensions:
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext not in extensions:
                    continue
            
            # Get file info
            file_stat = os.stat(file_path)
            
            files_list.append({
                'filename': filename,
                'size': file_stat.st_size,
                'url': f'/api/{page_name}/file/{filename}'
            })
        
        return files_list
        
    except Exception as e:
        logger.error(f"Error listing binary files for {page_name}: {e}")
        return []
