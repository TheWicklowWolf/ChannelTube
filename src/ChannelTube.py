import logging
import os
import sys
import time
import datetime
import threading
import re
from flask import Flask, render_template
from flask_socketio import SocketIO
import youtubesearchpython as youtube
import yt_dlp
import json
from plexapi.server import PlexServer


class Data_Handler:
    def __init__(self):
        self.config_folder = "config"
        self.download_folder = "download"
        self.plex_address = "http://192.168.1.2:32400"
        self.plex_token = ""
        self.plex_library_name = "YouTube"
        self.plex_scan_req_flag = False

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

        task_thread = threading.Thread(target=self.schedule_checker)
        task_thread.daemon = True
        task_thread.start()

    def load_from_file(self):
        try:
            with open(self.settings_config_file, "r") as json_file:
                ret = json.load(json_file)
            self.sync_start_times = ret["sync_start_times"]
            self.plex_address = ret["plex_address"]
            self.plex_token = ret["plex_token"]
            self.plex_library_name = ret["plex_library_name"]

        except Exception as e:
            logger.error("Error Loading Config: " + str(e))

    def save_to_file(self):
        try:
            with open(self.settings_config_file, "w") as json_file:
                json.dump(
                    {
                        "sync_start_times": self.sync_start_times,
                        "plex_address": self.plex_address,
                        "plex_token": self.plex_token,
                        "plex_library_name": self.plex_library_name,
                    },
                    json_file,
                    indent=4,
                )

        except Exception as e:
            logger.error("Error Saving Config: " + str(e))

    def load_channel_list_from_file(self):
        try:
            with open(self.channel_list_config_file, "r") as json_file:
                self.req_channel_list = json.load(json_file)

        except Exception as e:
            logger.error("Error Loading Channels: " + str(e))

    def save_channel_list_to_file(self):
        try:
            with open(self.channel_list_config_file, "w") as json_file:
                json.dump(self.req_channel_list, json_file, indent=4)

        except Exception as e:
            logger.error("Error Saving Channels: " + str(e))

    def schedule_checker(self):
        while True:
            current_time = datetime.datetime.now().time()
            within_sync_window = any(datetime.time(t, 0, 0) <= current_time <= datetime.time(t, 59, 59) for t in self.sync_start_times)

            if within_sync_window:
                logger.warning("Time to Start Sync")
                self.master_queue()
                logger.warning("Big sleep for 1 Hour - Sync Done")
                time.sleep(3600)
            else:
                logger.warning("Small sleep as not in sync time window " + str(self.sync_start_times) + " - checking again in 60 seconds")
                time.sleep(60)

    def get_list_of_videos(self, channel):
        channel_name = channel["Name"]
        days_to_retrieve = channel["DL_Days"]

        channelsSearch = youtube.ChannelsSearch(channel_name)
        ret = channelsSearch.result()

        channel_id = ret["result"][0]["id"]
        channel_title = ret["result"][0]["title"]
        logger.warning("Channel Title: " + channel_title)

        channel_playlist_url = youtube.playlist_from_channel_id(channel_id)
        playlist = youtube.Playlist(channel_playlist_url)

        today = datetime.datetime.now()
        last_date = today - datetime.timedelta(days=days_to_retrieve)

        video_list = []
        ok_to_continue_search = True

        while ok_to_continue_search:
            for video in playlist.videos:
                video_title = video["title"]
                video_link_in_playlist = video["link"]
                logger.warning(video_title + " : " + video_link_in_playlist)

                duration = self.get_seconds_from_duration(video["duration"])
                actual_video = youtube.Video.get(video_link_in_playlist, mode=youtube.ResultMode.json, get_upload_date=True)

                video_actual_link = actual_video["link"]
                video_date_raw = actual_video["uploadDate"]
                video_date = datetime.datetime.fromisoformat(video_date_raw).replace(tzinfo=None)

                if video_date >= last_date:
                    if duration > 60:
                        video_list.append({"title": video_title, "upload_date": video_date, "link": video_actual_link})
                        logger.warning("Added Video to List: " + video_title)
                    else:
                        logger.warning("Ignoring Short Video: " + video_title + " " + video_actual_link)
                else:
                    ok_to_continue_search = False
                    logger.warning("No more Videos in date range")
                    break
            else:
                if playlist.hasMoreVideos:
                    logger.warning("Getting more Videos")
                    playlist.getNextVideos()
                else:
                    ok_to_continue_search = False

        return video_list

    def check_and_download(self, video_list, channel):
        try:
            channel_folder = channel["Name"]
            channel_folder_path = os.path.join(self.download_folder, channel_folder)

            if not os.path.exists(channel_folder_path):
                os.makedirs(channel_folder_path)

            raw_directory_list = os.listdir(channel_folder_path)
            directory_list = self.string_cleaner(raw_directory_list)

            for vid in video_list:
                if self.string_cleaner(vid["title"]) not in directory_list:
                    logger.warning("Starting Download : " + vid["title"])
                    self.download_video(vid, channel_folder_path)
                else:
                    logger.warning("File Already in folder: " + vid["title"])
        except Exception as e:
            logger.error(str(e))

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

                if os.path.isfile(file_path):
                    channel["Video_Count"] += 1
                    file_ctime = datetime.datetime.fromtimestamp(os.path.getctime(file_path))
                    age = current_datetime - file_ctime

                    if age > datetime.timedelta(days=days_to_keep):
                        os.remove(file_path)
                        logger.warning(f"Deleted: {filename}")
                        channel["Video_Count"] -= 1

        except Exception as e:
            logger.error(str(e))

    def download_video(self, video, channel_folder_path):
        if self.plex_scan_req_flag == False:
            self.plex_scan_req_flag = True
        try:
            link = video["link"]
            title = self.string_cleaner(video["title"])
            full_file_path = os.path.join(channel_folder_path, title)
            ydl_opts = {
                "ffmpeg_location": "/usr/bin/ffmpeg",
                "format": "137+bestaudio/best",
                "outtmpl": full_file_path,
                "quiet": False,
                "writethumbnail": True,
                "progress_hooks": [self.progress_callback],
                "merge_output_format": "mp4",
                "postprocessors": [
                    {
                        "key": "EmbedThumbnail",
                    }
                ],
            }

            yt_downloader = yt_dlp.YoutubeDL(ydl_opts)
            logger.warning("yt_dl Start : " + link)

            yt_downloader.download([link])
            logger.warning("yt_dl Complete : " + link)

        except Exception as e:
            logger.error(f"Error downloading video: {link}. Error message: {e}")

    def progress_callback(self, d):
        if d["status"] == "finished":
            logger.warning("Download complete")

        elif d["status"] == "downloading":
            logger.warning(f'Downloaded {d["_percent_str"]} of {d["_total_bytes_str"]} at {d["_speed_str"]}')

    def master_queue(self):
        try:
            self.plex_scan_req_flag = False
            logger.warning("Sync Task started...")
            for channel in self.req_channel_list:
                logging.warning("Looking for channel Videos on YouTube: " + channel["Name"])
                vid_list = self.get_list_of_videos(channel)

                logging.warning("Starting Downloading List: " + channel["Name"])
                self.check_and_download(vid_list, channel)
                logging.warning("Finished Downloading List: " + channel["Name"])

                logging.warning("Start Clearing Files: " + channel["Name"])
                self.cleanup_old_files(channel)
                logging.warning("Finished Clearing Files: " + channel["Name"])

                channel["Last_Synced"] = datetime.datetime.now().strftime("%d-%m-%y %H:%M:%S")

            self.save_channel_list_to_file()
            data = {"Channel_List": self.req_channel_list}
            socketio.emit("Update", data)

            if self.plex_scan_req_flag == True and self.plex_token:
                logger.warning("Attempting Plex Sync")
                plex_server = PlexServer(self.plex_address, self.plex_token)
                library_section = plex_server.library.section(self.plex_library_name)
                library_section.update()
                logger.warning(f"Library scan for '{self.plex_library_name}' started.")
            else:
                logger.warning("Plex Sync not required")

        except Exception as e:
            logger.error(str(e))
            logger.warning("Sync Finished")

        else:
            logger.warning("Successfully Completed")

    def add_channel(self, channel):
        self.req_channel_list.extend(channel)

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

    def get_seconds_from_duration(self, duration):
        parts = duration.split(":")

        if len(parts) == 2:
            hours, minutes = 0, int(parts[0])
            seconds = int(parts[1])

        elif len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds


app = Flask(__name__)
app.secret_key = "secret_key"
socketio = SocketIO(app)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%d/%m/%Y %H:%M:%S", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger()

data_handler = Data_Handler()


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
        "plex_address": data_handler.plex_address,
        "plex_token": data_handler.plex_token,
        "plex_library_name": data_handler.plex_library_name,
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
    data_handler.plex_address = data["plex_address"]
    data_handler.plex_token = data["plex_token"]
    data_handler.plex_library_name = data["plex_library_name"]
    try:
        if data["sync_start_times"] == "":
            raise Exception("No Time Entered, defaulting to 00:00")
        raw_sync_start_times = [int(re.sub(r"\D", "", start_time.strip())) for start_time in data["sync_start_times"].split(",")]
        temp_sync_start_times = [0 if x < 0 or x > 23 else x for x in raw_sync_start_times]
        cleaned_sync_start_times = sorted(list(set(temp_sync_start_times)))
        data_handler.sync_start_times = cleaned_sync_start_times

    except Exception as e:
        logger.error(str(e))
        data_handler.sync_start_times = [0]
    finally:
        logger.warning("Sync Times: " + str(data_handler.sync_start_times))
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
