FROM python:3.14-slim

WORKDIR /srv/backend
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN useradd --no-create-home --uid 10001 adrobot
USER adrobot

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
