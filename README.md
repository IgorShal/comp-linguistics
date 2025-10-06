# compLinguistics

Запуск Django API корпуса текстов

1) Установка зависимостей

```bash
pip install -r requirements.txt
```

2) Переменные окружения (файл .env, опционально)

```ini
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=*

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_ENCRYPTED=0
```

3) Миграции и запуск

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

4) Эндпоинты

- CRUD Корпусов: `GET/POST/PUT/PATCH/DELETE /api/corpora/`
- CRUD Текстов: `GET/POST/PUT/PATCH/DELETE /api/texts/`
- Корпус c текстами: `GET /api/corpora/{id}/collect_corpus/`
- Здоровье онтологии Neo4j: `GET /api/ontology/health/`
- Классы онтологии: `GET /api/ontology/classes/`
