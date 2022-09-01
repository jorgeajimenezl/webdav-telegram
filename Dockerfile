FROM python:3.10 AS BUILD

# Build aiomega module
RUN apt-get update -y
RUN apt-get install -y git \
    make g++ gcc automake autoconf libtool \
    libcurl4-openssl-dev libsodium-dev libssl-dev \
    libcrypto++-dev libc-ares-dev  swig \
    libpthread-stubs0-dev zlib1g-dev libsqlite3-dev \
    python3-distutils

RUN python -m ensurepip --default-pip
RUN pip install build setuptools wheel

RUN git clone --recursive https://github.com/jorgeajimenezl/aiomega.git
WORKDIR /aiomega
RUN sh configure.sh
RUN python -m build --wheel --no-isolation

FROM python:3.10 AS PRODUCTION

RUN apt-get update -y
RUN apt-get install -y git ffmpeg aria2 \
    libcurl4-openssl-dev libsodium-dev libssl-dev \
    libcrypto++-dev libc-ares-dev libpthread-stubs0-dev \
    zlib1g-dev libsqlite3-dev

# Copy all files
RUN mkdir /app
COPY ./src /app
COPY ./requirements.txt /app
COPY --from=BUILD /aiomega/dist/*.whl /app
COPY ./run.sh /app
COPY ./aria2c.conf /app
WORKDIR /app

# Install requirements
RUN pip3 install -r /app/requirements.txt
RUN pip3 install /app/*.whl

# Create download folder
RUN mkdir data

# Run with -u $(id -u):$(id -g) to avoid file permission issues
# ENTRYPOINT ["python3", "app.py"]
CMD ["/bin/sh", "run.sh"]
