FROM python:3.14-alpine

# Set build arguments
ARG RELEASE_VERSION
ENV RELEASE_VERSION=${RELEASE_VERSION}

# Install ffmpeg and su-exec
RUN apk update && apk add --no-cache ffmpeg su-exec deno

# Create directories and set permissions
COPY . /channeltube
WORKDIR /channeltube

# Install requirements
RUN pip install --no-cache-dir -r requirements.txt

# Make the script executable
RUN chmod +x thewicklowwolf-init.sh

# Expose port
EXPOSE 5000

# Start the app
ENTRYPOINT ["./thewicklowwolf-init.sh"]


