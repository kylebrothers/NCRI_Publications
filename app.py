"""
Main Flask application - Multi-API Research Platform
Integrates Claude AI, PubMed, and Asana APIs
"""

from flask import render_template, request, jsonify, session, send_file, abort
from datetime import datetime
import os
import re
import json
import logging

# Import modular components
from config import create_app, setup_logging, setup_rate_limiter, ensure_directories
from utils import get_session_id, get_server_files_info, sanitize_form_key
from file_processors import process_uploaded_file, validate_file, load_server_files
from binary_file_handler import serve_binary_file, list_binary_files

# Import API clients
from claude_client import ClaudeClient
from pubmed_client import PubMedClient
from asana_client import AsanaClient

# Import page handlers (will be added as needed)
# from page_handlers import handle_claude_page, handle_pubmed_page, handle_asana_page

# Initialize application components
app = create_app()
logger = setup_logging()
limiter = setup_rate_limiter(app)

# Initialize API clients
claude_client = ClaudeClient()
pubmed_client = PubMedClient()
asana_client = AsanaClient()

# Ensure required directories exist
ensure_directories()

# Log initialization status
logger.info("Multi-API Research Platform initializing...")
logger.info(f"Claude API: {'Connected' if claude_client.is_connected() else 'Not configured'}")
logger.info(f"PubMed API: {'Connected' if pubmed_client.is_connected() else 'Not configured'}")
logger.info(f"Asana API: {'Connected' if asana_client.is_connected() else 'Not configured'}")

# Routes
@app.route('/')
def home():
    """Home page with API status dashboard"""
    session_id = get_session_id()
    logger.info(f"Home page accessed - Session: {session_id}")
    
    # Get API statuses
    api_status = {
        'claude': {
            'connected': claude_client.is_connected(),
            'name': 'Claude AI',
            'description': 'AI-powered text generation and analysis'
        },
        'pubmed': {
            'connected': pubmed_client.is_connected(),
            'name': 'PubMed',
            'description': 'Biomedical literature database'
        },
        'asana': {
            'connected': asana_client.is_connected(),
            'name': 'Asana',
            'description': 'Project and task management',
            'workspace': asana_client.get_workspace_info() if asana_client.is_connected() else None
        }
    }
    
    return render_template('home.html', api_status=api_status)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'apis': {
            'claude': claude_client.is_connected(),
            'pubmed': pubmed_client.is_connected(),
            'asana': asana_client.is_connected()
        }
    })

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/<page_name>')
def generic_page(page_name):
    """Serve any page that has a corresponding template"""
    session_id = get_session_id()
    logger.info(f"Page accessed: {page_name} - Session: {session_id}")
    
    # Convert URL format to template format
    template_name = page_name + '.html'
    
    # Get page configuration
    page_config = get_page_configuration(page_name)
    
    # Load server files if specified
    server_files_info = []
    if page_config.get('load_server_files'):
        directories = page_config.get('directories', [page_name])
        try:
            server_files_info = get_server_files_info(page_name, directories)
            logger.info(f"Server files loaded for {page_name}: {len(server_files_info)} files")
        except Exception as e:
            logger.error(f"Error loading server files for {page_name}: {e}")
    
    # Prepare context data
    context_data = {
        'page_name': page_name,
        'server_files_info': server_files_info,
        'page_config': page_config,
        'api_clients': {
            'claude_available': claude_client.is_connected(),
            'pubmed_available': pubmed_client.is_connected(),
            'asana_available': asana_client.is_connected()
        }
    }
    
    try:
        return render_template(template_name, **context_data)
    except Exception as e:
        logger.error(f"Template error for {template_name}: {e}")
        return render_template('404.html'), 404

