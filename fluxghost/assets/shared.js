
function appendLog(text, color) {
  var dt = new Date();
  var log_text = "[" + dt.getHours() + ":" + dt.getMinutes() + ":" + dt.getSeconds() + "] " + text;
  var $row = $("<div></div>").text(log_text);
  if(color) $row.css("color", color);
  $("#log").append($row);
}


function DiscoverWS(addCallback, removeCallback) {
    var self = this;

    this.ws = new WebSocket("ws://localhost:8000/ws/discover");
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

    this.ws.onclose = function(v) {
      appendLog("Discover WS Closed, code=" + v.code + "; reason=" + v.reason);
    };

    this.close = function() {
        self.ws.close();
        self.ws = undefined;
    }
}
