
function appendLog(text, color) {
  var dt = new Date();
  var hour = dt.getHours() < 10 ? "0" + String(dt.getHours()) : String(dt.getHours());
  var minute  = dt.getHours() < 10 ? "0" + String(dt.getMinutes()) : String(dt.getMinutes());
  var seconds = dt.getSeconds() < 10 ? "0" + String(dt.getSeconds()) : String(dt.getSeconds());
  
  var log_text = "[" + hour + ":" + minute + ":" + seconds + "] " + text;
  var $row = $("<div></div>").text(log_text);
  if(color) $row.css("color", color);

  $("#log").append($row);

  setTimeout(function() {
      var h = $("#log")[0].scrollHeight;
      $("#log").animate({ scrollTop: h }, "fast");
  }, 5);
}

function appendHtmlLog(html) {
    $("#log").append($(html));

    setTimeout(function() {
        var h = $("#log")[0].scrollHeight;
        $("#log").animate({ scrollTop: h }, "fast");
    }, 5);
}

function ws_close_handler(name) {
    return function(v) {
        if(v.code == 1000) {
            if(v.reason) {
                appendLog(name + "WS CLOSED NORMAL; reason='" + v.reason + "'");
            } else {
                appendLog(name + "WS CLOSED NORMAL");
            }
        } else if(v.code == 1006) {
            appendLog(name + "WS CLOSED ABNORMAL", "rgb(208, 142, 40)");
        } else {
            appendLog(name + "WS CLOSED, code=" + v.code + "; reason=" + v.reason, "#c00");
        }
    }
}

function DiscoverWS(addCallback, removeCallback) {
    var self = this;

    this.ws = new WebSocket("ws://" + window.location.host + "/ws/discover");
    this.ws.onopen = function() {
      appendLog("Discover WS Connected", "#0000aa");
    };
    this.ws.onmessage = function(m) {
      var payload = JSON.parse(m.data);

      if(payload.alive) {
          if(addCallback) {
              addCallback(payload.uuid, payload.serial, payload.name,
                     payload.version, payload.password, payload.ipaddr,
                     payload);
          }
      } else {
          if(removeCallback) removeCallback(payload.serial);
      }
    }

    this.ws.onclose = ws_close_handler("Discover");

    this.close = function() {
        self.ws.close();
        self.ws = undefined;
    }
}

function addDeviceStrHelper(input) {
  if(input===undefined) {
    return "-";
  } else if(input === "") {
    return "-";
  } else if(typeof(input) === "number") {
    var raw = input.toFixed(2);
    if(raw.endsWith(".00")) {
      return raw.substring(0, raw.length - 3);
    } else {
      return raw;
    }
  } else {
    return input;
  }
}

function addDevice(uuid, serial, name, version, password, ipaddr, dataset) {
  var $item = $("<a></a>").
    attr("href", "#" + uuid + ";" + name).
    addClass("list-group-item").
    attr("data-serial", uuid).
    attr("data-uuid", uuid).
    attr("data-password", password ? "true" : "false").
    attr("data-name", name);

  var $row1 = $("<div></div>");
  var $row2 = $("<div></div>");
  $item.append($row1);
  $item.append($row2);

  if(password) $row1.append($("<span></span>").addClass("glyphicon glyphicon-lock"));
  $row1.append($("<span></span>").text(serial).addClass("label label-primary"));
  $row1.append($("<span></span>").text(" "));
  $row1.append($("<span></span>").text(name));

  $row1.append($("<span></span>").text("ST_TS / ST_ID / ST_PROG / HEAD").addClass("pull-right"))

  $row2.append($("<span></span>").text(uuid).addClass("label label-default"));
  $row2.append($("<span></span>").text(" "));
  $row2.append($("<span></span>").text(version));
  $row2.append($("<span></span>").text(" / "));
  $row2.append($("<span></span>").text(ipaddr));

  $row2.append($("<span></span>").text(
    addDeviceStrHelper(dataset.st_ts) + " / " + addDeviceStrHelper(dataset.st_id) + " / " + 
    addDeviceStrHelper(dataset.st_prog) + " / " + addDeviceStrHelper(dataset.head_module)
  ).addClass("pull-right"))

  var $old = $("[data-uuid=" + uuid + "]", "#devices");
  $old.remove();

  $("#devices").append($item);
}

function removeDevice(serial) {
  $("[data-device=" + serial + "]").remove();
}

function startDiscover() {
  $("#devices").children().remove();
  if(window.discover_ws) stopDiscover();
  window.discover_ws = new DiscoverWS(addDevice, removeDevice);
  $("[data-role=discover]").removeClass("btn-success").addClass("btn-warning").text("Stop Discover");
}

function stopDiscover() {
  if(!window.discover_ws) return;
  window.discover_ws.close();
  window.discover_ws = undefined;
  $("[data-role=discover]").removeClass("btn-warning").addClass("btn-success").text("Start Discover");
}

