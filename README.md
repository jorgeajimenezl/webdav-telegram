# Telegram bot for manage your files via WebDAV

## Deploy

## Deploy (Debian)
Clone repository to the VM  
WARNING: Edit configuration in `src/config.yml`

### Install dependencies
```shell
~> sudo apt update
~> sudo apt install -y curl build-essential tcl libssl-dev libffi-dev python3-setuptools
~> sudo apt install -y python3.7 python3.7-dev python3.7-pip virtualenv
~> sudo apt install -y redis
```

### Start redis server
```shell
sudo systemctl start redis.service
```

### Create and activate virtual enviroment
```shell
~> virtualenv --python=python3 env
~> source ./env/bin/activate
```

### Install app dependencies
```shell
(env) ~> pip3 install -r requirements.txt
```


### Activate and start *webdav-telegram*
```shell
~> sudo cp ./src/webdav-telegram.service /etc/systemd/system/webdav-telegram.service
~> sudo systemctl start webdav-telegram
```

### Stop
```shell
~> sudo systemctl stop webdav-telegram
```