FROM python:3.11
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY . /channeltube
WORKDIR /channeltube
RUN pip install -r requirements.txt
EXPOSE 5000
CMD ["gunicorn","src.ChannelTube:app", "-c", "gunicorn_config.py"]