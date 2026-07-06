# Migración a Raspberry Pi

## Requisitos

- Raspberry Pi (3/4/5) con Raspberry Pi OS (64-bit recomendado)
- WiFi o Ethernet con IP fija: `192.168.80.20`
- Usuario: `andrespi`

## Acceso SSH

### Desde Ubuntu (ya configurado)

```bash
# Conexión simple
ssh andrespi@192.168.80.20

# O usando el alias (ya configurado en ~/.ssh/config)
ssh rpi
```

### Desde Windows

1. **Con clave SSH** (recomendado):
   ```powershell
   # Copiar la clave pública a la RPi (una sola vez, pide contraseña)
   type C:\Users\andres\.ssh\rpi_englishagent.pub | ssh andrespi@192.168.80.20 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

   # Conectar
   ssh -i C:\Users\andres\.ssh\rpi_englishagent andrespi@192.168.80.20
   ```

2. **Con contraseña**:
   ```powershell
   ssh andrespi@192.168.80.20
   # Ingresar contraseña cuando la pida
   ```

> **Nota**: La clave `rpi_englishagent` está en `~/.ssh/` en Ubuntu.
> Cópiala a Windows si quieres usar el mismo par de llaves:
> - Ubuntu: `~/.ssh/rpi_englishagent` y `~/.ssh/rpi_englishagent.pub`
> - Cópialos a `C:\Users\andres\.ssh\` en Windows

## Despliegue automático

```bash
chmod +x deploy_rpi.sh
./deploy_rpi.sh
```

Esto:
1. Copia tu clave SSH a la RPi
2. Instala Docker en la RPi
3. Transfiere el proyecto completo
4. Configura `.env`
5. Levanta los contenedores (ollama + bot)
6. Crea un servicio systemd para auto-inicio

## Despliegue manual (alternativa)

```bash
# 1. Conectar a la RPi
ssh andrespi@192.168.80.20

# 2. Instalar Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Cerrar sesión y volver a entrar

# 3. Preparar directorio
mkdir -p ~/english-agent

# 4. Copiar proyecto (desde Ubuntu)
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' --exclude='*.log' --exclude='.env' ~/Documents/EnglishAgent/ andrespi@192.168.80.20:~/english-agent/

# 5. Copiar .env
scp ~/Documents/EnglishAgent/.env andrespi@192.168.80.20:~/english-agent/.env

# 6. Iniciar
ssh andrespi@192.168.80.20 "cd ~/english-agent && docker-compose up -d"

# 7. Pull modelo Ollama
ssh andrespi@192.168.80.20 "docker exec english-ollama ollama pull qwen2.5:0.5b"
```

## Comandos útiles

```bash
# Ver logs del bot
ssh rpi "docker-compose -f ~/english-agent/docker-compose.yml logs -f bot"

# Ver logs de Ollama
ssh rpi "docker-compose -f ~/english-agent/docker-compose.yml logs -f ollama"

# Reiniciar bot
ssh rpi "docker-compose -f ~/english-agent/docker-compose.yml restart bot"

# Detener todo
ssh rpi "docker-compose -f ~/english-agent/docker-compose.yml down"

# Actualizar bot (después de cambios en el código)
./deploy_rpi.sh
# O manual:
rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' --exclude='*.log' --exclude='.env' ~/Documents/EnglishAgent/ andrespi@192.168.80.20:~/english-agent/
ssh rpi "docker-compose -f ~/english-agent/docker-compose.yml restart bot"
```

## RPi como nodo esclavo

La RPi también puede servir como worker para tareas desde esta máquina Ubuntu:

### Uso como servidor Ollama remoto

```bash
# En este Ubuntu, apunta a Ollama en la RPi
export OLLAMA_BASE_URL=http://192.168.80.20:11434

# Luego los comandos del bot usan la RPi en vez del Ollama local
english-agent explain "perseverance"
```

### Tareas programadas desde la RPi

Puedes ejecutar comandos del bot en la RPi desde este equipo:

```bash
# Recordatorio diario
ssh rpi "cd ~/english-agent && docker-compose exec -T bot english-agent notify 'Time to study!  📚'"

# Ver estadísticas
ssh rpi "cd ~/english-agent && docker-compose exec -T bot english-agent stats"

# Corrección de texto
ssh rpi "cd ~/english-agent && docker-compose exec -T bot english-agent correct 'She go to school yesterday'"
```

### Script helper para tareas esclavo

```bash
#!/bin/bash
# ~/scripts/rpi_task.sh
RPI_CMD="ssh rpi \"cd ~/english-agent && docker-compose exec -T bot english-agent $*\""
eval $RPI_CMD
```

Uso: `rpi_task.sh stats` o `rpi_task.sh correct "She go to school"`

## WiFi vs Ethernet

Actualmente estás en WiFi. Para mejor estabilidad:

1. Conecta la RPi al router por Ethernet
2. La IP puede cambiar. Para fijarla:
   ```bash
   ssh rpi "sudo nmcli con mod 'Wired connection 1' ipv4.addresses 192.168.80.20/24 ipv4.method manual"
   ssh rpi "sudo nmcli con up 'Wired connection 1'"
   ```
   O configúrala desde el router (DHCP reservation).

## Solución de problemas

### No se puede conectar por SSH

```bash
# Verificar si la RPi está en la red
nmap -sn 192.168.80.0/24

# O desde Windows:
arp -a
```

### El bot no responde en Telegram

```bash
ssh rpi "docker-compose -f ~/english-agent/docker-compose.yml logs bot --tail 50"
```

### Docker no arranca

```bash
ssh rpi "sudo systemctl restart docker"
ssh rpi "docker-compose -f ~/english-agent/docker-compose.yml up -d"
```
