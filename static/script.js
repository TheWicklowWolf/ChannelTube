
var config_modal = document.getElementById('config-modal');
var save_message = document.getElementById("save-message");
var save_changes_button = document.getElementById("save-changes-button");
var save_channel_list = document.getElementById("save-channel-list");
var save_channel_list_msg = document.getElementById("save-channel-list-msg");
var sync_start_times = document.getElementById("sync_start_times");
var media_server_addresses = document.getElementById("media_server_addresses");
var media_server_tokens = document.getElementById("media_server_tokens");
var media_server_library_name = document.getElementById("media_server_library_name");
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
                <td class="text-center">${channel.Video_Count}</td>
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
                                    <label for="channelName${index}">Channel Name:</label>
                                    <input type="text" class="form-control" id="channelName${index}" value="${channel.Name}">
                                </div>
                                <div class="form-group my-3">
                                    <label for="channelLink${index}">Channel Link:</label>
                                    <input type="text" class="form-control" id="channelLink${index}" value="${channel.Link}">
                                </div>
                                <div class="form-group my-3">
                                    <label for="dlDays${index}">Days to Sync:</label>
                                    <input type="number" class="form-control" min="0" id="dlDays${index}" value="${channel.DL_Days}">
                                </div>
                                <div class="form-group my-3">
                                    <label for="keepDays${index}">Days to Keep:</label>
                                    <input type="number" class="form-control" min="0" id="keepDays${index}" value="${channel.Keep_Days}">
                                </div>
                                <div class="form-group">
                                    <label for="filterTitleText${index}" class="me-2 mb-0">Filter Title Text:</label>
                                    <div class="form-group d-flex align-items-center">
                                        <input type="text" class="form-control me-2" id="filterTitleText${index}" value="${channel.Filter_Title_Text || ''}">
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" id="negateFilter${index}" ${channel.Negate_Filter ? 'checked' : ''}>
                                            <label class="form-check-label" for="negateFilter${index}">
                                                Negate
                                            </label>
                                        </div>
                                    </div>
                                    <p id="filterTextDescription${index}" class="m-1 text-secondary">
                                        ${channel.Negate_Filter ? "Videos with this text in the title are not downloaded." : "Only videos with this text in the title are downloaded."}
                                    </p>
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

        const negateCheckbox = document.getElementById(`negateFilter${index}`);
        const description = document.getElementById(`filterTextDescription${index}`);

        negateCheckbox.addEventListener('change', function () {
            if (negateCheckbox.checked) {
                description.textContent = "Videos with this text in the title are not downloaded.";
            } else {
                description.textContent = "Only videos with this text in the title are downloaded.";
            }
        });
    });
}

function saveChannelSettings(index) {
    channels[index].Name = document.getElementById(`channelName${index}`).value;
    channels[index].Link = document.getElementById(`channelLink${index}`).value;
    channels[index].DL_Days = parseInt(document.getElementById(`dlDays${index}`).value, 10);
    channels[index].Keep_Days = parseInt(document.getElementById(`keepDays${index}`).value, 10);
    channels[index].Filter_Title_Text = document.getElementById(`filterTitleText${index}`).value;
    channels[index].Negate_Filter = document.getElementById(`negateFilter${index}`).checked;

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
    channels.push(
        {
            Name: "New Channel",
            Link: "Channel URL",
            Keep_Days: 28,
            DL_Days: 14,
            Last_Synced: "Never",
            Video_Count: 0,
            Filter_Title_Text: "",
            Negate_Filter: false,
        }
    );
    renderChannels();
    createEditModalsAndListeners();
});

config_modal.addEventListener('show.bs.modal', function (event) {
    socket.emit("loadSettings");
    function handleSettingsLoaded(settings) {
        sync_start_times.value = settings.sync_start_times.join(', ');
        media_server_addresses.value = settings.media_server_addresses;
        media_server_tokens.value = settings.media_server_tokens;
        media_server_library_name.value = settings.media_server_library_name;
        socket.off("settingsLoaded", handleSettingsLoaded);
    }
    socket.on("settingsLoaded", handleSettingsLoaded);
});

save_changes_button.addEventListener("click", () => {
    socket.emit("updateSettings", {
        "sync_start_times": sync_start_times.value,
        "media_server_addresses": media_server_addresses.value,
        "media_server_tokens": media_server_tokens.value,
        "media_server_library_name": media_server_library_name.value,
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

const themeSwitch = document.getElementById('themeSwitch');
const savedTheme = localStorage.getItem('theme');
const savedSwitchPosition = localStorage.getItem('switchPosition');

if (savedSwitchPosition) {
    themeSwitch.checked = savedSwitchPosition === 'true';
}

if (savedTheme) {
    document.documentElement.setAttribute('data-bs-theme', savedTheme);
}

themeSwitch.addEventListener('click', () => {
    if (document.documentElement.getAttribute('data-bs-theme') === 'dark') {
        document.documentElement.setAttribute('data-bs-theme', 'light');
    } else {
        document.documentElement.setAttribute('data-bs-theme', 'dark');
    }
    localStorage.setItem('theme', document.documentElement.getAttribute('data-bs-theme'));
    localStorage.setItem('switchPosition', themeSwitch.checked);
});
