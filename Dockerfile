FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY expense_bot.py .

RUN mkdir -p logs

CMD ["python", "expense_bot.py"]
