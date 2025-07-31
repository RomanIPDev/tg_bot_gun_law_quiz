# tg_bot_gun_law_quiz
Telegram-бот для проверки знаний Правил безопасного обращения с оружием (БОО)

## 📚 Источник вопросов
Вопросы взяты из официального документа:
[Вопросы_для_подготовки_к_аттестации_по_обучению_на_гражданское_оружие.pdf](https://drive.google.com/file/d/1T1OM-bTaktLCJ5Fms8iHFWpN6S-ubEMV/)

## 🛠 Установка и запуск
### 1. Клонирование репозитория
```bash
git clone https://github.com/RomanIPDev/tg_bot_gun_law_quiz.git
cd tg_bot_gun_law_quiz
```
### 2. Сборка Docker-образа
```bash
docker-compose -f docker-compose.build.yml build
```
### 3. Запуск бота (в фоновом режиме)
```bash
docker-compose up -d
```

## 📱 Скриншоты бота @GunLawTest_Bot
<img src="https://github.com/user-attachments/assets/7b90fe3a-4408-4999-8c24-cead8ca4b5bd" width="200" alt="Gun Law Quiz Bot">
<img src="https://github.com/user-attachments/assets/673d6ad7-8fdb-4c7a-b042-2825abd37bd9" width="200" alt="Gun Law Quiz Bot">
<img src="https://github.com/user-attachments/assets/5d5c4eab-2c97-4e0d-ae92-6c7d1a05be3b" width="200" alt="Gun Law Quiz Bot">
<img src="https://github.com/user-attachments/assets/c59f6b5b-290e-431e-bb4b-fb19943cfd53" width="200" alt="Gun Law Quiz Bot">


## ⚠️ Важно

Для работы бота требуется Docker и Docker Compose.

Бот не хранит персональные данные пользователей.

Актуальность вопросов сверяйте с официальным источником.
