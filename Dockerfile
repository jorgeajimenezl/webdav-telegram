FROM python:3.9

# Install aria2
RUN apt-get update -y
RUN apt-get install -y aria2

# Copy all files
RUN mkdir /app
COPY ./src /app
COPY ./requirements.txt /app
WORKDIR /app

# Install requirements
RUN pip3 install -r /app/requirements.txt

# Run aria2 daemon
RUN mkdir torrent_data
RUN aria2c --enable-rpc --daemon --dir=/app/torrent_data

# Run with -u $(id -u):$(id -g) to avoid file permission issues
# ENTRYPOINT ["python3", "app.py"]
CMD ["python3", "app.py"]