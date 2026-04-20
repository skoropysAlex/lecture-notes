# Як запушити проект на GitHub

Покрокова інструкція для створення публічного (або приватного) репозиторію з цим проектом.

## Попередньо

Тобі знадобиться:
- Аккаунт GitHub (https://github.com)
- Встановлений Git (https://git-scm.com/download/win)

Перевір чи є Git:
```
git --version
```
Якщо не знаходить — встанови, при інсталяції став галочку "Use Git from the Windows Command Prompt".

## Крок 1: Налаштуй Git (один раз на всіх проектах)

```
git config --global user.name "Твоє Ім'я"
git config --global user.email "твоя@пошта.com"
```

Пошту використовуй ту, що в GitHub акаунті.

## Крок 2: Підготуй локально папку проекту

Перед комітом переконайся, що в `C:\lectures\` є:
- ✅ `process.py`
- ✅ `google_drive_export.py`
- ✅ `обробити_лекцію.bat`
- ✅ `requirements.txt`
- ✅ `README.md`
- ✅ `CLAUDE.md`
- ✅ `.gitignore`
- ❌ **НЕ повинно бути** `credentials.json` (це твій секрет!)
- ❌ **НЕ повинно бути** `token.json`

Перевір що секретів нема:
```powershell
ls C:\lectures\credentials.json
```

Якщо є — все одно `.gitignore` їх не пустить, але подвійна перевірка не завадить.

## Крок 3: Ініціалізуй Git репозиторій

У PowerShell:
```powershell
cd C:\lectures
git init
git add .
git commit -m "Initial commit: lecture notes pipeline"
```

Команда `git add .` додасть усі файли **крім** тих, що в `.gitignore` (venv, credentials, output тощо).

Перевір що все правильно:
```
git status
```
Має сказати "nothing to commit, working tree clean".

Подивися що точно закоммітилось:
```
git ls-files
```
Не повинно бути `credentials.json`, `token.json`, `venv/*`, `output/*`.

## Крок 4: Створи репозиторій на GitHub

1. Зайди на https://github.com/new
2. **Repository name:** `lecture-notes` (або інша назва)
3. **Description:** "Automated lecture/screencast → Google Doc with slides, transcript and OCR"
4. **Public** (щоб ділитись) або **Private** (для себе)
5. **НЕ** став галочки на "Add README", "Add .gitignore", "Choose license" — у нас вже є
6. Натисни **Create repository**

GitHub покаже команди. Тобі потрібна секція **"…or push an existing repository from the command line"**.

## Крок 5: Залий локальний репо на GitHub

Скопіюй команди з GitHub (вони з твоїм username), приблизно так:

```powershell
git remote add origin https://github.com/твій-username/lecture-notes.git
git branch -M main
git push -u origin main
```

Перший push запитає логін і пароль. Сучасний GitHub вимагає **personal access token** замість пароля:

1. На GitHub → правий верхній кут → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token (classic)
3. Галочка "repo" (full control)
4. Скопіюй токен — **це твій "пароль"**, вставляй його коли Git запитає

Після першого успішного push Git збереже токен, більше не запитуватиме.

## Крок 6: Готово!

Перейди на `https://github.com/твій-username/lecture-notes` — побачиш всі файли з README. README рендериться автоматично.

## Як оновлювати проект далі

Щоразу як щось зміниш:
```powershell
cd C:\lectures
git add .
git commit -m "короткий опис що змінив"
git push
```

Три команди — і все на GitHub.

## Якщо випадково закоммітив credentials.json

НЕ панікуй, але дій швидко:

1. Негайно **відклич credentials** у Google Cloud Console (створи нові)
2. Видали файл з історії:
   ```
   git rm --cached credentials.json
   git commit -m "Remove accidentally committed credentials"
   git push
   ```
3. Але історія все ще містить файл. Для повного видалення потрібен `git filter-repo` або BFG Repo Cleaner. Простіше в цьому випадку — створити репо заново.

## Примітка щодо ліцензії

У README.md вказано MIT — це дозвіл будь-кому використовувати твій код. Якщо не хочеш — можеш видалити секцію "Ліцензія" з README або змінити на "All rights reserved".
