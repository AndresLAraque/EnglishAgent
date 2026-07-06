# Migrar EnglishAgent a Raspberry Pi

## 1. Copiar clave SSH (pide contraseña de la RPi)
```bash
ssh-copy-id -i ~/.ssh/rpi_englishagent.pub andrespi@192.168.80.20
```

## 2. Ejecutar despliegue automático
```bash
cd ~/Documents/EnglishAgent && ./deploy_rpi.sh
```

## 3. Si el deploy falla con `docker compose` → instalar docker-compose
```bash
ssh rpi "sudo apt-get install -y docker-compose"
```

## 4. Iniciar el bot manualmente
```bash
ssh rpi "cd /home/andrespi/english-agent && docker-compose up -d"
```

## 5. Ver progreso de la primera compilación (descarga ~2.6GB)
```bash
ssh rpi "tail -3 /tmp/docker-compose.log"
```

## 6. Verificar que el bot esté corriendo
```bash
ssh rpi "cd /home/andrespi/english-agent && docker-compose ps"
```

---

## Comandos de operación diaria
```bash
# Ver logs del bot
ssh rpi "docker-compose -f /home/andrespi/english-agent/docker-compose.yml logs -f bot"

# Ver logs de Ollama
ssh rpi "docker-compose -f /home/andrespi/english-agent/docker-compose.yml logs -f ollama"

# Detener todo
ssh rpi "docker-compose -f /home/andrespi/english-agent/docker-compose.yml down"

# Reiniciar bot
ssh rpi "docker-compose -f /home/andrespi/english-agent/docker-compose.yml restart bot"

# Tareas esclavo (stats, correct, etc.)
~/scripts/rpi_task.sh stats
~/scripts/rpi_task.sh correct "She go to school"
```

## Descargar modelo Ollama en la RPi
```bash
ssh rpi "docker exec english-ollama ollama pull qwen2.5:0.5b"
```

## Desde Windows
```powershell
type C:\Users\andres\.ssh\rpi_englishagent.pub | ssh andrespi@192.168.80.20 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
ssh andrespi@192.168.80.20
```
