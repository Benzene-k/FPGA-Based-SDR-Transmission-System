module sdr_uart_endpoint #(
        parameter   PROFILE_RF = 0,
        parameter   PROFILE_N = 4096,
        parameter   [31:0]  DEFAULT_PEAK = 1,
        parameter   [31:0]  DEFAULT_MARGIN = 1
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    [31:0]  session_id,
        input   wire    [7:0]   rx_data,
        input   wire    rx_valid,
        output  reg     [7:0]   tx_data,
        output  wire    tx_valid,
        input   wire    tx_ready,
        output  reg     load_start,
        output  reg     [15:0]  load_seq,
        output  reg     [15:0]  load_length,
        output  wire    load_valid,
        output  wire    [7:0]   load_data,
        input   wire    load_ready,
        input   wire    message_ready,
        output  reg     tx_start,
        output  reg     tx_abort,
        input   wire    tx_busy,
        input   wire    tx_done,
        input   wire    tx_error,
        input   wire    [2:0]   tx_error_code,
        output  reg     rx_abort,
        output  reg     release_packet,
        output  wire    [7:0]   read_addr,
        input   wire    [7:0]   read_data,
        input   wire    read_valid,
        input   wire    packet_ready,
        input   wire    packet_valid,
        input   wire    [15:0]  packet_seq,
        input   wire    [15:0]  packet_length,
        input   wire    rx_error,
        input   wire    [2:0]   rx_error_code,
        input   wire    sync_locked,
        input   wire    rx_flow_fault,
        output  reg     [31:0]  peak_config,
        output  reg     [31:0]  margin_config,
        output  reg     diagnostic_loopback
);

localparam  RX = 0;
localparam  EXEC = 1;
localparam  BEGIN_WAIT = 2;
localparam  WRITE = 3;
localparam  READ = 4;
localparam  REPLY = 5;
localparam  CONFIG_REPLY = 6;
localparam  [31:0] CENTER = PROFILE_RF ? 7000000 : 0;
localparam  [31:0] BANDWIDTH = PROFILE_RF ? 1000000 : 0;
localparam  [31:0] RF_RATE = PROFILE_RF ? 25000000 : 0;
localparam  [31:0] BASE_RATE = PROFILE_RF ? 2500000 : 0;
localparam  [15:0] POINTS = PROFILE_N;

reg [2:0]   state;
reg [8:0]   rx_pos;
reg [8:0]   tx_pos;
reg [8:0]   body_length;
reg [8:0]   write_index;
reg [8:0]   read_index;
reg [15:0]  request_length;
reg [15:0]  loaded;
reg [15:0]  planned;
reg [15:0]  crc;
reg [7:0]   kind;
reg [7:0]   seq;
reg [7:0]   reply_kind;
reg    active_load;
reg [3:0]   wait_count;
reg [31:0]  generation;
reg    exhausted;
reg [2:0]   last_tx_error;
reg [2:0]   last_rx_error;
reg [7:0]   args[0:255];
reg [7:0]   body[0:255];

wire    [15:0]  offset = {args[0],args[1]};
wire    [15:0]  read_offset = {args[8],args[9]};
wire    [31:0]  ticket_session = {args[0],args[1],args[2],args[3]};
wire    [31:0]  ticket_generation = {args[4],args[5],args[6],args[7]};
wire    ticket_ok = packet_ready && !exhausted && ticket_session == session_id && ticket_generation == generation;
wire    [16:0]  write_end = {1'b0,offset} + {1'b0,request_length} - 17'd2;
wire    [16:0]  read_end = {1'b0,read_offset} + {9'b0,args[10]};

assign  load_valid = state == WRITE && load_ready;
assign  load_data = args[write_index + 2];
assign  read_addr = read_offset[7:0] + read_index[7:0];
assign  tx_valid = state == REPLY;

