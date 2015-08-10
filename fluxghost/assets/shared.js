
function appendLog(text, color) {
  var dt = new Date();
  var hour = dt.getHours() < 10 ? "0" + String(dt.getHours()) : String(dt.getHours());
  var minute  = dt.getHours() < 10 ? "0" + String(dt.getMinutes()) : String(dt.getMinutes());
  var seconds = dt.getSeconds() < 10 ? "0" + String(dt.getSeconds()) : String(dt.getSeconds());
  
  var log_text = "[" + hour + ":" + minute + ":" + seconds + "] " + text;
  var $row = $("<div></div>").text(log_text);
  if(color) $row.css("color", color);
  $("#log").prepend($row);
}

function appendHtmlLog(html) {
    $("#log").prepend($(html));
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
          if(addCallback) addCallback(payload.serial, payload.name, payload.version, payload.password);
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

function addDevice(serial, name, version, password) {
  var $item = $("<a></a>").
    attr("href", "#").
    addClass("list-group-item").
    attr("data-serial", serial).
    attr("data-password", password ? "true" : "false").
    attr("data-name", name);

  if(password) $item.append($("<span></span>").addClass("glyphicon glyphicon-lock"));
  $item.append($("<span></span>").text(" "));
  $item.append($("<span></span>").text(name));
  $item.append($("<span></span>").text(" "));
  $item.append($("<span></span>").text(serial).addClass("label label-default"));

  $("#devices").append($item);
}

function removeDevice(serial) {
  $("[data-device=" + serial + "]").remove();
}

function startDiscover() {
  $("#devices").children().remove();
  window.discover_ws = new DiscoverWS(addDevice, removeDevice);
  $("[data-role=discover]").removeClass("btn-success").addClass("btn-warning").text("Stop Discover");
}

function stopDiscover() {
  if(!window.discover_ws) return;
  window.discover_ws.close();
  window.discover_ws = undefined;
  $("[data-role=discover]").removeClass("btn-warning").addClass("btn-success").text("Start Discover");
}

