FROM python:3.12-slim
WORKDIR /lab
RUN python -m pip install --no-cache-dir fastapi uvicorn
COPY origin.py ./origin.py
CMD ["uvicorn", "origin:app", "--host", "0.0.0.0", "--port", "8000"]
