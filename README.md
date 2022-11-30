# Telegram bot for manage your files via WebDAV

## Dependencies
+ Python (+3.9)
+ Redis

## Enviroment variables
- `TELEGRAM_API_ID`: Get from [Telegram](https://my.telegram.org)
- `TELEGRAM_API_HASH`: Get from [Telegram](https://my.telegram.org)
- `TELEGRAM_BOT_TOKEN`: Get from [Bot Father](https://t.me/BotFather)
- `REDIS_HOST`: Redis server in format `[username:password]@hostname[:port]`
- `ACL_USERS`: A list of users that will be used in ACL check in format `123456789,@jorgeajimenezl,@JimScope`
- `ACL_MODE`: ACL mode for users. Must be `whitelist` or `blacklist`. Default to `blacklist`

## Deploy to Heroku
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/jorgeajimenezl/webdav-telegram)

## Deploy with docker
```shell
~> sudo apt update
~> sudo apt install -y docker
~> sudo systemctl start docker.service
~> sudo docker build --tag webdav-telegram:latest 
~> sudo docker run -d webdav-telegram:latest
```

## Services
- [X] Mega.nz
- [X] Telegram
- [X] Torrent
- [X] Youtube (and a lot of videos webs support by [youtube-dl](https://github.com/ytdl-org/youtube-dl/))
- [X] Mediafire
- [ ] ZippyShare
- [X] Animeflv.net
- [X] Git repositories

## License
[MIT License](./LICENSE)

## Author
This program was developed by Jorge Alejandro Jiménez Luna <<jorgeajimenezl17@gmail.com>>
