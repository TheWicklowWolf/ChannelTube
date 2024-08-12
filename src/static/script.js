const config_modal = document.getElementById("config-modal");
const save_message = document.getElementById("save-message");
const save_changes_button = document.getElementById("save-changes-button");
const sync_start_times = document.getElementById("sync-start-times");
const media_server_addresses = document.getElementById("media-server-addresses");
const media_server_tokens = document.getElementById("media-server-tokens");
const media_server_library_name = document.getElementById("media-server-library-name");
const add_channel = document.getElementById("add-channel");
const channel_table = document.getElementById("channel-table").querySelector("tbody");
const modal_channel_template = document.getElementById("modal-channel-template").content;
let channel_list = [];
const socket = io();

function change_filter_description(negate_filter_checkbox, filter_text_description) {
    filter_text_description.textContent = negate_filter_checkbox.checked
        ? "Ignore videos with this text in the title."
        : "Only get videos with this text in the title.";
}

function open_edit_modal(channel) {
    const channel_edit_modal_container = document.createElement("div");
    channel_edit_modal_container.appendChild(document.importNode(modal_channel_template, true));

    const modal = channel_edit_modal_container.querySelector("#modal-channel-config");
    const channel_name_input = modal.querySelector("#channel-name");
    const channel_link_input = modal.querySelector("#channel-link");
    const download_days_input = modal.querySelector("#download-days");
    const keep_days_input = modal.querySelector("#keep-days");
    const title_filter_text_input = modal.querySelector("#title-filter-text");
    const negate_filter_checkbox = modal.querySelector("#negate-filter");
    const media_type_selector = modal.querySelectorAll("input[name='media-type-selector']");
    const filter_text_description = modal.querySelector("#filter-text-description");

    channel_name_input.value = channel.Name;
    channel_link_input.value = channel.Link;
    download_days_input.value = channel.DL_Days;
    keep_days_input.value = channel.Keep_Days;
    title_filter_text_input.value = channel.Filter_Title_Text;
    negate_filter_checkbox.checked = channel.Negate_Filter;

    change_filter_description(negate_filter_checkbox, filter_text_description);

    negate_filter_checkbox.addEventListener("change", () => {
        change_filter_description(negate_filter_checkbox, filter_text_description);
    });

    media_type_selector.forEach(radio => {
        if (radio.value === channel.Media_Type) {
            radio.checked = true;
        }
    });

    document.body.appendChild(channel_edit_modal_container);
    const modal_edit_channel = new bootstrap.Modal(modal);
    modal_edit_channel.show();

    modal.querySelector("#save-channel-changes-button").addEventListener("click", function () {
        save_channel_changes(channel);
    });

    modal.addEventListener("hidden.bs.modal", function () {
        channel_edit_modal_container.remove();
    });
}

function add_row_to_channel_table(channel) {
    const template = document.getElementById("channel-row-template");
    const new_row = document.importNode(template.content, true);
    const row = new_row.querySelector("tr");

    row.id = channel.Id;
    row.querySelector(".channel-name").textContent = channel.Name;
    row.querySelector(".channel-last-synced").textContent = channel.Last_Synced;
    row.querySelector(".channel-item-count").textContent = channel.Item_Count;

    const edit_button = row.querySelector(".edit-button");
    edit_button.addEventListener("click", function () {
        open_edit_modal(channel);
    });

    const remove_button = row.querySelector(".remove-button");
    remove_button.addEventListener("click", function () {
        remove_channel(channel);
    });

    channel_table.appendChild(row);
}

function remove_channel(channel_to_be_removed) {
    const confirmation = confirm("Are you sure you want to remove this channel?");

    if (confirmation) {
        socket.emit("remove_channel", channel_to_be_removed);

        const index = channel_list.findIndex(c => c.Id === channel_to_be_removed.Id);
        if (index > -1) {
            channel_list.splice(index, 1);
            const row = document.getElementById(`${channel_to_be_removed.Id}`);
            if (row) {
                row.remove();
            }
        }
    }
}

function save_channel_changes(channel) {
    const channel_updates = {
        Id: channel.Id,
        Name: document.getElementById("channel-name").value,
        Link: document.getElementById("channel-link").value,
        DL_Days: parseInt(document.getElementById("download-days").value, 10),
        Keep_Days: parseInt(document.getElementById("keep-days").value, 10),
        Filter_Title_Text: document.getElementById("title-filter-text").value,
        Negate_Filter: document.getElementById("negate-filter").checked,
        Media_Type: document.querySelector("input[name='media-type-selector']:checked").value,
    };

    socket.emit("save_channel_changes", channel_updates);

    const rows = channel_table.querySelectorAll("tr");
    rows.forEach(row => {
        if (row.id === String(channel.Id)) {
            row.querySelector(".channel-name").textContent = channel_updates.Name;
        }
    });

    document.getElementById("save-channel-message").style.display = "block";
    setTimeout(() => {
        document.getElementById("save-channel-message").style.display = "none";
    }, 1000);
}

add_channel.addEventListener("click", function () {
    socket.emit("add_channel");
});

config_modal.addEventListener("show.bs.modal", function (event) {
    socket.emit("get_settings");
});

save_changes_button.addEventListener("click", () => {
    socket.emit("update_settings", {
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

socket.on("update_channel_list", function (data) {
    channel_table.innerHTML = "";
    channel_list = data.Channel_List;
    channel_list.forEach(channel => {
        add_row_to_channel_table(channel);
    });
});

socket.on("new_channel_added", function (new_channel) {
    channel_list.push(new_channel);
    add_row_to_channel_table(new_channel);
});

socket.on("updated_settings", function (settings) {
    sync_start_times.value = settings.sync_start_times.join(", ");
    media_server_addresses.value = settings.media_server_addresses;
    media_server_tokens.value = settings.media_server_tokens;
    media_server_library_name.value = settings.media_server_library_name;
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
