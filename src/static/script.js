
var config_modal = document.getElementById('config-modal');
var save_message = document.getElementById("save-message");
var save_changes_button = document.getElementById("save-changes-button");
var save_channel_list = document.getElementById("save-channel-list");
var save_channel_list_msg = document.getElementById("save-channel-list-msg");
var sync_start_time = document.getElementById("sync_start_time");
var plex_address = document.getElementById("plex_address");
var plex_token = document.getElementById("plex_token");
var plex_library_name = document.getElementById("plex_library_name");
var channels = [];
var socket = io();

function renderChannels() {
    var channelList = document.getElementById("channel-list");
    channelList.innerHTML = "";
    channels.forEach((channel, index) => {
        var row = document.createElement("tr");
        row.innerHTML = `
                <td>${channel.Name}</td>
                <td>${channel.Last_Synced}</td>
                <td>${channel.Video_Count}</td>
                <td>
                    <button class="btn btn-sm btn-primary custom-button-width" data-bs-toggle="modal" data-bs-target="#editModal${index}">Edit</button>
                </td>
            `;
        var deleteButton = createDeleteButton(index);
        row.querySelector("td:last-child").appendChild(deleteButton);
        channelList.appendChild(row);
    });
}

function removeChannel(index) {
    channels.splice(index, 1);
    renderChannels();
    createEditModalsAndListeners();
}

function createDeleteButton(index) {
    var deleteButton = document.createElement("button");
    deleteButton.className = "btn btn-sm btn-danger custom-button-width";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", function () {
        removeChannel(index);
    });
    return deleteButton;
}

function updated_info(response) {
    channels = response.Channel_List;
    renderChannels();
    createEditModalsAndListeners();
}

function createEditModalsAndListeners() {
    channels.forEach((channel, index) => {
        var editModal = document.createElement("div");
        editModal.innerHTML = `
                <div class="modal fade" id="editModal${index}" tabindex="-1" role="dialog" aria-labelledby="editModalLabel" aria-hidden="true">                <div class="modal-dialog" role="document">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="editModalLabel${index}">Edit Channel</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                        <div id="save-message-channel-edit${index}" style="display: none;" class="alert alert-success mt-3">
                        Settings saved successfully.
                        </div>
                            <form>
                                <div class="form-group">
                                    <label for="channelName">Channel Name</label>
                                    <input type="text" class="form-control" id="channelName${index}" value="${channel.Name}">
                                </div>
                                <div class="form-group">
                                    <label for="dlDays">Days to Sync</label>
                                    <input type="number" class="form-control" id="dlDays${index}" value="${channel.DL_Days}">
                                </div>
                                <div class="form-group">
                                    <label for="keepDays">Days to keep</label>
                                    <input type="number" class="form-control" id="keepDays${index}" value="${channel.Keep_Days}">
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                            <button type="button" class="btn btn-primary" onclick="saveChannelSettings(${index})">Save Changes</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(editModal);
    });
}

function saveChannelSettings(index) {
    channels[index].Name = document.getElementById(`channelName${index}`).value;
    channels[index].DL_Days = parseInt(document.getElementById(`dlDays${index}`).value, 10);
    channels[index].Keep_Days = parseInt(document.getElementById(`keepDays${index}`).value, 10);
    socket.emit("save_channel_settings", { "channel": channels[index] });
    var save_message_channel_edit = document.getElementById(`save-message-channel-edit${index}`);
    save_message_channel_edit.style.display = "block";
    setTimeout(function () {
        save_message_channel_edit.style.display = "none";
    }, 1000);
    renderChannels();
}

socket.on("Update", updated_info);

document.getElementById("add-channel").addEventListener("click", function () {
    channels.push({ Name: "New Channel", "Keep_Days": 28, "DL_Days": 14, Last_Synced: "Never", Video_Count: 0 });
    renderChannels();
    createEditModalsAndListeners();
});

config_modal.addEventListener('show.bs.modal', function (event) {
    socket.emit("loadSettings");
    function handleSettingsLoaded(settings) {
        sync_start_time.value = settings.sync_start_time;
        plex_address.value = settings.plex_address;
        plex_token.value = settings.plex_token;
        plex_library_name.value = settings.plex_library_name;
        socket.off("settingsLoaded", handleSettingsLoaded);
    }
    socket.on("settingsLoaded", handleSettingsLoaded);
});

save_changes_button.addEventListener("click", () => {
    socket.emit("updateSettings", {
        "sync_start_time": sync_start_time.value,
        "plex_address": plex_address.value,
        "plex_token": plex_token.value,
        "plex_library_name": plex_library_name.value,
    });
    save_message.style.display = "block";
    setTimeout(function () {
        save_message.style.display = "none";
    }, 1000);
});

save_channel_list.addEventListener("click", () => {
    socket.emit("save_channels", { "Saved_Channel_List": channels });
    save_channel_list_msg.style.display = "inline";
    save_channel_list_msg.textContent = "Saved!";
    setTimeout(function () {
        save_channel_list_msg.textContent = "";
        save_message.style.display = "none";
    }, 3000);
});