function [15:0] crc_byte;
        input   [15:0]  seed;
        input   [7:0]   value;
        reg [15:0]  c;
        integer i;
        begin
            c = seed ^ {value,8'b0};
            for (i = 0; i < 8; i = i + 1) c = c[15] ? (c << 1) ^ 16'h1021 : c << 1;
            crc_byte = c;
        end
endfunction

always  @* begin
    case (tx_pos)
        0: tx_data = 8'haa;
        1: tx_data = 8'h55;
        2: tx_data = reply_kind;
        3: tx_data = seq;
        4: tx_data = {7'b0,body_length[8]};
        5: tx_data = body_length[7:0];
        default: begin
            if (tx_pos == body_length + 6) tx_data = crc[15:8];
            else if (tx_pos == body_length + 7) tx_data = crc[7:0];
            else tx_data = body[tx_pos - 6];
        end
    endcase
end

task response;
        input   [7:0]   response_type;
        input   [8:0]   size;
        begin
            reply_kind <= response_type;
            body_length <= size;
            tx_pos <= 0;
            crc <= 16'hffff;
            state <= REPLY;
        end
endtask

task failure;
        input   [7:0]   code;
        begin
            body[0] <= kind;
            body[1] <= code;
            response(8'hdf, 2);
        end
endtask

always  @(posedge clk) begin
    if (rst_n && state == RX && rx_valid && rx_pos >= 6 && rx_pos < request_length + 6) begin
        args[rx_pos - 6] <= rx_data;
    end
end

always  @(posedge clk) begin
    if (!rst_n) begin
        state <= RX;
        rx_pos <= 0;
        tx_pos <= 0;
        request_length <= 0;
        kind <= 0;
        seq <= 0;
        body_length <= 0;
        reply_kind <= 0;
        crc <= 16'hffff;
        write_index <= 0;
        read_index <= 0;
        load_start <= 0;
        load_seq <= 0;
        load_length <= 0;
        tx_start <= 0;
        tx_abort <= 0;
        rx_abort <= 0;
        release_packet <= 0;
        loaded <= 0;
        planned <= 0;
        active_load <= 0;
        wait_count <= 0;
        generation <= 0;
        exhausted <= 0;
        last_tx_error <= 0;
        last_rx_error <= 0;
        peak_config <= DEFAULT_PEAK;
        margin_config <= DEFAULT_MARGIN;
        diagnostic_loopback <= 0;
    end
    else begin
        load_start <= 0;
        tx_start <= 0;
        tx_abort <= 0;
        rx_abort <= 0;
        release_packet <= 0;
        if (tx_error) last_tx_error <= tx_error_code;
        if (rx_error) last_rx_error <= rx_error_code;
        if (packet_valid) begin
            if (generation == 32'hffffffff) exhausted <= 1;
            else generation <= generation + 1'b1;
        end
        case (state)
            RX: if (rx_valid) begin
                if (rx_pos == 2) kind <= rx_data;
                if (rx_pos == 3) seq <= rx_data;
                if (rx_pos == 4) request_length[15:8] <= rx_data;
                if (rx_pos == 5) request_length[7:0] <= rx_data;
                if (rx_pos >= 7 && rx_pos == request_length + 7) begin
                    rx_pos <= 0;
                    state <= EXEC;
                end
                else rx_pos <= rx_pos + 1'b1;
            end
            EXEC: case (kind)
                8'h50: begin
                    if (request_length != 4 || {args[2],args[3]} > 256) failure(1);
                    else if (tx_busy) failure(2);
                    else begin
                        load_seq <= {args[0],args[1]};
                        load_length <= {args[2],args[3]};
                        planned <= {args[2],args[3]};
                        loaded <= 0;
                        active_load <= 1;
                        load_start <= 1;
                        wait_count <= 0;
                        state <= BEGIN_WAIT;
                    end
                end
                8'h51: begin
                    if (request_length < 3 || request_length > 130 || write_end > {1'b0,planned}) failure(1);
                    else if (tx_busy) failure(2);
                    else if (!active_load || offset != loaded) failure(3);
                    else begin
                        write_index <= 0;
                        wait_count <= 0;
                        state <= WRITE;
                    end
                end
                8'h52: begin
                    if (request_length != 0) failure(1);
                    else if (tx_busy) failure(2);
                    else if (!active_load || loaded != planned || !message_ready) failure(3);
                    else begin
                        tx_start <= 1;
                        active_load <= 0;
                        response(8'hd2, 0);
                    end
                end
                8'h53: begin
                    if (request_length != 0) failure(1);
                    else begin
                        body[0] <= 1;
                        body[1] <= {1'b0,diagnostic_loopback,exhausted,rx_flow_fault,sync_locked,packet_ready,message_ready,tx_busy};
                        body[2] <= session_id[31:24];
                        body[3] <= session_id[23:16];
                        body[4] <= session_id[15:8];
                        body[5] <= session_id[7:0];
                        body[6] <= generation[31:24];
                        body[7] <= generation[23:16];
                        body[8] <= generation[15:8];
                        body[9] <= generation[7:0];
                        body[10] <= packet_seq[15:8];
                        body[11] <= packet_seq[7:0];
                        body[12] <= packet_length[15:8];
                        body[13] <= packet_length[7:0];
                        body[14] <= loaded[15:8];
                        body[15] <= loaded[7:0];
                        body[16] <= {5'b0,last_tx_error};
                        body[17] <= {5'b0,last_rx_error};
                        response(8'hd3, 18);
                    end
                end
                8'h54: begin
                    if (request_length != 11 || args[10] == 0 || args[10] > 128 || read_end > {1'b0,packet_length}) failure(1);
                    else if (!packet_ready) failure(4);
                    else if (!ticket_ok) failure(5);
                    else begin
                        body[0] <= session_id[31:24];
                        body[1] <= session_id[23:16];
                        body[2] <= session_id[15:8];
                        body[3] <= session_id[7:0];
                        body[4] <= generation[31:24];
                        body[5] <= generation[23:16];
                        body[6] <= generation[15:8];
                        body[7] <= generation[7:0];
                        body[8] <= packet_seq[15:8];
                        body[9] <= packet_seq[7:0];
                        body[10] <= packet_length[15:8];
                        body[11] <= packet_length[7:0];
                        body[12] <= read_offset[15:8];
                        body[13] <= read_offset[7:0];
                        read_index <= 0;
                        state <= READ;
                    end
                end
                8'h55: begin
                    if (request_length != 8) failure(1);
                    else if (!packet_ready) failure(4);
                    else if (!ticket_ok) failure(5);
                    else begin
                        release_packet <= 1;
                        response(8'hd5, 0);
                    end
                end
                8'h56: begin
                    if (request_length != 1 || args[0] == 0 || (args[0] & 8'hfc) != 0) failure(1);
                    else begin
                        tx_abort <= args[0][0];
                        rx_abort <= args[0][1];
                        if (args[0][0]) begin
                            active_load <= 0;
                            loaded <= 0;
                        end
                        response(8'hd6, 0);
                    end
                end
                8'h57: begin
                    if (request_length == 0) state <= CONFIG_REPLY;
                    else if (request_length != 8) failure(1);
                    else if (tx_busy || packet_ready || sync_locked) failure(2);
                    else begin
                        peak_config <= {args[0],args[1],args[2],args[3]};
                        margin_config <= {args[4],args[5],args[6],args[7]};
                        state <= CONFIG_REPLY;
                    end
                end
                8'h58: begin
                    if (!PROFILE_RF || request_length > 1 || (request_length == 1 && args[0] > 1)) failure(1);
                    else if (request_length == 1 && (tx_busy || packet_ready || sync_locked)) failure(2);
                    else begin
                        body[0] <= 1;
                        body[1] <= request_length == 1 ? args[0] : {7'b0,diagnostic_loopback};
                        if (request_length == 1 && diagnostic_loopback != args[0][0]) begin
                            diagnostic_loopback <= args[0][0];
                            rx_abort <= 1;
                        end
                        response(8'hd8, 2);
                    end
                end
                default: failure(1);
            endcase
            CONFIG_REPLY: begin
                body[0] <= 1;
                body[1] <= {6'b0,diagnostic_loopback,(PROFILE_RF != 0)};
                body[2] <= CENTER[31:24];
                body[3] <= CENTER[23:16];
                body[4] <= CENTER[15:8];
                body[5] <= CENTER[7:0];
                body[6] <= BANDWIDTH[31:24];
                body[7] <= BANDWIDTH[23:16];
                body[8] <= BANDWIDTH[15:8];
                body[9] <= BANDWIDTH[7:0];
                body[10] <= RF_RATE[31:24];
                body[11] <= RF_RATE[23:16];
                body[12] <= RF_RATE[15:8];
                body[13] <= RF_RATE[7:0];
                body[14] <= BASE_RATE[31:24];
                body[15] <= BASE_RATE[23:16];
                body[16] <= BASE_RATE[15:8];
                body[17] <= BASE_RATE[7:0];
                body[18] <= POINTS[15:8];
                body[19] <= POINTS[7:0];
                body[20] <= peak_config[31:24];
                body[21] <= peak_config[23:16];
                body[22] <= peak_config[15:8];
                body[23] <= peak_config[7:0];
                body[24] <= margin_config[31:24];
                body[25] <= margin_config[23:16];
                body[26] <= margin_config[15:8];
                body[27] <= margin_config[7:0];
                response(8'hd7, 28);
            end
            BEGIN_WAIT: begin
                if (wait_count >= 2 && ((planned == 0 && message_ready) || (planned != 0 && load_ready))) response(8'hd0, 0);
                else if (wait_count == 7) begin
                    active_load <= 0;
                    tx_abort <= 1;
                    failure(6);
                end
                else wait_count <= wait_count + 1'b1;
            end
            WRITE: begin
                if (load_ready) begin
                    wait_count <= 0;
                    if (write_index == request_length - 3) begin
                        loaded <= write_end[15:0];
                        body[0] <= write_end[15:8];
                        body[1] <= write_end[7:0];
                        response(8'hd1, 2);
                    end
                    else write_index <= write_index + 1'b1;
                end
                else if (wait_count == 7) begin
                    active_load <= 0;
                    tx_abort <= 1;
                    failure(6);
                end
                else wait_count <= wait_count + 1'b1;
            end
            READ: begin
                if (!read_valid || !ticket_ok) failure(6);
                else begin
                    body[read_index + 14] <= read_data;
                    if (read_index == args[10] - 1) response(8'hd4, {1'b0,args[10]} + 9'd14);
                    else read_index <= read_index + 1'b1;
                end
            end
            REPLY: if (tx_ready) begin
                if (tx_pos >= 2 && tx_pos < body_length + 6) crc <= crc_byte(crc, tx_data);
                if (tx_pos == body_length + 7) begin
                    state <= RX;
                    tx_pos <= 0;
                end
                else tx_pos <= tx_pos + 1'b1;
            end
            default: state <= RX;
        endcase
    end
end

endmodule
