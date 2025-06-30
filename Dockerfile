# Используем многоэтапную сборку для минимизации финального образа
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    # Устанавливаем домашнюю директорию внутри WORKDIR
    HOME=/app \
    # Отключаем запись pyc файлов для зависимостей
    PYTHONDONTWRITEBYTECODE=1 \
    # Отключаем буферизацию вывода
    PYTHONUNBUFFERED=1

WORKDIR /app

# Копируем только файлы зависимостей для лучшего использования кэша
COPY pyproject.toml uv.lock ./

# Установка зависимостей с кэшированием
RUN --mount=type=cache,target=/app/.cache/uv \
    uv sync --frozen --no-dev

# Копируем остальные файлы приложения
COPY . .

# Финальный образ
FROM python:3.12-slim-bookworm

ARG USER_NAME=user
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Создаем непривилегированного пользователя
RUN groupadd --gid $USER_GID $USER_NAME && \
    useradd --uid $USER_UID --gid $USER_GID -m $USER_NAME

# Копируем приложение с правильными правами
COPY --from=builder --chown=$USER_UID:$USER_GID /app /app

USER $USER_NAME
WORKDIR /app

# Настраиваем PATH для виртуального окружения
ENV PATH="/app/.venv/bin:$PATH"

# Запускаем приложение напрямую без оболочки
ENTRYPOINT ["/app/.venv/bin/python", "/app/gun_law_quiz_tg_bot.py"]
#ENTRYPOINT ["sh", "-c", "/app/.venv/bin/python -V && /app/.venv/bin/python gun_law_quiz_tg_bot.py"]