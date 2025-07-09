runserver:
	cd web && uv run ./manage.py runserver

worker:
	cd web && uv run celery -A mdh worker -l debug

beat:
	cd web && uv run celery -A mdh beat -l debug

runserver-prod:
	cd web && uv run gunicorn mdh.wsgi -w 2 --bind 0.0.0.0:8000

worker-prod:
	cd web && uv run celery -A mdh worker -l info

beat-prod:
	cd web ** uv run celery -A mdh beat -l info

createsuperuser:
	cd web && uv run ./manage.py createsuperuser

migrate:
	cd web && uv run ./manage.py migrate

migrations:
	cd web && uv run ./manage.py makemigrations

collectstatic:
	cd web && uv run ./manage.py collectstatic

createcachetable:
	cd web && uv run ./manage.py createcachetable

init-database:
	cd web && uv run ./manage.py init_database

create-default-subplans:
	cd web && uv run ./manage.py create_default_plans

db:
	docker run --rm -v data:/var/lib/postgresql/data \
		--name mdh-db \
		-p 5432:5432 \
		-e POSTGRES_DB=mdh \
		-e POSTGRES_USER=mdh \
		-e POSTGRES_PASSWORD=mdh \
		-d docker.io/postgres:16.4-alpine3.19
flower:
	docker compose up -d flower

# Docker - Dev
dev-build:
	docker compose --profile dev build

dev-up:
	docker compose --profile dev up -d

dev-logs:
	docker compose --profile dev logs -f

dev-restart:
	docker compose --profile dev restart

dev-logs-web:
	docker compose --profile dev logs -f web-dev

dev-logs-db:
	docker compose --profile dev logs -f db

dev-down:
	docker compose --profile dev down --remove-orphans

dev-migrations:
	docker compose --profile dev exec -it web-dev uv run python manage.py makemigrations

dev-migrate:
	docker compose --profile dev exec -it web-dev uv run python manage.py migrate

dev-createcachetable:
	docker compose --profile dev exec -it web-dev uv run python manage.py createcachetable

dev-init-database:
	docker compose --profile dev exec -it web-dev uv run python manage.py init_database

dev-createsuperuser:
	docker compose --profile dev exec -it web-dev uv run python manage.py createsuperuser

dev-collectstatic:
	docker compose --profile dev exec -it web-dev uv run python manage.py collectstatic

# Docker - Prod
prod-build:
	docker compose --profile prod build

prod-up:
	docker compose --profile prod up -d

prod-logs:
	docker compose --profile prod logs -f

prod-restart:
	docker compose --profile prod restart

prod-logs-web:
	docker compose --profile prod logs -f web

prod-logs-db:
	docker compose --profile prod logs -f db

prod-down:
	docker compose --profile prod down --remove-orphans

prod-migrations:
	docker compose --profile prod exec -it web uv run python manage.py makemigrations

prod-migrate:
	docker compose --profile prod exec -it web uv run python manage.py migrate

prod-createcachetable:
	docker compose --profile prod exec -it web uv run python manage.py createcachetable

prod-init-database:
	docker compose --profile prod exec -it web uv run python manage.py init_database

prod-createsuperuser:
	docker compose --profile prod exec -it web uv run python manage.py createsuperuser

prod-collectstatic:
	docker compose --profile prod exec -it web uv run python manage.py collectstatic

# only dbs
dbs:
	docker compose --profile only-dbs up -d

down:
	docker compose --profile only-dbs down
# Docker Common
clean:
	docker system prune -f

# Systemd setup
pull:
	git fetch -p && git pull

reload:
	sudo systemctl restart daemon-reload

mdh:
	sudo systemctl restart mdh && journalctl -u mdh

mdh-worker:
	sudo systemctl restart mdh-worker && journalctl -u mdh-worker
