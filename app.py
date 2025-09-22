"""
Main Flask application - routes and error handlers only
"""

from flask import render_template, request, jsonify, session, send_file, abort
from datetime import datetime
import os
import re
import json

# Import our modular components
from config import create_app, setup_logging, setup_rate_limiter, setup_claude_client, ensure_directories
from file_processors import process_uploaded_file, validate_file, load_server_files
from page_handlers import handle_no_call_page, handle_claude_call_page
from utils import get_session_id, get_server_files_info
from binary_file_handler import serve_binary_file, list_binary_files

# Initialize application components
app = create_app()
logger = setup_logging()
limiter = setup_rate_limiter(app)
claude_client = setup_claude_client()

# Ensure required directories exist
ensure_directories()

# Log initialization status
if claude_client:
    logger.info("Application initialized successfully with Claude API")
else:
    logger.warning("Application initialized without Claude API")

# Routes
@app.route('/')
def home():
    session_id = get_session_id()
    logger.info(f"Home page accessed - Session: {session_id}")
    return render_template('home.html')

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'claude_available': claude_client is not None
    })

@app.route('/favicon.ico')
def favicon():
    return '', 204  # No content response

@app.route('/<page_name>')
def generic_page(page_name):
    """Serve any page that has a corresponding template"""
    session_id = get_session_id()
    logger.info(f"Page accessed: {page_name} - Session: {session_id}")
    
    # Convert URL format to template format (e.g., chairs-promotion-letter -> chairs_promotion_letter.html)
    template_name = page_name.replace('-', '_') + '.html'
    
    # Check if template specifies additional server directories
    directories_to_load = [page_name]  # Always include the page's own directory
    try:
        template_path = os.path.join(app.template_folder, template_name)
        if os.path.exists(template_path):
            with open(template_path, 'r') as f:
                content = f.read()
                # Look for server_dirs_config in the template
                config_match = re.search(r'<script[^>]*id="server_dirs_config"[^>]*>(.*?)</script>', content, re.DOTALL)
                if config_match:
                    try:
                        config_json = config_match.group(1).strip()
                        config = json.loads(config_json)
                        if isinstance(config, dict) and 'directories' in config:
                            # Add specified directories (but keep page directory first)
                            for dir_name in config['directories']:
                                if dir_name not in directories_to_load:
                                    directories_to_load.append(dir_name)
                            logger.info(f"Page {page_name} loading from directories: {directories_to_load}")
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in server_dirs_config for {page_name}")
    except Exception as e:
        logger.warning(f"Error checking template for server_dirs_config: {e}")
    
    # Load server files for this page to show on the page
    try:
        server_files_info = get_server_files_info(page_name, directories_to_load)
        logger.info(f"Server files info loaded for {page_name}: {len(server_files_info)} files")
    except Exception as e:
        logger.error(f"Error loading server files info for {page_name}: {e}")
        server_files_info = []
    
    try:
        return render_template(template_name, page_name=page_name, server_files_info=server_files_info)
    except Exception as e:
        logger.error(f"Template error for {template_name}: {e}")
        return render_template('404.html'), 404

