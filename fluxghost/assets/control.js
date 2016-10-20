
(function(base) {
    BinaryReciver = function(mimetype, size) {
        var blobs = []
        var buffered = 0;

        this.size = size;

        this.buffered_length = function() {
            return buffered;
        }

        this.feed = function(blob) {
            if(buffered + blob.size <= size) {
                blobs.push(blob);
                buffered += blob.size;
            } else {
                console.log("Bad data length, buffered=" + buffered + ", recived=" + blob.size + ", size=" + size);
                throw "Buffer full";
            }
        }

        this.getBlob = function(blob) {
            if(buffered != size) {
                console.log("Bad data length, buffered=" + buffered + ", size=" + size);
                throw "Broken stream";
            }
            return new Blob(blobs, { type: mimetype });
        }


    }

    base.FLUXControl = function(uuid, options) {
        /* options = {
            clientkey: "RSA key (pem)",
            baseurl: "http://localhost:8000",

            on_connecting: function(obj|controller, str|stage) {},
            on_connected: function(obj|controller) {},
            on_error: function(obj|controller, str|cmd, array|errors, any|data) {},
            on_close: function(obj|controller, obj|event) {},
            on_fatal: function(obj|controller, str|source, str|cmd, array|errors) {
                // source: "REMOTE" -> fatal come from device,
                //         "LOCAL" -> fatal is raised from local program
                // cmd can be undefined during connecting stage
            },
        }

        this.send_command("COMMAND", {
            on_success: function(obj|controller, str|cmd, obj|result, any|data) {},
            on_error: function(obj|controller, str|cmd, array|errors, any|data) {},
            on_upload_begin: function(obj|controller, int|datasize, any|data) {},
            on_uploading: function(obj|controller, int|sentsize, int|datasize, any|data) {
                // Note 1: Please consider datasize will be changed during uploading.
                // Note 2: When sentsize === datasize stands for uploading is completed.
            },
            on_download_begin: function(obj|controller, int|datasize, any|data) {},
            on_downloading: function(obj|controller, int|recivedsize, int|datasize, any|data) {
                // Note 1: When recivedsize === datasize stands for download is completed.
            },
            file: fileobject,
            data: any
        })
        this.is_busy(); // => return true if has command executing
        this.get_counter(); // => return number of commands has sent
        this.status(); // => return "INIT"|"CONNECTING"|"CONNECTED"|"DISCONNECTING"|"CLOSED"
        this.close();
        */

        var ST_INIT = "INIT";
        var ST_CONNECTING = "CONNECTING";
        var ST_CONNECTED = "CONNECTED";
        var ST_DISCONNECTING = "DISCONNECTING";
        var ST_CLOSED = "CLOSED";

        var self = this;
        var ws_url = "ws://" + (options.baseurl || base.location.host ) + "/ws/control/" + uuid;
        var ws = new WebSocket(ws_url);
        var command_queue = [];
        var waitting_response = false;
        var _status = ST_INIT;

        var binaries = undefined;
        var additional = undefined;

        var raw = false;
        var counter = 0;

        ws.onopen = function(v) {
            ws.send(options.clientkey);
            _status = ST_CONNECTING;
        }

        function connecting_helper(payload) {
            switch(payload.status) {
                case "connecting":
                    if(options.on_connecting) {
                        options.on_connecting(self, payload.stage);
                    }
                    break;
                case "connected":
                    _status = ST_CONNECTED;
                    if(options.on_connected) {
                        options.on_connected(self);
                    }
                    break;
                case "fatal":
                    self.close();
                    if(options.on_fatal) {
                        options.on_fatal(self, "REMOTE", undefined,
                                         [payload.error])
                    }
                    break;
                default:
                    console.log("Unhandle status: " + payload.status);
            }
        }

        function ParseJsonData(str) {
            try {
                return JSON.parse(str);
            } catch(err) {
                console.log(err);
                // MONKEY PATCH // MONKEY PATCH // MONKEY PATCH // MONKEY PATCH
                if(str.indexOf("NaN")) {
                    console.log("Parse response failed but find magic str: NaN, try replace and parse again");
                    console.log("Data: '" + str + "'")
                    return ParseJsonData(str.replace("NaN", "null"));
                }
                throw err;
            }
        }

        ws.onmessage = function(m) {
            if(_status === ST_CONNECTING) {
                try {
                    var payload = JSON.parse(m.data);
                    connecting_helper(payload);
                } catch(err) {
                    console.log("Handle connecting error: " + err + "; DATA=" + m.data);
                    self.close();
                }
            } else if(command_queue.length) {
                var obj = command_queue[0];

                if(m.data.constructor === Blob) {
                    if(!binaries) {
                        console.log("Recive binary but can not process");
                        return;
                    }

                    var binary_obj = binaries[binaries.length - 1];
                    binary_obj.feed(m.data);

                    if(obj.options.on_downloading) {
                        obj.options.on_downloading(
                            self, binary_obj.buffered_length(), binary_obj.size,
                            obj.options.data);
                    }
                    return;
                }

                try {
                    var payload = ParseJsonData(m.data);
                } catch(err) {
                    console.log("Unhandle response '" + m.data + "' from command: '" + obj.cmd + "'.");
                    return;
                }

                if(payload.status === "ok" || payload.status === "pong") {
                    command_queue.shift();
                    waitting_response = false;

                    if(binaries) {
                        var blobs = [];
                        for(var i=0;i<binaries.length;i++) {
                            blobs.push(binaries[i].getBlob());
                        }
                        payload.binaries = blobs;
                        binaries = undefined;
                    }
                    if(additional) {
                      for(var key in additional) {
                        payload[key] = additional[key];
                      }
                      additional = undefined;
                    }

                    if(payload.task !== undefined) {
                        raw = payload.task === "raw";
                    }

                    if(obj.options.on_success) {
                        obj.options.on_success(self, obj.cmd, payload, obj.data);
                    }
                } else if(payload.status === "error" || payload.status === "fatal") {
                    command_queue.shift();
                    waitting_response = false;
                    on_error_helper(obj, payload);
                } else if(payload.status === "continue") {
                    var reader = new FileReader();
                    reader.onload = upload_helper;
                    reader.readAsArrayBuffer(obj.options.file);
                    obj.amount = obj.options.file.size;
                    if(obj.options.on_upload_begin) {
                        obj.options.on_upload_begin(self, obj.options.file.size, obj.options.data);
                    }
                } else if(payload.status === "uploading") {
                    if(payload.amount) obj.amount = payload.amount;
                    if(obj.options.on_uploading) {
                        obj.options.on_uploading(self, payload.sent, obj.amount, obj.options.data)
                    }
                } else if(payload.status === "binary") {
                    if(!binaries) {
                        binaries = []
                    }
                    var br = new BinaryReciver(payload.mimetype, payload.size || payload.length);
                    binaries.push(br);
                    if(obj.options.on_download_begin) {
                        obj.options.on_download_begin(self, payload.size || payload.length, obj.options.data);
                    }
                } else if(payload.status === "transfer") {
                    if(payload.completed === 0 && obj.options.on_transfer_begin) {
                        obj.options.on_transfer_begin(self, payload.size, obj.options.data);
                    }
                    if(obj.options.on_transfer) {
                        obj.options.on_transfer(self, payload.completed, payload.size, obj.options.data);
                    }
                } else {
                    var event_name = "on_" + payload.status;
                    if(obj.options[event_name]) {
                        obj.options[event_name](self, obj.cmd, payload, obj.options.data);
                    } else {
                        if(!additional) {
                            additional = {};
                        }
                        if(!additional[payload.status]) {
                            additional[payload.status] = [];
                        }
                        additional[payload.status].push(payload);
                        delete payload.status;
                    }
                }
                fire()
            } else {
                try {
                    var payload = JSON.parse(m.data);
                    if(payload.status === "raw") {
                        if(options.on_raw) {
                            options.on_raw(self, payload.text);
                        }
                        return;
                    }
                } catch(err) {}
                console.log("Recive message but command queue is empty. (" + m.data + ")");
            }
        }

        ws.onclose = function(v) {
            _status = ST_CLOSED;
            if(options.on_close) options.on_close(self, v);
        };

        function on_error_helper(obj, payload) {
            if(payload.status === "error") {
                if(obj.options.on_error) {
                    errors = (payload.error.constructor === Array) ? payload.error : [payload.error];
                    obj.options.on_error(self, obj.cmd, errors, obj.data);
                } else if(options.on_error) {
                    errors = (payload.error.constructor === Array) ? payload.error : [payload.error];
                    options.on_error(self, obj.cmd, errors, obj.data);
                } else {
                    console.log("Command '" + obj.cmd + "' got an error: " + er);
                }
            } else if(payload.status === "fatal") {
                self.close();
                var er = (payload.error.constructor === String) ? payload.error.split(" ") : payload.error;
                if(options.on_fatal) {
                    options.on_fatal(self, "REMOTE", er)
                } else {
                    console.log("Control get an fatal error: " + er);
                }
            }
        }

        function upload_helper(f) {
            var offset = 0;
            while(offset < f.target.result.byteLength) {
              ws.send(f.target.result.slice(offset, offset + 3984));
              offset += 3984;
            }
        }

        function fire() {
            if(waitting_response || command_queue.length === 0 || _status !== ST_CONNECTED) {
                return;
            }

            var obj = command_queue[0];
            ws.send(obj.cmd);
            counter += 1;
            waitting_response = true;
        };

        this.get_counter = function() {
            return counter;
        }

        this.is_busy = function() {
            return waitting_response;
        }

        this.send_command = function(command, options) {
            if(_status === "CONNECTED") {
                if(raw && command !== "task quit" && command != "ping") {
                    ws.send(command);
                    return;
                }

                if(options.constructor === Function) {
                    options = {on_success: options};
                }

                command_queue.push({cmd: command, options: options});
                fire();
            } else {
                throw "Can not send command '" + command + "' because connection status is '" + _status + "'";
            }
        };

        this.status = function() {
            return _status;
        }

        this.close = function() {
            if(_status !== ST_CLOSED) {
                _status = ST_DISCONNECTING;
                ws.close();
            }
        };

        return self;
    };
})(this);
