# Makefile for Multi-API Research Platform
# Provides automated build, deployment, and management commands

# Variables
DOCKER_COMPOSE = docker-compose
DOCKER = docker
PYTHON = python3
PIP = pip3
APP_NAME = research-platform
CONTAINER_NAME = research-platform-app
REDIS_CONTAINER = research-platform-redis
IMAGE_NAME = research-platform:latest
NAS_IP ?= 192.168.0.134
HOST_PORT ?= 5000

# Color output
RED = \033[0;31m
GREEN = \033[0;32m
YELLOW = \033[1;33m
BLUE = \033[0;34m
NC = \033[0m # No Color

# Default target
.DEFAULT_GOAL := help

# Phony targets
.PHONY: help build up down restart logs shell test clean backup restore status

## Help
help: ## Show this help message
	@echo "$(GREEN)Multi-API Research Platform - Management Commands$(NC)"
	@echo ""
	@echo "$(YELLOW)Quick Start:$(NC)"
	@echo "  make setup       - Initial setup (create .env and NAS directories)"
	@echo "  make build       - Build Docker images"
	@echo "  make up          - Start all services"
	@echo ""
	@echo "$(YELLOW)Available Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Environment Variables:$(NC)"
	@echo "  NAS_IP=$(NAS_IP)"
	@echo "  HOST_PORT=$(HOST_PORT)"

## Setup Commands
setup: ## Initial setup - create .env and NAS directories
	@echo "$(GREEN)Setting up Multi-API Research Platform...$(NC)"
	@echo ""
	@echo "$(YELLOW)1. Creating .env file...$(NC)"
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(GREEN)✓ Created .env from template$(NC)"; \
		echo "$(RED)⚠ Please edit .env and add your API keys!$(NC)"; \
	else \
		echo "$(BLUE)✓ .env file already exists$(NC)"; \
	fi
	@echo ""
	@echo "$(YELLOW)2. Creating NAS directory structure...$(NC)"
	@echo "Please ensure these directories exist on your NAS ($(NAS_IP)):"
	@echo "  /Docker/research-platform/logs"
	@echo "  /Docker/research-platform/server_files"
	@echo "  /Docker/research-platform/templates"
	@echo "  /Docker/research-platform/static"
	@echo "  /Docker/research-platform/uploads"
	@echo "  /Docker/research-platform/redis"
	@echo ""
	@echo "$(YELLOW)3. Creating local directories...$(NC)"
	@mkdir -p logs templates static server_files uploads
	@mkdir -p server_files/pubmed-search
	@mkdir -p server_files/literature-review
	@mkdir -p server_files/research-assistant
	@mkdir -p server_files/shared-articles
	@echo "$(GREEN)✓ Local directories created$(NC)"
	@echo ""
	@echo "$(GREEN)Setup complete! Next steps:$(NC)"
	@echo "  1. Edit .env file with your API keys"
	@echo "  2. Run 'make build' to build Docker images"
	@echo "  3. Run 'make up' to start services"

init: setup ## Alias for setup

## Docker Commands
build: ## Build Docker images
	@echo "$(GREEN)Building Docker images...$(NC)"
	$(DOCKER_COMPOSE) build --no-cache
	@echo "$(GREEN)✓ Build complete!$(NC)"

build-fast: ## Build Docker images (with cache)
	@echo "$(GREEN)Building Docker images (with cache)...$(NC)"
	$(DOCKER_COMPOSE) build
	@echo "$(GREEN)✓ Build complete!$(NC)"

up: ## Start all services
	@echo "$(GREEN)Starting services...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✓ Services started!$(NC)"
	@echo "Access the platform at: $(BLUE)http://localhost:$(HOST_PORT)$(NC)"

down: ## Stop all services
	@echo "$(YELLOW)Stopping services...$(NC)"
	$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✓ Services stopped!$(NC)"

restart: ## Restart all services
	@echo "$(YELLOW)Restarting services...$(NC)"
	$(MAKE) down
	$(MAKE) up

stop: ## Stop services without removing containers
	@echo "$(YELLOW)Stopping services...$(NC)"
	$(DOCKER_COMPOSE) stop
	@echo "$(GREEN)✓ Services stopped!$(NC)"

start: ## Start existing containers
	@echo "$(GREEN)Starting existing containers...$(NC)"
	$(DOCKER_COMPOSE) start
	@echo "$(GREEN)✓ Services started!$(NC)"

## Monitoring Commands
logs: ## View application logs (follow mode)
	@echo "$(GREEN)Showing logs (Ctrl+C to exit)...$(NC)"
	$(DOCKER_COMPOSE) logs -f $(CONTAINER_NAME)

logs-all: ## View all service logs
	@echo "$(GREEN)Showing all logs (Ctrl+C to exit)...$(NC)"
	$(DOCKER_COMPOSE) logs -f

logs-redis: ## View Redis logs
	@echo "$(GREEN)Showing Redis logs (Ctrl+C to exit)...$(NC)"
	$(DOCKER_COMPOSE) logs -f redis

status: ## Show container status
	@echo "$(GREEN)Container Status:$(NC)"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "$(GREEN)Health Check:$(NC)"
	@curl -s http://localhost:$(HOST_PORT)/health | python3 -m json.tool || echo "$(RED)Service not responding$(NC)"

stats: ## Show container resource usage
	@echo "$(GREEN)Container Resource Usage:$(NC)"
	$(DOCKER) stats $(CONTAINER_NAME) $(REDIS_CONTAINER)

health: ## Check platform health
	@echo "$(GREEN)Checking platform health...$(NC)"
	@curl -s http://localhost:$(HOST_PORT)/health | python3 -m json.tool

## Development Commands
shell: ## Access application shell
	@echo "$(GREEN)Accessing application shell...$(NC)"
	$(DOCKER) exec -it $(CONTAINER_NAME) /bin/bash

shell-redis: ## Access Redis CLI
	@echo "$(GREEN)Accessing Redis CLI...$(NC)"
	$(DOCKER) exec -it $(REDIS_CONTAINER) redis-cli

dev: ## Start in development mode with live reload
	@echo "$(GREEN)Starting in development mode...$(NC)"
	@export FLASK_ENV=development && \
	export FLASK_DEBUG=true && \
	$(DOCKER_COMPOSE) up

test-apis: ## Test all API connections
	@echo "$(GREEN)Testing API connections...$(NC)"
	@echo ""
	@echo "$(YELLOW)Testing Claude API...$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) python -c "from claude_client import ClaudeClient; c = ClaudeClient(); print('Claude:', 'Connected' if c.is_connected() else 'Not connected')" || echo "$(RED)Claude test failed$(NC)"
	@echo ""
	@echo "$(YELLOW)Testing PubMed API...$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) python -c "from pubmed_client import PubMedClient; p = PubMedClient(); print('PubMed:', 'Connected' if p.is_connected() else 'Not connected')" || echo "$(RED)PubMed test failed$(NC)"
	@echo ""
	@echo "$(YELLOW)Testing Asana API...$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) python -c "from asana_client import AsanaClient; a = AsanaClient(); print('Asana:', 'Connected' if a.is_connected() else 'Not connected')" || echo "$(RED)Asana test failed$(NC)"

python-shell: ## Open Python shell in container
	@echo "$(GREEN)Opening Python shell...$(NC)"
	$(DOCKER) exec -it $(CONTAINER_NAME) python

## Data Management
backup: ## Backup server files and configurations
	@echo "$(GREEN)Creating backup...$(NC)"
	@mkdir -p backups
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	tar -czf backups/backup_$$timestamp.tar.gz \
		server_files/ \
		templates/ \
		static/ \
		.env \
		docker-compose.yml || true
	@echo "$(GREEN)✓ Backup created in backups/ directory$(NC)"

restore: ## Restore from latest backup
	@echo "$(YELLOW)Restoring from latest backup...$(NC)"
	@latest_backup=$$(ls -t backups/*.tar.gz 2>/dev/null | head -1); \
	if [ -z "$$latest_backup" ]; then \
		echo "$(RED)No backup found!$(NC)"; \
		exit 1; \
	fi; \
	echo "$(GREEN)Restoring from $$latest_backup...$(NC)"; \
	tar -xzf $$latest_backup
	@echo "$(GREEN)✓ Restore complete!$(NC)"

export-data: ## Export all JSON data from server_files
	@echo "$(GREEN)Exporting data...$(NC)"
	@mkdir -p exports
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	cp -r server_files exports/data_$$timestamp
	@echo "$(GREEN)✓ Data exported to exports/data_$$timestamp$(NC)"

clean-logs: ## Clean log files
	@echo "$(YELLOW)Cleaning log files...$(NC)"
	@rm -f logs/*.log
	@touch logs/app.log
	@echo "$(GREEN)✓ Logs cleaned!$(NC)"

## Redis Commands
redis-flush: ## Flush Redis cache
	@echo "$(YELLOW)Flushing Redis cache...$(NC)"
	$(DOCKER) exec $(REDIS_CONTAINER) redis-cli FLUSHALL
	@echo "$(GREEN)✓ Redis cache flushed!$(NC)"

redis-info: ## Show Redis info
	@echo "$(GREEN)Redis Information:$(NC)"
	$(DOCKER) exec $(REDIS_CONTAINER) redis-cli INFO

redis-monitor: ## Monitor Redis commands in real-time
	@echo "$(GREEN)Monitoring Redis (Ctrl+C to exit)...$(NC)"
	$(DOCKER) exec -it $(REDIS_CONTAINER) redis-cli MONITOR

## Maintenance Commands
update: ## Update and restart services
	@echo "$(GREEN)Updating services...$(NC)"
	git pull || true
	$(MAKE) build
	$(MAKE) restart
	@echo "$(GREEN)✓ Update complete!$(NC)"

clean: ## Clean up containers and images
	@echo "$(RED)This will remove all containers and images!$(NC)"
	@echo "$(YELLOW)Continue? [y/N]$(NC)"
	@read -r response; \
	if [ "$$response" = "y" ]; then \
		$(DOCKER_COMPOSE) down -v --rmi all; \
		echo "$(GREEN)✓ Cleanup complete!$(NC)"; \
	else \
		echo "$(YELLOW)Cleanup cancelled$(NC)"; \
	fi

clean-volumes: ## Clean Docker volumes (preserves NAS data)
	@echo "$(YELLOW)Cleaning Docker volumes...$(NC)"
	$(DOCKER) volume prune -f
	@echo "$(GREEN)✓ Volumes cleaned!$(NC)"

prune: ## Prune unused Docker resources
	@echo "$(YELLOW)Pruning Docker resources...$(NC)"
	$(DOCKER) system prune -f
	@echo "$(GREEN)✓ Docker pruned!$(NC)"

## Quick Commands
quick-start: setup build up ## Quick start for new installations
	@echo "$(GREEN)Quick start complete!$(NC)"

rebuild: down build up ## Rebuild and restart everything
	@echo "$(GREEN)Rebuild complete!$(NC)"

refresh: ## Refresh application (restart without rebuild)
	@echo "$(YELLOW)Refreshing application...$(NC)"
	$(DOCKER_COMPOSE) restart $(CONTAINER_NAME)
	@echo "$(GREEN)✓ Application refreshed!$(NC)"

tail-logs: ## Tail application logs
	@$(DOCKER) exec $(CONTAINER_NAME) tail -f /app/logs/app.log

## Debugging Commands
debug-env: ## Show environment variables
	@echo "$(GREEN)Environment Variables:$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) env | grep -E "CLAUDE|PUBMED|ASANA|FLASK" | sort

debug-network: ## Test network connectivity
	@echo "$(GREEN)Testing network connectivity...$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) ping -c 3 api.anthropic.com || echo "$(RED)Cannot reach Claude API$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) ping -c 3 eutils.ncbi.nlm.nih.gov || echo "$(RED)Cannot reach PubMed$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) ping -c 3 app.asana.com || echo "$(RED)Cannot reach Asana$(NC)"

debug-nfs: ## Check NFS mounts
	@echo "$(GREEN)Checking NFS mounts...$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) df -h | grep nfs || echo "$(YELLOW)No NFS mounts found$(NC)"
	@echo ""
	@echo "$(GREEN)Testing NFS write access...$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) touch /app/server_files/test.txt && \
		$(DOCKER) exec $(CONTAINER_NAME) rm /app/server_files/test.txt && \
		echo "$(GREEN)✓ NFS write access OK$(NC)" || \
		echo "$(RED)✗ NFS write access failed$(NC)"

validate: ## Validate configuration files
	@echo "$(GREEN)Validating configuration...$(NC)"
	@python3 -m py_compile app.py claude_client.py pubmed_client.py asana_client.py 2>/dev/null && \
		echo "$(GREEN)✓ Python files valid$(NC)" || \
		echo "$(RED)✗ Python syntax errors found$(NC)"
	@docker-compose config --quiet && \
		echo "$(GREEN)✓ docker-compose.yml valid$(NC)" || \
		echo "$(RED)✗ docker-compose.yml invalid$(NC)"

## Information Commands
version: ## Show version information
	@echo "$(GREEN)Multi-API Research Platform$(NC)"
	@echo "Version: 1.0.0"
	@echo "Python: $$($(PYTHON) --version)"
	@echo "Docker: $$($(DOCKER) --version)"
	@echo "Docker Compose: $$($(DOCKER_COMPOSE) --version)"

info: ## Show platform information
	@echo "$(GREEN)Platform Information:$(NC)"
	@echo "  URL: http://localhost:$(HOST_PORT)"
	@echo "  NAS IP: $(NAS_IP)"
	@echo "  Container: $(CONTAINER_NAME)"
	@echo "  Image: $(IMAGE_NAME)"
	@echo ""
	@$(MAKE) status

# Hidden targets for advanced users
.install-local: ## Install Python dependencies locally (hidden)
	$(PIP) install -r requirements.txt
	$(PYTHON) -m spacy download en_core_web_sm

.test-local: ## Run tests locally (hidden)
	$(PYTHON) -m pytest tests/ -v
