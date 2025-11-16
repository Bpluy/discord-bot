# Диагностика проблем с веб-панелью

## Проблема: Веб-панель не работает

### Шаг 1: Проверьте, что веб-панель включена

Убедитесь, что переменная окружения `WEB_PANEL_ENABLED=true` установлена:

**Вариант А: Через .env файл**
Создайте или отредактируйте файл `.env` в корне проекта:
```env
WEB_PANEL_ENABLED=true
WEB_PANEL_PORT=5000
```

**Вариант Б: Через переменные окружения системы**

Windows PowerShell:
```powershell
$env:WEB_PANEL_ENABLED="true"
$env:WEB_PANEL_PORT="5000"
```

Linux/Mac:
```bash
export WEB_PANEL_ENABLED=true
export WEB_PANEL_PORT=5000
```

### Шаг 2: Пересоберите Docker контейнер

После изменения переменных окружения необходимо пересобрать контейнер:

```bash
docker-compose down
docker-compose up -d --build
```

### Шаг 3: Проверьте логи

Проверьте логи контейнера на наличие сообщений о веб-панели:

```bash
docker-compose logs discord-bot | grep -i "веб-панель\|web panel\|flask"
```

Или все логи:
```bash
docker-compose logs discord-bot
```

Вы должны увидеть одно из сообщений:
- ✅ `Веб-панель инициализирована, будет доступна на http://0.0.0.0:5000`
- ⚠️ `Flask не установлен. Веб-панель недоступна`
- ℹ️ `Веб-панель отключена. Установите WEB_PANEL_ENABLED=true для включения.`

### Шаг 4: Проверьте, что порт проброшен

Убедитесь, что в `docker-compose.yml` раскомментирована секция `ports`:

```yaml
ports:
  - "5000:5000"
```

### Шаг 5: Проверьте доступность

Попробуйте открыть в браузере:
- http://localhost:5000
- http://127.0.0.1:5000

Если бот запущен на удалённом сервере, используйте IP сервера:
- http://IP_СЕРВЕРА:5000

### Шаг 6: Проверьте, что Flask установлен

Если видите ошибку "Flask не установлен", убедитесь, что `requirements.txt` содержит:
```
flask>=2.3.0
flask-cors>=4.0.0
```

И пересоберите образ:
```bash
docker-compose build --no-cache
docker-compose up -d
```

### Шаг 7: Проверьте файрвол

Убедитесь, что порт 5000 не заблокирован файрволом:
- Windows: Проверьте настройки брандмауэра Windows
- Linux: `sudo ufw allow 5000` или `sudo firewall-cmd --add-port=5000/tcp --permanent`

## Частые ошибки

### Ошибка: "Connection refused"
- Проверьте, что контейнер запущен: `docker-compose ps`
- Проверьте логи на наличие ошибок
- Убедитесь, что порт проброшен в docker-compose.yml

### Ошибка: "Flask не установлен"
- Пересоберите образ: `docker-compose build --no-cache`
- Проверьте, что requirements.txt содержит flask и flask-cors

### Веб-панель не загружается
- Проверьте логи контейнера
- Убедитесь, что WEB_PANEL_ENABLED=true
- Проверьте, что порт 5000 доступен

