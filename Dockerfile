FROM python:3.11-alpine
# Create User
ARG UID=1000
ARG GID=1000
RUN addgroup -g $GID general_user && \
    adduser -D -u $UID -G general_user -s /bin/sh general_user
# Install ffmpeg
RUN apk update && apk add --no-cache ffmpeg
# Create directories and set permissions
COPY . /channeltube
WORKDIR /channeltube
RUN mkdir -p /channeltube/downloads
RUN chown -R $UID:$GID /channeltube
RUN chmod -R 777 /channeltube/downloads
# Install requirements and run code as general_user
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 5000
USER general_user
CMD ["gunicorn","src.ChannelTube:app", "-c", "gunicorn_config.py"]