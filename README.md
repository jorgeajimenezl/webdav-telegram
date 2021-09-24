# Telegram bot for manage your files via WebDAV

## Dependencies
+ Python (+3.7)
+ Redis

## Enviroment variables
- `TELEGRAM_API_ID`: Get from [Telegram](https://my.telegram.org)
- `TELEGRAM_API_HASH`: Get from [Telegram](https://my.telegram.org)
- `TELEGRAM_BOT_TOKEN`: Get from [Bot Father](https://t.me/BotFather)
- `REDIS_HOST`: Redis server in format `[username:password]@hostname[:port]`

## Deploy to Heroku
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/jorgeajimenezl/webdav-telegram)

## Deploy to VPS

### Install dependencies
```shell
~> sudo apt update
~> sudo apt install -y curl build-essential tcl libssl-dev libffi-dev python3-setuptools
~> sudo apt install -y python3.7 python3.7-dev python3.7-pip virtualenv
~> sudo apt install -y redis
~> sudo systemctl start redis.service
```

### Activate
```shell
~> cd webdav-telegram
~> sudo cp webdav-telegram.service /etc/systemd/system/
~> virtualenv --python=python3 env
~> source ./env/bin/activate
(env) ~> pip3 install -r requirements.txt
```

### Start
```shell
# Start 
~> sudo systemctl start webdav-telegram.service
# Stop
~> sudo systemctl stop webdav-telegram.service
```

## License
[MIT License](./LICENSE)

## Author
This program was deverloped by Jorge Jimenez <<jorgeajimenezl17@gmail.com>>
