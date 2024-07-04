import logging
import os
import time
import datetime
import threading
import re
from flask import Flask, render_template
from flask_socketio import SocketIO
import yt_dlp
import json
from plexapi.server import PlexServer
import requests
from mutagen.mp4 import MP4


class DataHandler:
    def __init__(self):
        self.config_folder = "config"
        self.download_folder = "downloads"
        self.media_server_addresses = "Plex: http://192.168.1.2:32400, Jellyfin: http://192.168.1.2:8096"
        self.media_server_tokens = "Plex: abc, Jellyfin: xyz"
        self.media_server_library_name = "YouTube"
        self.media_server_scan_req_flag = False
        self.video_format_id = os.environ.get("video_format_id", "137")
        self.audio_format_id = os.environ.get("audio_format_id", "140")

        if not os.path.exists(self.config_folder):
            os.makedirs(self.config_folder)
        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)

        self.sync_start_times = [0]
        self.settings_config_file = os.path.join(self.config_folder, "settings_config.json")

        self.req_channel_list = []
        self.channel_list_config_file = os.path.join(self.config_folder, "channel_list.json")

        if os.path.exists(self.settings_config_file):
            self.load_from_file()

        if os.path.exists(self.channel_list_config_file):
            self.load_channel_list_from_file()

        full_cookies_path = os.path.join(self.config_folder, "cookies.txt")
        self.cookies_path = full_cookies_path if os.path.exists(full_cookies_path) else None

        task_thread = threading.Thread(target=self.schedule_checker)
        task_thread.daemon = True
        task_thread.start()

    def load_from_file(self):
        try:
            with open(self.settings_config_file, "r") as json_file:
                ret = json.load(json_file)
            self.sync_start_times = ret["sync_start_times"]
            self.media_server_addresses = ret["media_server_addresses"]
            self.media_server_tokens = ret["media_server_tokens"]
            self.media_server_library_name = ret["media_server_library_name"]

        except Exception as e:
            logger.error(f"Error Loading Config: {str(e)}")

    def save_to_file(self):
        try:
            with open(self.settings_config_file, "w") as json_file:
                json.dump(
                    {
                        "sync_start_times": self.sync_start_times,
                        "media_server_addresses": self.media_server_addresses,
                        "media_server_tokens": self.media_server_tokens,
                        "media_server_library_name": self.media_server_library_name,
                    },
                    json_file,
                    indent=4,
                )

        except Exception as e:
            logger.error(f"Error Saving Config: {str(e)}")

    def load_channel_list_from_file(self):
        try:
            with open(self.channel_list_config_file, "r") as json_file:
                self.req_channel_list = json.load(json_file)

        except Exception as e:
            logger.error(f"Error Loading Channels: {str(e)}")

    def save_channel_list_to_file(self):
        try:
            with open(self.channel_list_config_file, "w") as json_file:
                json.dump(self.req_channel_list, json_file, indent=4)

        except Exception as e:
            logger.error(f"Error Saving Channels: {str(e)}")

    def schedule_checker(self):
        while True:
            current_time = datetime.datetime.now().time()
            within_sync_window = any(datetime.time(t, 0, 0) <= current_time <= datetime.time(t, 59, 59) for t in self.sync_start_times)

            if within_sync_window:
                logger.warning(f"Time to Start Sync - as in a time window {str(self.sync_start_times)}")
                self.master_queue()
                logger.warning("Big sleep for 1 Hour - Sync Complete")
                time.sleep(3600)
                logger.warning(f"Checking every 60 seconds as not in sync time window {str(self.sync_start_times)}")
            else:
                time.sleep(60)

    def get_list_of_videos(self, channel):
        channel_name = channel["Name"]

        days_to_retrieve = channel["DL_Days"]
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "force_generic_extractor": True,
        }
        ydl = yt_dlp.YoutubeDL(ydl_opts)

        try:
            channel_link = channel["Link"]
            channel_info = ydl.extract_info(channel_link, download=False)
            channel_id = channel_info["channel_id"]
            channel_title = channel_info["title"]

            if not channel_id:
                raise Exception("No Channel ID")
            if not channel_title:
                raise Exception("No Channel Title")

        except Exception as e:
            logger.error(f"Error using Channel Link: {str(e)}")
            logger.error("Trying to search for the Channel manually...")
            ret = ydl.extract_info(f"ytsearch:{channel_name} channel", download=False)
            channel_id = ret["entries"][0]["channel_id"]
            channel_title = ret["entries"][0]["uploader"]

        logger.warning(f"Channel Title: {channel_title} and Channel ID: {channel_id}")
        uploads_playlist_url = f"https://www.youtube.com/playlist?list=UU{channel_id[2:]}"
        playlist = ydl.extract_info(uploads_playlist_url, download=False)

        today = datetime.datetime.now()
        last_date = today - datetime.timedelta(days=days_to_retrieve)

        video_list = []
        for video in playlist["entries"]:
            try:
                video_title = video["title"]
                video_link_in_playlist = video["url"]
                logger.warning(f"{video_title} -> {video_link_in_playlist}")

                duration = video["duration"]
                channel = video["channel"].strip()
                actual_video = ydl.extract_info(video_link_in_playlist, download=False)

                video_actual_link = actual_video["webpage_url"]
                video_date_raw = actual_video["upload_date"]
                video_id = actual_video["id"]
                video_date = datetime.datetime.strptime(video_date_raw, "%Y%m%d")

                if video_date >= last_date:
                    if duration > 60:
                        video_list.append({"title": video_title, "upload_date": video_date, "link": video_actual_link, "id": video_id, "channel": channel})
                        logger.warning(f"Added Video to List: {video_title}")
                    else:
                        logger.warning(f"Ignoring Short Video: {video_title} - {video_actual_link}")
                else:
                    logger.warning("No more Videos in date range")
                    break

            except Exception as e:
                logger.error(f"Error extracting details of {video_title}: {str(e)}")

        return video_list

    def check_and_download(self, video_list, channel):
        try:
            channel_folder = channel["Name"]
            channel_folder_path = os.path.join(self.download_folder, channel_folder)

            if not os.path.exists(channel_folder_path):
                os.makedirs(channel_folder_path)

            for vid in video_list:
                if not self.is_video_in_folder(vid, channel_folder_path):
                    logger.warning(f'Starting Download: {vid["title"]}')
                    self.download_video(vid, channel_folder_path)

        except Exception as e:
            logger.error(f"Error checking download {str(e)}")

    def is_video_in_folder(self, vid, channel_folder_path):
        try:
            raw_directory_list = os.listdir(channel_folder_path)

            if f'{self.string_cleaner(vid["title"])}.mp4' in raw_directory_list:
                logger.warning(f'Video File Already in folder: {vid["title"]}')
                return True

            for filename in raw_directory_list:
                file_path = os.path.join(channel_folder_path, filename)
                if os.path.isfile(file_path):
                    try:
                        mp4_file = MP4(file_path)
                        embedded_video_id = mp4_file.get("\xa9cmt", [None])[0]
                        if embedded_video_id == vid["id"]:
                            logger.warning(f'Video ID for: {vid["title"]} found embedded in: {file_path}')
                            return True

                    except Exception as e:
                        logger.error(f"No Video ID present or cannot read it from metadata: {e}")
            return False

        except Exception as e:
            logger.error(f"Error checking if video is in folder: {str(e)}")
            return False

    def cleanup_old_files(self, channel):
        channel_folder = channel["Name"]
        days_to_keep = channel["Keep_Days"]

        channel_folder_path = os.path.join(self.download_folder, channel_folder)
        raw_directory_list = os.listdir(channel_folder_path)

        current_datetime = datetime.datetime.now()

        try:
            channel["Video_Count"] = 0
            for filename in raw_directory_list:
                file_path = os.path.join(channel_folder_path, filename)

                if os.path.isfile(file_path) and filename.lower().endswith(".mp4"):
                    try:
                        mp4_file = MP4(file_path)
                        mp4_created_timestamp = mp4_file.get("\xa9day", [None])[0]
                        if mp4_created_timestamp:
                            file_mtime = datetime.datetime.strptime(mp4_created_timestamp, "%Y-%m-%d %H:%M:%S")
                            logger.warning(f"Extracted datetime from metadata: {file_mtime}")
                        else:
                            raise Exception("No timestamp found")

                    except Exception as e:
                        logger.error(f"Error extracting datetime from metadata: {e}")
                        file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                        logger.error(f"Using Modified timestamp instead.... {file_mtime}")

                    age = current_datetime - file_mtime

                    if age > datetime.timedelta(days=days_to_keep):
                        os.remove(file_path)
                        logger.warning(f"Deleted: {filename} as it is {age.days} days old")
                        if self.media_server_scan_req_flag == False:
                            self.media_server_scan_req_flag = True
                    else:
                        channel["Video_Count"] += 1
                        logger.warning(f"File: {filename} is {age.days} days old, keeping file as not over {days_to_keep} days")

        except Exception as e:
            logger.error(f"Error Cleaning Old Files: {str(e)}")

    def download_video(self, video, channel_folder_path):
        if self.media_server_scan_req_flag == False:
            self.media_server_scan_req_flag = True
        try:
            link = video["link"]
            title = self.string_cleaner(video["title"])
            full_file_path = os.path.join(channel_folder_path, f"{title}.mp4")
            ydl_opts = {
                "ffmpeg_location": "/usr/bin/ffmpeg",
                "format": f"{self.video_format_id}+{self.audio_format_id}",
                "outtmpl": full_file_path,
                "quiet": True,
                "writethumbnail": True,
                "progress_hooks": [self.progress_callback],
                "merge_output_format": "mp4",
                "postprocessors": [
                    {"key": "EmbedThumbnail"},
                    {"key": "SponsorBlock", "categories": ["sponsor"]},
                    {"key": "ModifyChapters", "remove_sponsor_segments": ["sponsor"]},
                    {"key": "FFmpegMetadata"},
                ],
            }
            if self.cookies_path:
                ydl_opts["cookiefile"] = self.cookies_path

            yt_downloader = yt_dlp.YoutubeDL(ydl_opts)
            logger.warning(f"yt_dl Start: {link}")

            yt_downloader.download([link])
            logger.warning(f"yt_dl Complete: {link}")

            self.add_extra_metadata(full_file_path, video)

        except Exception as e:
            logger.error(f"Error downloading video: {link}. Error message: {e}")

    def progress_callback(self, d):
        if d["status"] == "finished":
            logger.warning("Download complete")

        elif d["status"] == "downloading":
            logger.warning(f'Downloaded {d["_percent_str"]} of {d["_total_bytes_str"]} at {d["_speed_str"]}')

    def add_extra_metadata(self, file_path, video):
        try:
            current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mp4_file = MP4(file_path)
            mp4_file["\xa9day"] = current_datetime
            mp4_file["\xa9cmt"] = video["id"]
            mp4_file["\xa9nam"] = video["title"]
            mp4_file["\xa9ART"] = video["channel"]
            mp4_file["\xa9gen"] = video["channel"]
            mp4_file.save()
            logger.warning(f"Added datetime {current_datetime} to metadata to {file_path}")

        except Exception as e:
            logger.error(f"Error adding metadata to {file_path}: {e}")

    def master_queue(self):
        try:
            self.media_server_scan_req_flag = False
            logger.warning("Sync Task started...")
            for channel in self.req_channel_list:
                logging.warning(f'Looking for channel Videos on YouTube:  {channel["Name"]}')
                vid_list = self.get_list_of_videos(channel)

                logging.warning(f'Starting Downloading List: {channel["Name"]}')
                self.check_and_download(vid_list, channel)
                logging.warning(f'Finished Downloading List: {channel["Name"]}')

                logging.warning(f'Start Clearing Files: {channel["Name"]}')
                self.cleanup_old_files(channel)
                logging.warning(f'Finished Clearing Files: {channel["Name"]}')

                channel["Last_Synced"] = datetime.datetime.now().strftime("%d-%m-%y %H:%M:%S")

            self.save_channel_list_to_file()
            data = {"Channel_List": self.req_channel_list}
            socketio.emit("Update", data)

            if self.media_server_scan_req_flag == True and self.media_server_tokens:
                self.sync_media_servers()
            else:
                logger.warning("Media Server Sync not required")

        except Exception as e:
            logger.error(f"Error in Queue: {str(e)}")
            logger.warning("Finished: Incomplete")

        else:
            logger.warning("Finished: Complete")

    def add_channel(self, channel):
        self.req_channel_list.extend(channel)

    def sync_media_servers(self):
        media_servers = self.convert_string_to_dict(self.media_server_addresses)
        media_tokens = self.convert_string_to_dict(self.media_server_tokens)
        if "Plex" in media_servers and "Plex" in media_tokens:
            try:
                token = media_tokens.get("Plex")
                address = media_servers.get("Plex")
                logger.warning("Attempting Plex Sync")
                media_server_server = PlexServer(address, token)
                library_section = media_server_server.library.section(self.media_server_library_name)
                library_section.update()
                logger.warning(f"Plex Library scan for '{self.media_server_library_name}' started.")
            except Exception as e:
                logger.warning(f"Plex Library scan failed: {str(e)}")
        if "Jellyfin" in media_servers and "Jellyfin" in media_tokens:
            try:
                token = media_tokens.get("Jellyfin")
                address = media_servers.get("Jellyfin")
                logger.warning("Attempting Jellyfin Sync")
                url = f"{address}/Library/Refresh?api_key={token}"
                response = requests.post(url)
                if response.status_code == 204:
                    logger.warning("Jellyfin Library refresh request successful.")
                else:
                    logger.warning(f"Jellyfin Error: {response.status_code}, {response.text}")
            except Exception as e:
                logger.warning(f"Jellyfin Library scan failed: {str(e)}")

    def string_cleaner(self, input_string):
        if isinstance(input_string, str):
            raw_string = re.sub(r'[\/:*?"<>|]', " ", input_string)
            temp_string = re.sub(r"\s+", " ", raw_string)
            cleaned_string = temp_string.strip()
            return cleaned_string

        elif isinstance(input_string, list):
            cleaned_strings = []
            for string in input_string:
                file_name_without_extension, file_extension = os.path.splitext(string)
                raw_string = re.sub(r'[\/:*?"<>|]', " ", file_name_without_extension)
                temp_string = re.sub(r"\s+", " ", raw_string)
                cleaned_string = temp_string.strip()
                cleaned_strings.append(cleaned_string)
            return cleaned_strings

    def convert_string_to_dict(self, raw_string):
        result = {}
        if not raw_string:
            return result

        pairs = raw_string.split(",")
        for pair in pairs:
            key_value = pair.split(":", 1)
            if len(key_value) == 2:
                key, value = key_value
                result[key.strip()] = value.strip()

        return result


