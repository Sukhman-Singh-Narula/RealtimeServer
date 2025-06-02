# ESP32 Language Learning System - Docker Management

.PHONY: help build up down restart logs shell test clean backup restore status

# Default target
help:
	@echo "ESP32 Language Learning System - Docker Commands"
	@echo "================================================"
	@echo "setup     - Initial setup (copy .env, create dirs)"
	@echo "build     - Build the Docker images"
	@echo "up        - Start all services"
	@echo "down      - Stop all services"
	@echo "restart   - Restart all services"
	@echo "logs      - Show logs from all services"
	@echo "logs-app  - Show only application logs"
	@echo "shell     - Open shell in app container"
	@echo "test      - Run test client"
	@echo "clean     - Clean up containers and images"
	@echo "backup    - Create manual backup"
	@echo "restore   - List available backups"
	@echo "status    - Show service status"
	@echo "monitor   - Monitor application health"

# Initial setup
setup:
	@echo "Setting up environment..."
	@mkdir -p data logs backups monitoring
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env file - please edit with your OpenAI API key"; \
	fi
	@if [ ! -f firebase-credentials.json ]; then \
		echo "WARNING: firebase-credentials.json not found!"; \
		echo "Please add your Firebase credentials file"; \
	fi
	@echo "Setup complete!"

# Build Docker images
build:
	@echo "Building Docker images..."
	docker-compose build --no-cache

# Start all services
up:
	@echo "Starting ESP32 Language Learning System..."
	docker-compose up -d
	@echo "Services started!"
	@echo "Application will be available at: http://localhost:8000"
	@echo "Check status with: make status"

# Stop all services
down:
	@echo "Stopping all services..."
	docker-compose down

# Restart all services
restart:
	@echo "Restarting services..."
	docker-compose restart

# Show logs
logs:
	docker-compose logs -f

# Show only app logs
logs-app:
	docker-compose logs -f app

# Open shell in app container
shell:
	docker-compose exec app /bin/bash

# Run the test client (requires Python locally)
test:
	@echo "Running test client..."
	@if [ -f testing/test.py ]; then \
		cd testing && python test.py; \
	else \
		echo "Test file not found at testing/test.py"; \
	fi

# Clean up everything
clean:
	@echo "Cleaning up containers and images..."
	docker-compose down -v --rmi all
	docker system prune -f

# Create manual backup
backup:
	@echo "Creating manual backup..."
	@timestamp=$$(date +%Y%m%d-%H%M%S); \
	docker-compose exec app tar -czf /app/data/manual-backup-$$timestamp.tar.gz -C /app/data .; \
	echo "Backup created: manual-backup-$$timestamp.tar.gz"

# List available backups
restore:
	@echo "Available backups:"
	@docker-compose exec app ls -la /app/data/*.tar.gz 2>/dev/null || echo "No backups found"

# Show service status
status:
	@echo "Service Status:"
	@echo "==============="
	docker-compose ps
	@echo ""
	@echo "Application Health:"
	@curl -s http://localhost:8000/status 2>/dev/null | python -m json.tool || echo "Application not responding"

# Monitor application
monitor:
	@echo "Monitoring application (Ctrl+C to stop)..."
	@while true; do \
		clear; \
		echo "ESP32 Language Learning System - Live Monitor"; \
		echo "Time: $$(date)"; \
		echo "==========================================="; \
		echo ""; \
		echo "Service Status:"; \
		docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"; \
		echo ""; \
		echo "Application Health:"; \
		curl -s http://localhost:8000/status 2>/dev/null | python -m json.tool || echo "❌ Application not responding"; \
		echo ""; \
		echo "Recent Logs (last 5 lines):"; \
		docker-compose logs --tail=5 app | tail -5; \
		sleep 5; \
	done

# Development targets
dev-up:
	@echo "Starting in development mode..."
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

dev-logs:
	docker-compose logs -f app redis