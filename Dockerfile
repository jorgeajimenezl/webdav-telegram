FROM archlinux

# Install dependencies
RUN pacman -Syyu --noconfirm
RUN pacman -S python base-devel aria2 git --noconfirm

# Copy all files
RUN mkdir /app
COPY ./src /app
COPY ./requirements.txt /app
COPY ./run.sh /app
WORKDIR /app

# Install requirements
RUN pip3 install -r /app/requirements.txt

# Create torrent download folder
RUN mkdir torrent_data

# Run with -u $(id -u):$(id -g) to avoid file permission issues
# ENTRYPOINT ["python3", "app.py"]
CMD ["/bin/sh", "run.sh"]