app = Flask(__name__)
app.secret_key = "secret_key"
socketio = SocketIO(app)

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger()

data_handler = DataHandler()


@app.route("/")
def home():
    return render_template("base.html")


@socketio.on("connect")
def connection():
    data = {"Channel_List": data_handler.req_channel_list}
    socketio.emit("Update", data)


@socketio.on("loadSettings")
def loadSettings():
    data = {
        "sync_start_times": data_handler.sync_start_times,
        "media_server_addresses": data_handler.media_server_addresses,
        "media_server_tokens": data_handler.media_server_tokens,
        "media_server_library_name": data_handler.media_server_library_name,
    }
    socketio.emit("settingsLoaded", data)


@socketio.on("save_channel_settings")
def save_channel_settings(data):
    channel_to_be_saved = data["channel"]
    channel_name = channel_to_be_saved["Name"]
    for channel in data_handler.req_channel_list:
        if channel["Name"] == channel_name:
            channel.update(channel_to_be_saved)
            break
    else:
        data_handler.req_channel_list.append(channel_to_be_saved)
    data_handler.save_channel_list_to_file()


@socketio.on("updateSettings")
def updateSettings(data):
    data_handler.media_server_addresses = data["media_server_addresses"]
    data_handler.media_server_tokens = data["media_server_tokens"]
    data_handler.media_server_library_name = data["media_server_library_name"]
    try:
        if data["sync_start_times"] == "":
            raise Exception("No Time Entered, defaulting to 00:00")
        raw_sync_start_times = [int(re.sub(r"\D", "", start_time.strip())) for start_time in data["sync_start_times"].split(",")]
        temp_sync_start_times = [0 if x < 0 or x > 23 else x for x in raw_sync_start_times]
        cleaned_sync_start_times = sorted(list(set(temp_sync_start_times)))
        data_handler.sync_start_times = cleaned_sync_start_times

    except Exception as e:
        logger.error(f"Error Updating settings: {str(e)}")
        data_handler.sync_start_times = [0]
    finally:
        logger.warning(f"Sync Times: {str(data_handler.sync_start_times)}")
    data_handler.save_to_file()


@socketio.on("add_channel")
def add_channel(data):
    data_handler.add_channel(data)


@socketio.on("save_channels")
def save_channels(data):
    data_handler.req_channel_list = data["Saved_Channel_List"]
    data_handler.save_channel_list_to_file()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
