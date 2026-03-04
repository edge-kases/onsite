FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dataplane/ ./dataplane/
COPY agent/ ./agent/
EXPOSE 8080
WORKDIR /app/dataplane
CMD ["python", "main.py"]
