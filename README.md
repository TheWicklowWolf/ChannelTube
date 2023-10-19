![Build Status](https://github.com/TheWicklowWolf/ChannelTube/actions/workflows/main.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/thewicklowwolf/channeltube.svg)

<p align="center">

![full_logo](https://github.com/TheWicklowWolf/ChannelTube/assets/111055425/c07c2794-d537-407e-9f5b-83098244f6c7)



</p>

Web GUI for syncing and downloadinng a YouTube Channel.


## Run using docker-compose

```yaml
version: "2.1"
services:
  channeltube:
    image: thewicklowwolf/channeltube:latest
    container_name: channeltube
    volumes:
      - /config/channeltube:/channeltube/config
      - /data/media/channeltube:/channeltube/download
    ports:
      - 5000:5000
    restart: unless-stopped
```

---

<p align="center">


![image](https://github.com/TheWicklowWolf/ChannelTube/assets/111055425/b9ba0532-f4cf-4ed2-b5ac-8970c9d54848)



</p>


https://hub.docker.com/r/thewicklowwolf/channeltube
