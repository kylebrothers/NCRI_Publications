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
# API-specific request handlers
# Replace the existing handler functions in app.py with these updated versions

def handle_claude_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Handle Claude API requests"""
    if not claude_client.is_connected():
        return jsonify({'error': 'Claude API not available'}), 503
    
    operation = form_data.get('operation', 'generate')
    
    # Test connection operation
    if operation == 'test':
        return jsonify({
            'success': True,
            'model': claude_client.model,
            'max_tokens': claude_client.max_tokens,
            'session_id': session_id
        })
    
    elif operation == 'generate':
        prompt = form_data.get('prompt', '')
        if not prompt:
            return jsonify({'error': 'Prompt required'}), 400
        
        # Build context from files
        context = build_context(uploaded_files_data, server_files_data)
        
        # Get optional parameters
        temperature = float(form_data.get('temperature', 0.7))
        system_prompt = form_data.get('system_prompt')
        
        try:
            # Call Claude
            response = claude_client.generate(
                prompt, 
                context,
                system_prompt=system_prompt,
                temperature=temperature
            )
            
            return jsonify({
                'success': True,
                'content': response,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Claude generation error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'analyze':
        text = form_data.get('text', '')
        analysis_type = form_data.get('analysis_type', 'summary')
        
        if not text:
            return jsonify({'error': 'Text required for analysis'}), 400
        
        try:
            result = claude_client.analyze(text, analysis_type)
            return jsonify({
                'success': True,
                'analysis': result,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Claude analysis error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'compare':
        text1 = form_data.get('text1', '')
        text2 = form_data.get('text2', '')
        comparison_type = form_data.get('comparison_type', 'both')
        
        if not text1 or not text2:
            return jsonify({'error': 'Both text1 and text2 required'}), 400
        
        try:
            result = claude_client.compare_texts(text1, text2, comparison_type)
            return jsonify({
                'success': True,
                'comparison': result,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Claude comparison error: {e}")
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': f'Unknown operation: {operation}'}), 400


def handle_pubmed_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Handle PubMed API requests"""
    if not pubmed_client.is_connected():
        return jsonify({'error': 'PubMed API not available'}), 503
    
    operation = form_data.get('operation', 'search')
    
    # Test connection operation
    if operation == 'test':
        return jsonify({
            'success': True,
            'has_api_key': bool(pubmed_client.api_key),
            'rate_limit': f'{pubmed_client.rate_limit}/sec',
            'session_id': session_id
        })
    
    elif operation == 'search':
        query = form_data.get('query', '')
        if not query:
            return jsonify({'error': 'Query required'}), 400
        
        filters = json.loads(form_data.get('filters', '{}'))
        max_results = int(form_data.get('max_results', 100))
        
        try:
            results = pubmed_client.search(query, filters, max_results)
            
            return jsonify({
                'success': True,
                'results': results,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"PubMed search error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'fetch':
        pmids = json.loads(form_data.get('pmids', '[]'))
        if not pmids:
            return jsonify({'error': 'PMIDs required'}), 400
        
        include_abstract = form_data.get('include_abstract', 'true').lower() == 'true'
        include_full_text = form_data.get('include_full_text', 'false').lower() == 'true'
        
        try:
            articles = pubmed_client.fetch_articles(pmids, include_abstract, include_full_text)
            
            return jsonify({
                'success': True,
                'articles': articles,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"PubMed fetch error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'advanced_search':
        criteria = {}
        
        # Extract all possible search criteria
        for field in ['keywords', 'title_words', 'abstract_words', 'authors', 
                     'journals', 'mesh_terms', 'publication_types']:
            if field in form_data:
                criteria[field] = json.loads(form_data.get(field, '[]'))
        
        for field in ['date_from', 'date_to']:
            if field in form_data:
                criteria[field] = form_data.get(field)
        
        max_results = int(form_data.get('max_results', 100))
        
        try:
            results = pubmed_client.advanced_search(**criteria, max_results=max_results)
            
            return jsonify({
                'success': True,
                'results': results,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"PubMed advanced search error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'get_citations':
        pmid = form_data.get('pmid')
        if not pmid:
            return jsonify({'error': 'PMID required'}), 400
        
        try:
            citations = pubmed_client.get_citations(pmid)
            return jsonify({
                'success': True,
                'citations': citations,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"PubMed citations error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'get_related':
        pmid = form_data.get('pmid')
        if not pmid:
            return jsonify({'error': 'PMID required'}), 400
        
        max_related = int(form_data.get('max_related', 10))
        
        try:
            related = pubmed_client.get_related_articles(pmid, max_related)
            return jsonify({
                'success': True,
                'related_pmids': related,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"PubMed related articles error: {e}")
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': f'Unknown operation: {operation}'}), 400


def handle_asana_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Handle Asana API requests"""
    if not asana_client.is_connected():
        return jsonify({'error': 'Asana API not available'}), 503
    
    operation = form_data.get('operation', 'list_projects')
    
    # Test connection operation
    if operation == 'test':
        try:
            workspace_info = asana_client.get_workspace_info()
            user_info = asana_client.get_me()
            return jsonify({
                'success': True,
                'workspace': workspace_info,
                'user': user_info,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Asana test error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'get_workspace':
        try:
            workspace_info = asana_client.get_workspace_info()
            return jsonify({
                'success': True,
                'workspace': workspace_info,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Asana workspace error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'get_project':
        project_gid = form_data.get('project_gid')
        if not project_gid:
            return jsonify({'error': 'project_gid required'}), 400
        
        try:
            project = asana_client.get_project(project_gid)
            
            # Try to get metrics too
            try:
                metrics = asana_client.get_task_metrics_for_project(project_gid)
            except:
                metrics = None
            
            return jsonify({
                'success': True,
                'project': project,
                'metrics': metrics,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Asana get project error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'get_tasks':
        project_gid = form_data.get('project_gid')
        if not project_gid:
            return jsonify({'error': 'project_gid required'}), 400
        
        completed_since = form_data.get('completed_since')
        limit = int(form_data.get('limit', 100))
        
        try:
            tasks = asana_client.get_project_tasks(project_gid, completed_since, limit)
            return jsonify({
                'success': True,
                'tasks': tasks,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Asana get tasks error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'get_task':
        task_gid = form_data.get('task_gid')
        if not task_gid:
            return jsonify({'error': 'task_gid required'}), 400
        
        try:
            task = asana_client.get_task(task_gid)
            return jsonify({
                'success': True,
                'task': task,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Asana get task error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'search_tasks':
        project_gid = form_data.get('project_gid')
        query = form_data.get('query', '')
        
        if not project_gid or not query:
            return jsonify({'error': 'project_gid and query required'}), 400
        
        try:
            tasks = asana_client.search_tasks_in_project(project_gid, query)
            return jsonify({
                'success': True,
                'tasks': tasks,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Asana search tasks error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'get_metrics':
        project_gid = form_data.get('project_gid')
        if not project_gid:
            return jsonify({'error': 'project_gid required'}), 400
        
        start_date = form_data.get('start_date')
        end_date = form_data.get('end_date')
        
        try:
            metrics = asana_client.get_task_metrics_for_project(
                project_gid, 
                start_date, 
                end_date
            )
            return jsonify({
                'success': True,
                'metrics': metrics,
                'session_id': session_id
            })
        except Exception as e:
            logger.error(f"Asana get metrics error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif operation == 'find_project':
        project_name = form_data.get('project_name')
        if not project_name:
            return jsonify({'error': 'project_name required'}), 400
        
        try:
            project = asana_client.find_project_by_name(project_name)
            if project:
                return jsonify({
                    'success': True,
                    'project': project,
                    'session_id': session_id
                })
            else:
                return jsonify({'error': 'Project not found'}), 404
        except Exception as e:
            logger.error(f"Asana find project error: {e}")
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': f'Unknown operation: {operation}'}), 400


def handle_combined_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Handle requests that use multiple APIs"""
    operations = json.loads(form_data.get('operations', '[]'))
    results = {}
    
    for op in operations:
        api = op.get('api')
        op_data = op.get('data', {})
        
        try:
            if api == 'claude' and claude_client.is_connected():
                # Process with Claude
                if op.get('operation') == 'generate':
                    response = claude_client.generate(
                        op_data.get('prompt', ''),
                        op_data.get('context')
                    )
                    results[f"{api}_{op.get('operation')}"] = response
                    
            elif api == 'pubmed' and pubmed_client.is_connected():
                # Process with PubMed
                if op.get('operation') == 'search':
                    response = pubmed_client.search(
                        op_data.get('query', ''),
                        op_data.get('filters', {}),
                        op_data.get('max_results', 100)
                    )
                    results[f"{api}_{op.get('operation')}"] = response
                    
            elif api == 'asana' and asana_client.is_connected():
                # Process with Asana
                if op.get('operation') == 'get_project':
                    response = asana_client.get_project(op_data.get('project_gid'))
                    results[f"{api}_{op.get('operation')}"] = response
                    
        except Exception as e:
            logger.error(f"Combined operation error for {api}: {e}")
            results[f"{api}_{op.get('operation')}_error"] = str(e)
    
    return jsonify({
        'success': True,
        'results': results,
        'session_id': session_id
    })


def handle_generic_request(page_name, form_data, uploaded_files_data, server_files_data, session_id):
    """Default handler for pages without specific API requirements"""
    # Check if this is actually an API-specific request that wasn't routed properly
    operation = form_data.get('operation')
    
    # If it has an operation but no api_type, try to route based on the operation
    if operation:
        # Common operations that can help identify the API
        if operation in ['generate', 'analyze', 'compare']:
            form_data['api_type'] = 'claude'
            return handle_claude_request(page_name, form_data, uploaded_files_data, 
                                        server_files_data, session_id)
        elif operation in ['search', 'fetch', 'advanced_search', 'get_citations']:
            form_data['api_type'] = 'pubmed'
            return handle_pubmed_request(page_name, form_data, uploaded_files_data, 
                                        server_files_data, session_id)
        elif operation in ['get_project', 'get_tasks', 'get_task', 'get_workspace']:
            form_data['api_type'] = 'asana'
            return handle_asana_request(page_name, form_data, uploaded_files_data, 
                                       server_files_data, session_id)
    
    # Default response for truly generic requests
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
