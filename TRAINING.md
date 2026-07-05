# Entrenamiento: Domina el Bot de Terminal

## 1. Gestión de procesos (matar y reiniciar)

```bash
# Ver qué procesos del bot están corriendo
ps aux | grep "python3.*bot" | grep -v grep

# Salida típica:
# andres  2184  python3 -m src.english_agent.bot   ← proceso VIVO

# Matar un proceso por PID
kill 2184

# Matar por nombre (sin buscar PID)
kill $(pgrep -f "python3.*src.english_agent.bot")

# Verificar que murió
ps aux | grep "python3.*bot" | grep -v grep
# → No debe mostrar nada
```

## 2. Arrancar el bot

```bash
# Ir al proyecto
cd ~/Documents/EnglishAgent

# En primer plano (ves los logs en vivo, Ctrl+C para parar)
python3 -m src.english_agent.bot

# En segundo plano (sigue funcionando aunque cierres terminal)
nohup python3 -m src.english_agent.bot > bot.log 2>&1 &

# Explicación:
#   nohup        → ignora la señal de "colgar" (sigue vivo al cerrar terminal)
#   > bot.log    → redirige la salida a un archivo
#   2>&1         → también redirige los errores al mismo archivo
#   &            → ejecuta en segundo plano
```

## 3. Ver logs

```bash
# Ver últimas líneas
tail -f bot.log

# Salida típica:
# ❌ ERROR: algo explotó aquí       ← BÚSCALO
# ✅ HTTP 200 OK                     ← Respuesta correcta

# Buscar errores en los logs
grep -i "error\|traceback\|exception" bot.log

# Ver las últimas 20 líneas
tail -20 bot.log

# Ver el log completo (y salir con q)
less bot.log
```

## 4. Lo que pasó hoy (diagnóstico en vivo)

**Síntoma**: El bot no respondía a otros usuarios

**Diagnóstico**:
```bash
ps aux | grep python3.*bot
# → Mostró un proceso VIVO con PID 2184, arrancado a las 11:25
# → Ese proceso tenía el código ANTIGUO (con filtro de usuario)
```

**Causas reales** (hubo 2):
1. El proceso viejo seguía corriendo — los cambios en archivos NO afectan procesos ya iniciados
2. La función `scheduler.setup_writing_topic_reminder()` usaba `days_of_week=` que no existe en la versión instalada de python-telegram-bot v22 → debe ser `days=`

**Solución**:
```bash
# 1. Matar el proceso viejo
kill 2184

# 2. Corregir el error en scheduler.py (days_of_week → days)

# 3. Arrancar de nuevo
cd ~/Documents/EnglishAgent && nohup python3 -m src.english_agent.bot > bot.log 2>&1 &

# 4. Verificar que arrancó sin errores
cat bot.log
# Buscar: ✅ HTTP 200 OK y "Application started"
# Si ves "Traceback" → hay error, compártelo
```

## 5. Verificar que el bot está vivo

```bash
# Revisar logs en tiempo real
tail -f bot.log

# Debe mostrar algo como:
# HTTP Request: POST https://api.telegram.org/.../getMe "HTTP/1.1 200 OK"
# HTTP Request: POST https://api.telegram.org/.../deleteWebhook "HTTP/1.1 200 OK"
# Application started
```

Si ves `200 OK` → el bot está conectado a Telegram.
Si ves `Traceback` o `Error` → algo falló al arrancar.

## 6. Cómo saber qué versión de un paquete tienes

```bash
# Versión de python-telegram-bot
pip3 show python-telegram-bot | grep Version

# Para qué sirve: cada versión tiene parámetros distintos
# Ejemplo: v20+ usa `days=`, versiones anteriores usaban `days_of_week=`
```

## 7. Ciclo completo de "algo no funciona"

```
1. Ver procesos     → ps aux | grep python
2. Ver logs         → tail -f bot.log
3. Buscar errores   → grep -i error bot.log
4. Matar si hay     → kill <PID>
5. Corregir código  → editar el archivo
6. Re-arrancar      → nohup python3 -m src.english_agent.bot > bot.log 2>&1 &
7. Verificar        → cat bot.log (buscar "200 OK" y "Application started")
```

## 8. Comandos útiles para el día a día

```bash
# Ver el proyecto
ls ~/Documents/EnglishAgent/
ls ~/Documents/EnglishAgent/src/english_agent/

# Ver el .env (tokens, config)
cat ~/Documents/EnglishAgent/.env

# Ver cambios recientes en el código
cd ~/Documents/EnglishAgent && git diff --stat HEAD

# Buscar una palabra en todo el código
grep -r "CHAT_ID" ~/Documents/EnglishAgent/src/

# Ver el log del bot en tiempo real
tail -f ~/Documents/EnglishAgent/bot.log
```

## Resumen de esta sesión

| Qué aprendiste | Por qué es útil |
|----------------|----------------|
| `ps aux \| grep` | Ver procesos vivos |
| `kill <PID>` | Matar procesos colgados |
| `nohup ... &` | Arrancar en segundo plano |
| `tail -f` | Ver logs en tiempo real |
| `grep -i error` | Buscar errores en logs |
| Los archivos editados no afectan procesos ya corriendo | Saber que hay que reiniciar |
| `pip3 show` | Saber versión de paquetes |
| Parámetros de API cambian entre versiones | Buscar en docs antes de asumir |
