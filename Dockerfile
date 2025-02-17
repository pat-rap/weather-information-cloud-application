FROM python:3.13

WORKDIR /app

COPY ./app /app/app
COPY ./db.sql /app/db.sql
COPY ./.env /app/.env

RUN pip install --no-cache-dir -r /app/app/requirements.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
