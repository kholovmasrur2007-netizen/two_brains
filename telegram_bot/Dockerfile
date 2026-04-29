# two_brains Telegram bot — production container.
#
#   docker build -t two_brains_bot:latest .
#   docker run -e TELEGRAM_BOT_TOKEN=xxx -e TWOBRAINS_URL=http://app:8000 two_brains_bot:latest

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bot.py .

# Run as a non-root user.
RUN useradd --create-home --shell /usr/sbin/nologin botuser
USER botuser

CMD ["python", "bot.py"]
