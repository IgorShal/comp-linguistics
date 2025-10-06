МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ РОССИЙСКОЙ ФЕДЕРАЦИИ

ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ АВТОНОМНОЕ ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ ВЫСШЕГО ОБРАЗОВАНИЯ
«НОВОСИБИРСКИЙ НАЦИОНАЛЬНЫЙ ИССЛЕДОВАТЕЛЬСКИЙ ГОСУДАРСТВЕННЫЙ УНИВЕРСИТЕТ»

ФАКУЛЬТЕТ ИНФОРМАЦИОННЫХ ТЕХНОЛОГИЙ

Кафедра Систем информатики 
Направление подготовки 09.06.01 – Информатика и вычислительная техника


ОТЧЕТ

Обучающегося Шалыгина Игоря Дмитриевича группы № 22214 курса 4
(Ф.И.О. полностью)

Тема задания: Django REST API


Оглавление

- Введение
- Реализация
- Модели данных
- Эндпоинты
- Как запустить
- Мини‑примеры
- Заключение


Введение
Цель работы — разработать веб‑хранилище корпуса текстов единой предметной области с CRUD‑интерфейсами и онтологическими операциями на базе Django + DRF и Neo4j.


Реализация
- Стек: Django 3.0.3, Django REST Framework, SQLite (по умолчанию), Neo4j (для онтологии).
- Структура: приложение `db` (модели, вью‑функции, URL‑ы), репозитории в `db/api`.
- Для работы с Neo4j используется класс‑репозиторий `repositories/neo4j_repository.py`, адаптированный в `db/api/OntologyRepository.py`.
- DRF Browsable API доступен для объявленных эндпоинтов.


Модели данных (Django)
- Corpus (`db/models.py`):
  - name: CharField(255)
  - description: TextField (nullable)
  - genre: CharField(128) (nullable)
- Text (`db/models.py`):
  - title: CharField(255)
  - description: TextField (nullable)
  - text: TextField (полный текст)
  - corpus: ForeignKey → Corpus (CASCADE), related_name="texts"
  - has_translation: ManyToManyField('self', symmetrical=False) — связь «имеет перевод»/«является переводом»


Эндпоинты
Базовый префикс: `api/` (см. `core/urls.py`, `db/urls.py`).

- Корпуса (`db/views.py`):
  - POST `api/corpus/create` — создать корпус
  - PUT/PATCH `api/corpus/update?id={id}` — обновить корпус
  - GET `api/corpus/get?id={id}` — получить корпус c вложенными текстами
  - DELETE `api/corpus/delete?id={id}` — удалить корпус

- Тексты (`db/views.py`):
  - POST `api/text/create` — создать текст
  - PUT/PATCH `api/text/update?id={id}` — обновить текст
  - GET `api/text/get?id={id}` — получить текст
  - DELETE `api/text/delete?id={id}` — удалить текст

- Онтология (Neo4j) (`db/api/OntologyRepository.py`, `db/views.py`):
  - GET `api/ontology/nodes` — получить все узлы (служебный просмотр)
  - POST `api/ontology/create_class` — создать класс (title, description?, parent_title?)

Примечание: дополнительные онтологические операции (узлы/рёбра/объекты/атрибуты) легко расширяются на базе методов `repositories/neo4j_repository.py`.


Как запустить
1) Установить зависимости:
   - `pip install -r requirements.txt` (внутри каталога `skeleton/` создано локальное venv)
2) Миграции:
   - `python manage.py makemigrations`
   - `python manage.py migrate`
3) Запуск сервера разработки:
   - `python manage.py runserver`
4) Доступ:
   - API: `http://localhost:8000/api/…`
   - Админка: `http://localhost:8000/admin/` (создайте суперпользователя при необходимости: `python manage.py createsuperuser`)

Neo4j (для онтологии)
- Укажите переменные окружения (например, в `.env`):
  - `NEO4J_URI=bolt://localhost:7687`
  - `NEO4J_USER=neo4j`
  - `NEO4J_PASSWORD=…`
- Подключение используется в `db/api/OntologyRepository.py` и `db/api/DriverRepository.py`.


Мини‑примеры
- Создать корпус:
  POST `api/corpus/create`
  JSON: {"name": "Мой корпус", "description": "…", "genre": "новости"}

- Создать текст:
  POST `api/text/create`
  JSON: {"title": "Заголовок", "description": "…", "text": "Полный текст…", "corpus_id": 1, "has_translation_ids": [2,3]}

- Создать класс онтологии:
  POST `api/ontology/create_class`
  JSON: {"title": "Document", "description": "…", "parent_title": null}

- Просмотр узлов онтологии:
  GET `api/ontology/nodes`


Заключение
Реализованы модели корпуса текстов и REST‑эндпоинты для управления корпусами и текстами, а также базовые операции с онтологией в Neo4j (создание класса, просмотр узлов). Архитектура опирается на репозитории, что позволяет оперативно расширять API за счет готовых методов `Neo4jRepository` (создание/обновление узлов, рёбер, объектов, атрибутов и т.д.). Все операции доступны через DRF Browsable API и админ‑интерфейс Django.
