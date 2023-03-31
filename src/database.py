from urllib.parse import urlparse

from redis import Redis
import config
import utils


class Database(object):
    def __init__(self, db: int = 0, **kwargs):
        ret = urlparse(config.REDIS_HOST)

        self._redis = Redis(
            host=ret.hostname,
            port=ret.port if ret.port != 80 else 6379,
            username=ret.username,
            password=ret.password,
            db=db,
        )

    def add_user(self, id: int, force=False):
        if not self.contains_user(id) or force:
            data = {
                "server-uri": "",
                "username": "",
                "password": "",
                "split-size": 100,
                "upload-path": "/",
                "upload-parallel": "false",
                "streaming": "false",
                "use-libcurl": "false",
                "use-compression": "false",
                "file-password": "",
                "checksum": "true",
                "file-overwrite": "false",
                "is-admin": "false",
            }

            self.set_data(id, **data)
            return True

        return False

    def get_data(self, id: int):
        return {
            k.decode("utf-8"): v.decode("utf-8")
            for k, v in self._redis.hgetall(f"user:{id}").items()
        }

    def set_data(self, id: int, **kwargs):
        # print(kwargs)
        for k, v in kwargs.items():
            self._redis.hset(f"user:{id}", key=k, value=v)

    def contains_user(self, id: int):
        return self._redis.exists(f"user:{id}")

    def is_admin(self, id: int):
        data = self.get_data(id)
        return utils.get_bool(data["admin"])
