import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


async def main():
    scheduler.start()

    scheduler.add_job(print, args=("hello world",))

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Stoped!!! ...")


if __name__ == "__main__":
    asyncio.run(main())
