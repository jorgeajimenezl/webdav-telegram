FROM python:3.9

# Copy all files
RUN mkdir /app
COPY ./src /app
COPY ./requirements.txt /app
WORKDIR /app

# Write secrets
RUN sed -i 's/TELEGRAM_API_ID/$TELEGRAM_API_ID/g' /app/config.yml
RUN sed -i 's/TELEGRAM_API_HASH/$TELEGRAM_API_HASH/g' /app/config.yml
RUN sed -i 's/TELEGRAM_BOT_TOKEN/$TELEGRAM_BOT_TOKEN/g' /app/config.yml
RUN sed -i 's/REDIS_HOST/$REDIS_HOST/g' /app/config.yml

# Install requirements
RUN pip3 install -r /app/requirements.txt

# Run with -u $(id -u):$(id -g) to avoid file permission issues
# ENTRYPOINT ["python3", "app.py"]
CMD ["python3", "app.py"]