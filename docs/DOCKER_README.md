# KBLI 2020 Docker Setup

## 🚀 Quick Start

### Prerequisites
- Docker Desktop installed
- Docker Compose installed

### Running the Application

1. **Build and start the container:**
   ```bash
   docker-compose up -d
   ```

2. **Access the application:**
   - From your computer: `http://localhost:3000`
   - From other devices on the same network: `http://YOUR_IP:3000`
     - Example: `http://192.168.1.29:3000`

3. **Find your IP address:**
   - Windows: `ipconfig` (look for IPv4 Address)
   - Linux/Mac: `ifconfig` or `ip addr`

### Stopping the Application

```bash
docker-compose down
```

### Viewing Logs

```bash
docker-compose logs -f
```

### Rebuilding After Changes

```bash
docker-compose down
docker-compose up -d --build
```

## 📝 Configuration

### Environment Variables

The application uses environment variables from `backend/.env`:
- `OPENAI_API_KEY` - For AI smart search
- `SUPABASE_URL` - Optional Supabase integration
- `SUPABASE_KEY` - Optional Supabase key

### Port Configuration

By default, the application runs on port 3000. To change this, edit `docker-compose.yml`:

```yaml
ports:
  - "YOUR_PORT:8000"  # Change YOUR_PORT to desired port
```

## 🔧 Troubleshooting

### Cannot access from other devices

1. Check Windows Firewall:
   - Allow port 3000 through Windows Firewall
   - Or temporarily disable firewall for testing

2. Verify Docker is running:
   ```bash
   docker ps
   ```

3. Check container logs:
   ```bash
   docker-compose logs
   ```

### Backend not responding

1. Ensure `kbli_parsed_fast.json` exists in the project root
2. Check backend logs for errors
3. Verify all dependencies are installed

## 📦 What's Included

- **Backend**: FastAPI Python application (port 8000 in container)
- **Frontend**: Static HTML/CSS/JS served by FastAPI
- **Data**: KBLI 2020 classification data

## 🌐 Network Access

The application is configured to:
- Bind to `0.0.0.0` inside the container (accessible from any network interface)
- Map to port 3000 on your host machine
- Allow CORS for cross-origin requests

## 🔐 Security Notes

For production deployment:
1. Remove the `.env` file from the repository
2. Use Docker secrets or environment variables
3. Configure proper firewall rules
4. Use HTTPS with a reverse proxy (nginx/traefik)
5. Remove development volume mounts from docker-compose.yml
