![Build Status](https://github.com/TheWicklowWolf/ChannelTube/actions/workflows/main.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/thewicklowwolf/channeltube.svg)

<p align="center">

![full_logo](https://github.com/TheWicklowWolf/ChannelTube/assets/111055425/c07c2794-d537-407e-9f5b-83098244f6c7)



</p>

Web GUI for synchronising and fetching content from a YouTube channel.


## Run using docker-compose

```yaml
version: "2.1"
services:
  channeltube:
    image: thewicklowwolf/channeltube:latest
    container_name: channeltube
    volumes:
      - /config/channeltube:/channeltube/config
      - /data/media/channeltube:/channeltube/downloads
      - /etc/localtime:/etc/localtime:ro
    ports:
      - 5000:5000
    restart: unless-stopped
```

---


![image](https://github.com/TheWicklowWolf/ChannelTube/assets/111055425/b9ba0532-f4cf-4ed2-b5ac-8970c9d54848)


---


![ChannelTubeDark](https://github.com/TheWicklowWolf/ChannelTube/assets/111055425/1e09a757-55cd-42bd-b3cb-aadd7152bd2e)


https://hub.docker.com/r/thewicklowwolf/channeltube
