FROM python:3.9

# Copy all files
RUN mkdir /app
COPY ./src /app
COPY ./requirements.txt /app
WORKDIR /app

# Install requirements
RUN pip3 install -r /app/requirements.txt

# Run with -u $(id -u):$(id -g) to avoid file permission issues
# ENTRYPOINT ["python3", "app.py"]
CMD ["python3", "app.py"]