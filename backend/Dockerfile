# Build a partir da RAIZ do repositório (não de dentro de backend/), porque
# o app também serve os arquivos estáticos de ../frontend. Na Railway, isso é
# configurado apontando o "Dockerfile Path" para backend/Dockerfile enquanto o
# contexto de build continua sendo a raiz (ver railway.toml).

FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY frontend/ /app/frontend

EXPOSE 8000
CMD ["python", "app.py"]
