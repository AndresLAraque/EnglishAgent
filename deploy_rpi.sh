#!/bin/bash
set -e

RPI_USER="andrespi"
RPI_HOST="192.168.80.20"
RPI_DIR="/home/$RPI_USER/english-agent"
SSH_KEY="$HOME/.ssh/rpi_englishagent"
LOCAL_PROJECT="$HOME/Documents/EnglishAgent"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

if [ ! -f "$SSH_KEY" ]; then
    err "SSH key not found at $SSH_KEY"
    err "Run: ssh-keygen -t ed25519 -f $SSH_KEY -N ''"
    exit 1
fi

log "Checking connectivity to $RPI_USER@$RPI_HOST..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "echo 'connected'" 2>/dev/null; then
    warn "Cannot connect with key. Attempting password-based copy..."
    ssh-copy-id -i "$SSH_KEY.pub" "$RPI_USER@$RPI_HOST" 2>/dev/null || {
        warn "ssh-copy-id failed. Trying manual method..."
        cat "$SSH_KEY.pub" | ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no "$RPI_USER@$RPI_HOST" "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys" 2>/dev/null || {
            err "Could not copy SSH key. Make sure the RPi is reachable and password is correct."
            err "Commands to try manually:"
            echo "  ssh-copy-id -i $SSH_KEY.pub $RPI_USER@$RPI_HOST"
            echo "  Or if ssh-copy-id is not available on Windows:"
            echo "  type C:\\Users\\andres\\.ssh\\rpi_englishagent.pub | ssh $RPI_USER@$RPI_HOST \"mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys\""
            exit 1
        }
    }
    log "SSH key copied to RPi"
fi

log "Testing key-based SSH..."
ssh -o BatchMode=yes -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "echo 'SSH OK'" || {
    err "SSH key authentication failed after copy."
    exit 1
}

log "Checking RPi architecture..."
ARCH=$(ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "uname -m")
log "Architecture: $ARCH"

if [ "$ARCH" != "aarch64" ] && [ "$ARCH" != "armv7l" ]; then
    warn "Unexpected architecture: $ARCH. Expected aarch64 or armv7l for Raspberry Pi."
fi

log "Checking/Installing Docker on RPi..."
ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "bash -c '
    if ! command -v docker &>/dev/null; then
        echo \"Installing Docker...\"
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker \$USER
        echo \"Docker installed. You may need to log out and back in.\"
    else
        echo \"Docker already installed: \$(docker --version)\"
    fi
    if ! command -v docker compose &>/dev/null; then
        echo \"Installing docker-compose plugin...\"
        sudo apt-get update && sudo apt-get install -y docker-compose-plugin
    else
        echo \"docker compose already installed\"
    fi
'"

log "Creating project directory on RPi..."
ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "mkdir -p $RPI_DIR"

log "Copying project files to RPi..."
rsync -avz --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='*.log' \
    --exclude='.env' \
    -e "ssh -i $SSH_KEY" \
    "$LOCAL_PROJECT/" "$RPI_USER@$RPI_HOST:$RPI_DIR/"

log "Copying .env file..."
scp -i "$SSH_KEY" "$LOCAL_PROJECT/.env" "$RPI_USER@$RPI_HOST:$RPI_DIR/.env"

log "Pulling Ollama model on RPi..."
ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "cd $RPI_DIR && docker-compose up -d ollama && sleep 3 && docker exec english-ollama ollama pull qwen2.5:0.5b" || {
    warn "Could not pull Ollama model. You can do it later with:"
    echo "  ssh -i $SSH_KEY $RPI_USER@$RPI_HOST"
    echo "  cd $RPI_DIR && docker exec english-ollama ollama pull qwen2.5:0.5b"
}

log "Starting bot on RPi..."
ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "cd $RPI_DIR && docker-compose up -d"

sleep 3
log "Checking container status..."
ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "cd $RPI_DIR && docker compose ps"

log "Setting up systemd for auto-start on boot..."
ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "bash -c '
cat <<EOF | sudo tee /etc/systemd/system/english-agent.service > /dev/null
[Unit]
Description=English Agent Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$RPI_DIR
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
StandardOutput=journal

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable english-agent.service
sudo systemctl start english-agent.service
'"

log "Checking service status..."
ssh -i "$SSH_KEY" "$RPI_USER@$RPI_HOST" "sudo systemctl status english-agent.service --no-pager | head -10"

echo ""
log "======================================"
log "  Deployment complete!"
log "======================================"
echo ""
log "Bot is running on RPi at $RPI_HOST"
log "Connect: ssh -i $SSH_KEY $RPI_USER@$RPI_HOST"
log "View logs: ssh -i $SSH_KEY $RPI_USER@$RPI_HOST \"docker compose -f $RPI_DIR/docker-compose.yml logs -f\""
log "Stop bot:  ssh -i $SSH_KEY $RPI_USER@$RPI_HOST \"docker compose -f $RPI_DIR/docker-compose.yml down\""
log "Restart:   ssh -i $SSH_KEY $RPI_USER@$RPI_HOST \"docker compose -f $RPI_DIR/docker-compose.yml restart\""
echo ""
log "Telegram bot should be responding now."
