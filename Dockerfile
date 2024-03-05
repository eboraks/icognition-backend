# 
FROM python:3.12-slim

WORKDIR /app

# Install libraries
COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app to the container
COPY ./app ./app

ENV HOST 0.0.0.0
EXPOSE 8080
# command: uvicorn app.main:app --host 0.0.0.0 --port "8889"
# Run the app
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$PORT"]
CMD uvicorn app.main:app --host 0.0.0.0 --port 8080