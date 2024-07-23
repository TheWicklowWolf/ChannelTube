![Build Status](https://github.com/TheWicklowWolf/ChannelTube/actions/workflows/main.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/thewicklowwolf/channeltube.svg)


![full_logo](https://github.com/TheWicklowWolf/ChannelTube/assets/111055425/c07c2794-d537-407e-9f5b-83098244f6c7)


ChannelTube is a tool for synchronizing and fetching content from YouTube channels using yt-dlp.


## Run using docker-compose

```yaml
services:
  channeltube:
    image: thewicklowwolf/channeltube:latest
    container_name: channeltube
    volumes:
      - /path/to/config:/channeltube/config
      - /data/media/channeltube:/channeltube/downloads
      - /etc/localtime:/etc/localtime:ro
    ports:
      - 5000:5000
    restart: unless-stopped
```

## Configuration via environment variables

Certain values can be set via environment variables:

* __video_format_id__: The ID for the video format. Defaults to `137`.
* __audio_format_id__: The ID for the audio format. Defaults to `140`.
* __defer_hours__: Time to defer in hours. Defaults to `0`.

> See [https://github.com/yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp)
> 
> ![yt-dlp-formats](https://github.com/user-attachments/assets/e03b9dd3-028f-4c72-b822-06aa1d440cea)


## Sync Schedule

Use a comma-separated list of hours to search for new videos (e.g., 2, 20 will initiate a video search at 2 AM and 8 PM).

## Media Server Integration (optional)

A media server library scan can be triggered when new content is retrieved.

For Plex, use: `Plex: http://192.168.1.2:32400`  
For Jellyfin, use: `Jellyfin: http://192.168.1.2:8096`  
To use both, enter: `Plex: http://192.168.1.2:32400, Jellyfin: http://192.168.1.2:8096`  
The same format applies for the tokens.  

The **Media Server Library Name** refers to the name of the library where the videos are stored.  

To disable this feature:
- Leave **Media Server Addresses**, **Media Server Tokens** and **Media Server Library Name** blank.  

## Cookies (optional)
To utilize a cookies file with yt-dlp, follow these steps:

* Generate Cookies File: Open your web browser and use a suitable extension (e.g. cookies.txt for Firefox) to extract cookies for a user on YT.

* Save Cookies File: Save the obtained cookies into a file named `cookies.txt` and put it into the config folder.


---


![image](https://github.com/TheWicklowWolf/ChannelTube/assets/111055425/b9ba0532-f4cf-4ed2-b5ac-8970c9d54848)


---


![ChannelTubeDark](https://github.com/TheWicklowWolf/ChannelTube/assets/111055425/1e09a757-55cd-42bd-b3cb-aadd7152bd2e)

---


https://hub.docker.com/r/thewicklowwolf/channeltube
