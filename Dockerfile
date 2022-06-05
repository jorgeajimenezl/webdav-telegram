FROM python:3.10-slim

# Install aria2
RUN apt-get update -y
RUN apt-get install -y git ffmpeg aria2

# Copy all files
RUN mkdir /app
COPY ./src /app
COPY ./requirements.txt /app
COPY ./run.sh /app
WORKDIR /app

# Install requirements
RUN pip3 install -r /app/requirements.txt

# Create download folder
RUN mkdir data

# Run with -u $(id -u):$(id -g) to avoid file permission issues
# ENTRYPOINT ["python3", "app.py"]
CMD ["/bin/sh", "run.sh"]