@app.route('/api/<page_name>', methods=['POST'])
@limiter.limit("5 per minute")
def generic_api(page_name):
    """Generic API endpoint that handles any page"""
    try:
        # Handle file uploads - process all uploaded files
        uploaded_files_data = {}
        
        for field_name in request.files:
            file = request.files[field_name]
            if file and file.filename:
                is_valid, message = validate_file(file)
                if not is_valid:
                    return jsonify({'error': f'{field_name} error: {message}'}), 400
                
                try:
                    file_data = process_uploaded_file(file)
                    if file_data:
                        # Clean up field name for context
                        clean_field_name = field_name.replace('_file', '').replace('_', ' ')
                        uploaded_files_data[clean_field_name] = file_data
                        logger.info(f"File processed: {file.filename} for field {field_name}")
                except Exception as e:
                    return jsonify({'error': f'Error processing {field_name}: {str(e)}'}), 400
        
        # Check if this page specifies additional server directories
        directories_to_load = [page_name]  # Always include the page's own directory
        template_name = page_name.replace('-', '_') + '.html'
        try:
            template_path = os.path.join(app.template_folder, template_name)
            if os.path.exists(template_path):
                with open(template_path, 'r') as f:
                    content = f.read()
                    config_match = re.search(r'<script[^>]*id="server_dirs_config"[^>]*>(.*?)</script>', content, re.DOTALL)
                    if config_match:
                        try:
                            config_json = config_match.group(1).strip()
                            config = json.loads(config_json)
                            if isinstance(config, dict) and 'directories' in config:
                                for dir_name in config['directories']:
                                    if dir_name not in directories_to_load:
                                        directories_to_load.append(dir_name)
                                logger.info(f"API for {page_name} loading from directories: {directories_to_load}")
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in server_dirs_config for {page_name}")
        except Exception as e:
            logger.warning(f"Error checking template for server_dirs_config: {e}")
        
        # Load server files for this page
        server_files_data = load_server_files(page_name, directories_to_load)
        
        # Handle form data
        form_data = request.form.to_dict()
        session_id = get_session_id()
        
        logger.info(f"API called for page: {page_name} - Session: {session_id}")
        
        # Check page type based on form data
        page_type = form_data.get('page_type', 'claude-call')
        
        if page_type == 'no-call':
            # Handle no-call pages (no Claude API, just return organized data)
            return handle_no_call_page(page_name, form_data, uploaded_files_data, server_files_data, session_id)
        elif page_type == 'claude-call':
            # Handle Claude API pages (existing functionality)
            return handle_claude_call_page(page_name, form_data, uploaded_files_data, server_files_data, session_id, claude_client)
        else:
            return jsonify({'error': f'Unknown page type: {page_type}'}), 400
    
    except Exception as e:
        logger.error(f"Error in API for page {page_name}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/<page_name>/save-data', methods=['POST'])
@limiter.limit("10 per minute")
def save_page_data(page_name):
    """Generic endpoint to save JSON data for a page"""
    try:
        data = request.json
        if not data or 'filename' not in data or 'content' not in data:
            return jsonify({'error': 'Missing filename or content'}), 400
        
        filename = data['filename']
        # Ensure filename ends with .json
        if not filename.endswith('.json'):
            filename += '.json'
        
        # Security: sanitize filename to prevent directory traversal
        filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '', filename)
        
        # Optionally allow saving to a different directory if specified
        target_dir = data.get('directory', page_name)
        # Sanitize directory name
        target_dir = re.sub(r'[^a-zA-Z0-9_\-]', '', target_dir)
        
        # Save to server_files directory
        save_path = f"/app/server_files/{target_dir}/{filename}"
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # Save content as JSON
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data['content'], f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved data to {save_path}")
        return jsonify({
            'success': True, 
            'message': 'Data saved successfully',
            'filename': filename,
            'directory': target_dir
        })
        
    except Exception as e:
        logger.error(f"Error saving data for {page_name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<page_name>/load-data/<filename>', methods=['GET'])
def load_page_data(page_name, filename):
    """Generic endpoint to load JSON data for a page"""
    try:
        # Ensure filename ends with .json
        if not filename.endswith('.json'):
            filename += '.json'
        
        # Sanitize filename
        filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '', filename)
        
        # Check if a different directory is requested
        source_dir = request.args.get('directory', page_name)
        # Sanitize directory name
        source_dir = re.sub(r'[^a-zA-Z0-9_\-]', '', source_dir)
        
        load_path = f"/app/server_files/{source_dir}/{filename}"
        
        if not os.path.exists(load_path):
            # Try without .json if it was double-added
            alt_path = load_path.replace('.json.json', '.json')
            if os.path.exists(alt_path):
                load_path = alt_path
            else:
                logger.warning(f"File not found: {load_path}")
                return jsonify({'error': 'File not found', 'path': f"{source_dir}/{filename}"}), 404
        
        with open(load_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        logger.info(f"Loaded data from {load_path}")
        return jsonify({
            'success': True, 
            'content': content,
            'filename': filename,
            'directory': source_dir
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error loading {page_name}/{filename}: {e}")
        return jsonify({'error': 'Invalid JSON file'}), 400
    except Exception as e:
        logger.error(f"Error loading data for {page_name}/{filename}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<page_name>/list-data', methods=['GET'])
def list_page_data(page_name):
    """List available JSON data files for a page"""
    try:
        # Check if a different directory is requested
        source_dir = request.args.get('directory', page_name)
        # Sanitize directory name
        source_dir = re.sub(r'[^a-zA-Z0-9_\-]', '', source_dir)
        
        data_dir = f"/app/server_files/{source_dir}"
        
        if not os.path.exists(data_dir):
            return jsonify({'success': True, 'files': []})
        
        # List all JSON files
        json_files = []
        for filename in os.listdir(data_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(data_dir, filename)
                if os.path.isfile(file_path):
                    file_stat = os.stat(file_path)
                    json_files.append({
                        'filename': filename,
                        'size': file_stat.st_size,
                        'modified': datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                    })
        
        # Sort by modified date, newest first
        json_files.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            'success': True,
            'files': json_files,
            'directory': source_dir
        })
        
    except Exception as e:
        logger.error(f"Error listing data files for {page_name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<page_name>/delete-data/<filename>', methods=['DELETE'])
@limiter.limit("10 per minute")
def delete_page_data(page_name, filename):
    """Delete a JSON data file for a page"""
    try:
        # Ensure filename ends with .json
        if not filename.endswith('.json'):
            filename += '.json'
        
        # Sanitize filename
        filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '', filename)
        
        # Check if a different directory is requested
        target_dir = request.args.get('directory', page_name)
        # Sanitize directory name
        target_dir = re.sub(r'[^a-zA-Z0-9_\-]', '', target_dir)
        
        delete_path = f"/app/server_files/{target_dir}/{filename}"
        
        if not os.path.exists(delete_path):
            return jsonify({'error': 'File not found'}), 404
        
        os.remove(delete_path)
        logger.info(f"Deleted file: {delete_path}")
        
        return jsonify({
            'success': True,
            'message': 'File deleted successfully',
            'filename': filename,
            'directory': target_dir
        })
        
    except Exception as e:
        logger.error(f"Error deleting file {page_name}/{filename}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/<page_name>/file/<filename>', methods=['GET'])
def serve_page_file(page_name, filename):
    """Serve binary files from server_files directory"""
    logger.info(f"Binary file request: {page_name}/{filename}")
    return serve_binary_file(page_name, filename)

@app.route('/api/<page_name>/files', methods=['GET'])
def list_page_files(page_name):
    """List available binary files for a page"""
    extensions = request.args.getlist('ext')  # e.g., ?ext=.docx&ext=.pdf
    files = list_binary_files(page_name, extensions if extensions else None)
    return jsonify({'files': files})

# Error handlers
@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 10MB.'}), 413

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429

@app.errorhandler(404)
def not_found(e):
    try:
        return render_template('404.html'), 404
    except:
        # Fallback if 404.html template fails
        return '''
        <html><body>
        <h1>404 Page Not Found</h1>
        <p>The page you're looking for doesn't exist.</p>
        <a href="/">Go Home</a>
        </body></html>
        ''', 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    try:
        return render_template('500.html'), 500
    except:
        # Fallback if 500.html template fails
        return '''
        <html><body>
        <h1>500 Internal Server Error</h1>
        <p>The server encountered an internal error.</p>
        <a href="/">Go Home</a>
        </body></html>
        ''', 500

if __name__ == '__main__':
    # Run the application
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    )