@app.route('/api/<page_name>', methods=['POST'])
@limiter.limit("10 per minute")
def generic_api(page_name):
    """Generic API endpoint that routes to appropriate handlers"""
    try:
        # Handle file uploads
        uploaded_files_data = {}
        for field_name in request.files:
            file = request.files[field_name]
            if file and file.filename:
                is_valid, message = validate_file(file)
                if not is_valid:
                    return jsonify({'error': f'{field_name}: {message}'}), 400
                
                try:
                    file_data = process_uploaded_file(file)
                    if file_data:
                        clean_field_name = field_name.replace('_file', '').replace('_', ' ')
                        uploaded_files_data[clean_field_name] = file_data
                        logger.info(f"File processed: {file.filename} for {field_name}")
                except Exception as e:
                    return jsonify({'error': f'Error processing {field_name}: {str(e)}'}), 400
        
        # Get page configuration
        page_config = get_page_configuration(page_name)
        
        # Load server files if needed
        server_files_data = {}
        if page_config.get('load_server_files'):
            directories = page_config.get('directories', [page_name])
            server_files_data = load_server_files(page_name, directories)
        
        # Handle form data
        form_data = request.form.to_dict()
        session_id = get_session_id()
        
        logger.info(f"API called for: {page_name} - Session: {session_id}")
        
        # Route based on API type specified in form
        api_type = form_data.get('api_type', 'none')
        
        if api_type == 'claude':
            return handle_claude_request(
                page_name, form_data, uploaded_files_data, 
                server_files_data, session_id
            )
        elif api_type == 'pubmed':
            return handle_pubmed_request(
                page_name, form_data, uploaded_files_data, 
                server_files_data, session_id
            )
        elif api_type == 'asana':
            return handle_asana_request(
                page_name, form_data, uploaded_files_data, 
                server_files_data, session_id
            )
        elif api_type == 'combined':
            return handle_combined_request(
                page_name, form_data, uploaded_files_data, 
                server_files_data, session_id
            )
        else:
            # Default handler for pages that don't specify API type
            return handle_generic_request(
                page_name, form_data, uploaded_files_data, 
                server_files_data, session_id
            )
    
    except Exception as e:
        logger.error(f"Error in API for {page_name}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/<page_name>/file/<filename>', methods=['GET'])
def serve_page_file(page_name, filename):
    """Serve binary files from server_files directory"""
    logger.info(f"Binary file request: {page_name}/{filename}")
    return serve_binary_file(page_name, filename)

@app.route('/api/<page_name>/files', methods=['GET'])
def list_page_files(page_name):
    """List available binary files for a page"""
    extensions = request.args.getlist('ext')
    files = list_binary_files(page_name, extensions if extensions else None)
    return jsonify({'files': files})

# API-specific request handlers
def handle_claude_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Handle Claude API requests"""
    if not claude_client.is_connected():
        return jsonify({'error': 'Claude API not available'}), 503
    
    operation = form_data.get('operation', 'generate')
    
    if operation == 'generate':
        prompt = form_data.get('prompt', '')
        if not prompt:
            return jsonify({'error': 'Prompt required'}), 400
        
        # Build context from files
        context = build_context(uploaded_files_data, server_files_data)
        
        # Call Claude
        response = claude_client.generate(prompt, context)
        
        return jsonify({
            'success': True,
            'content': response,
            'session_id': session_id
        })
    
    return jsonify({'error': f'Unknown operation: {operation}'}), 400

def handle_pubmed_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Handle PubMed API requests"""
    if not pubmed_client.is_connected():
        return jsonify({'error': 'PubMed API not available'}), 503
    
    operation = form_data.get('operation', 'search')
    
    if operation == 'search':
        query = form_data.get('query', '')
        filters = json.loads(form_data.get('filters', '{}'))
        
        results = pubmed_client.search(query, filters)
        
        return jsonify({
            'success': True,
            'results': results,
            'session_id': session_id
        })
    
    elif operation == 'fetch':
        pmids = json.loads(form_data.get('pmids', '[]'))
        
        articles = pubmed_client.fetch_articles(pmids)
        
        return jsonify({
            'success': True,
            'articles': articles,
            'session_id': session_id
        })
    
    return jsonify({'error': f'Unknown operation: {operation}'}), 400

def handle_asana_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Handle Asana API requests"""
    if not asana_client.is_connected():
        return jsonify({'error': 'Asana API not available'}), 503
    
    operation = form_data.get('operation', 'list_projects')
    
    if operation == 'list_projects':
        projects = asana_client.get_projects()
        return jsonify({
            'success': True,
            'projects': projects,
            'session_id': session_id
        })
    
    elif operation == 'get_tasks':
        project_gid = form_data.get('project_gid')
        tasks = asana_client.get_project_tasks(project_gid)
        return jsonify({
            'success': True,
            'tasks': tasks,
            'session_id': session_id
        })
    
    return jsonify({'error': f'Unknown operation: {operation}'}), 400

def handle_combined_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Handle requests that use multiple APIs"""
    operations = json.loads(form_data.get('operations', '[]'))
    results = {}
    
    for op in operations:
        api = op.get('api')
        if api == 'claude' and claude_client.is_connected():
            # Process with Claude
            pass
        elif api == 'pubmed' and pubmed_client.is_connected():
            # Process with PubMed
            pass
        elif api == 'asana' and asana_client.is_connected():
            # Process with Asana
            pass
    
    return jsonify({
        'success': True,
        'results': results,
        'session_id': session_id
    })

def handle_generic_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Default handler for pages without specific API requirements"""
    return jsonify({
        'success': True,
        'message': 'Request processed',
        'form_data': form_data,
        'files_processed': list(uploaded_files_data.keys()),
        'server_files_loaded': list(server_files_data.keys()),
        'session_id': session_id
    })

# Helper functions
def get_page_configuration(page_name):
    """Get configuration for a specific page"""
    configurations = {
        'pubmed-search': {
            'api_type': 'pubmed',
            'load_server_files': True,
            'directories': ['pubmed-search', 'shared-articles']
        },
        'literature-review': {
            'api_type': 'combined',
            'load_server_files': True,
            'directories': ['literature-review', 'shared-articles']
        },
        'asana-dashboard': {
            'api_type': 'asana',
            'load_server_files': False
        },
        'research-assistant': {
            'api_type': 'claude',
            'load_server_files': True,
            'directories': ['research-assistant']
        }
    }
    
    return configurations.get(page_name, {
        'api_type': 'none',
        'load_server_files': False,
        'directories': [page_name]
    })

def build_context(uploaded_files_data, server_files_data):
    """Build context string from files for Claude"""
    context_parts = []
    
    # Add server files
    for name, data in server_files_data.items():
        if isinstance(data, dict) and 'text_content' in data:
            context_parts.append(f"=== {name} ===\n{data['text_content']}\n")
    
    # Add uploaded files
    for name, data in uploaded_files_data.items():
        if isinstance(data, dict) and 'text_content' in data:
            context_parts.append(f"=== Uploaded: {name} ===\n{data['text_content']}\n")
    
    return '\n'.join(context_parts)

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
        return '''
        <html><body>
        <h1>500 Internal Server Error</h1>
        <p>The server encountered an internal error.</p>
        <a href="/">Go Home</a>
        </body></html>
        ''', 500

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    )
