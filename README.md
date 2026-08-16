# Proxy telegram checker


## Usefull commands:

```bash
make help
```

## Install & Update

### Install service

```bash
git clone git@github.com:Balshgit/telegram_proxy_checker.git
cd telegram_proxy_checker
sudo rsync -a --delete --progress ./* /opt/gpt_chat_bot/ --exclude .git
cd /opt/telegram_proxy_checker
sudo cp ./envs/.env.template ./envs/.env
sudo cp ./telegram_proxy_checker.service /etc/systemd/system
sudo systemctl enable telegram_proxy_checker.service
sudo systemctl start telegram_proxy_checker.service
```

### Update service

```bash
git pull origin main
sudo rsync -a --delete --progress ./* /opt/telegram_proxy_checker/ --exclude .git
cd /opt/telegram_proxy_checker/
make build-images
sudo systemctl stop telegram_proxy_checker.service
sudo systemctl start telegram_proxy_checker.service
```