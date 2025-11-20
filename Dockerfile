# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем метаданные
LABEL maintainer="Discord Bot"
LABEL description="Discord Bot with Spotify and YouTube music support"

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Создаём рабочую директорию
WORKDIR /app

# Копируем requirements.txt
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY bot.py .
COPY web_panel.py .

# Копируем шаблоны веб-панели
COPY templates/ ./templates/

# Создаём пользователя без прав root для безопасности
RUN useradd -m -u 1000 botuser && \
    mkdir -p /app/data && \
    chown -R botuser:botuser /app

USER botuser

# Устанавливаем переменную окружения Python
ENV PYTHONUNBUFFERED=1

# Запускаем бота
CMD ["python", "bot.py"]

