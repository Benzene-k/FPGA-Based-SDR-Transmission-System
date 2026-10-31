module uart_protocol #(
        parameter   FRAME_TIMEOUT_CYCLES = 5_000_000
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    [7:0]   rx_data,
        input   wire    rx_valid,
        input   wire    rx_framing_error,
        output  wire    [7:0]   tx_data,
        output  wire    tx_valid,
        input   wire    tx_ready,
        output  reg     cmd_start,
        output  reg     cmd_stop,
        output  reg     cmd_reset,
        output  reg     requested_running,
        output  reg     [15:0]  crc_error_count,
        output  reg     [15:0]  length_error_count,
        output  reg     [15:0]  timeout_count
);

localparam  H0 = 0, H1 = 1, TYPE = 2, SEQ = 3, LEN_H = 4, LEN_L = 5, PAYLOAD = 6, CRC_H = 7, CRC_L = 8;

reg [3:0]   state;
reg [7:0]   request_type, request_seq, len_hi, received_crc_hi;
reg [15:0]  payload_length, payload_left, crc;
reg [31:0]  idle_cycles;
reg [7:0]   reply_bytes[0:15];
reg [4:0]   reply_pos, reply_length;
reg reply_busy;
reg request_blocked;
reg [7:0]   echo_payload[0:255];
reg echo_busy;
reg [8:0]   echo_position, echo_length;
reg [7:0]   echo_sequence;
reg [15:0]  echo_crc;
reg [7:0]   echo_data;

wire    sending_reply = reply_busy || echo_busy;

reg [15:0]  config_frame, config_sync;
reg [31:0]  config_seed;
reg [7:0]   config_input[0:7];

wire    [15:0]  input_frame = {config_input[0], config_input[1]};
wire    [15:0]  input_sync = {config_input[2], config_input[3]};
wire    [31:0]  input_seed = {config_input[4], config_input[5], config_input[6], config_input[7]};

wire    config_valid = input_frame >= 2 && input_frame <= 4096 &&
                       input_sync >= 1 && input_sync <= 1024 && input_sync < input_frame &&
                       input_seed <= 32'h7fffffff;

integer r;

always  @(posedge clk) begin
    if (rst_n && rx_valid && !rx_framing_error && state == PAYLOAD &&
        !request_blocked && request_type == 8'h20)
        echo_payload[payload_length - payload_left] <= rx_data;
end

assign  tx_valid = sending_reply;
assign  tx_data = echo_busy ? echo_data : reply_bytes[reply_pos];

always  @* begin
    case (echo_position)
        0: echo_data = 8'haa;
        1: echo_data = 8'h55;
        2: echo_data = 8'h21;
        3: echo_data = echo_sequence;
        4: echo_data = {7'd0, echo_length[8]};
        5: echo_data = echo_length[7:0];
        default: begin
            if (echo_position < echo_length + 9'd6)
                echo_data = echo_payload[echo_position - 9'd6];
            else if (echo_position == echo_length + 9'd6) echo_data = echo_crc[15:8];
            else echo_data = echo_crc[7:0];
        end
    endcase
end

function [15:0] crc_byte;
    input [15:0] seed;
    input [7:0] value;
    reg [15:0] c;
    integer i;
    begin
        c = seed ^ {value, 8'h00};
        for (i = 0; i < 8; i = i + 1) c = c[15] ? (c << 1) ^ 16'h1021 : c << 1;
        crc_byte = c;
    end
endfunction

task make_reply;
    input [7:0] kind;
    input [2:0] count;
    input [31:0] payload;
    reg [15:0] checksum;
    reg [7:0] value;
    integer j;
    begin
        reply_bytes[0] <= 8'haa;
        reply_bytes[1] <= 8'h55;
        reply_bytes[2] <= kind;
        reply_bytes[3] <= request_seq;
        reply_bytes[4] <= 0;
        reply_bytes[5] <= {5'b0, count};
        checksum = crc_byte(16'hffff, kind);
        checksum = crc_byte(checksum, request_seq);
        checksum = crc_byte(checksum, 0);
        checksum = crc_byte(checksum, {5'b0, count});
        for (j = 0; j < 4; j = j + 1)
            if (j < count) begin
                value = payload >> (24 - j * 8);
                reply_bytes[6 + j] <= value;
                checksum = crc_byte(checksum, value);
            end
        reply_bytes[6 + count] <= checksum[15:8];
        reply_bytes[7 + count] <= checksum[7:0];
        reply_pos <= 0;
        reply_length <= 8 + count;
        reply_busy <= 1;
    end
endtask

task config_reply;
    input [63:0] payload;
    reg [15:0] checksum;
    reg [7:0] value;
    integer j;
    begin
        reply_bytes[0] <= 8'haa;
        reply_bytes[1] <= 8'h55;
        reply_bytes[2] <= 8'h31;
        reply_bytes[3] <= request_seq;
        reply_bytes[4] <= 0;
        reply_bytes[5] <= 8;
        checksum = crc_byte(16'hffff, 8'h31);
        checksum = crc_byte(checksum, request_seq);
        checksum = crc_byte(checksum, 0);
        checksum = crc_byte(checksum, 8);
        for (j = 0; j < 8; j = j + 1) begin
            value = payload >> (56 - j * 8);
            reply_bytes[6 + j] <= value;
            checksum = crc_byte(checksum, value);
        end
        reply_bytes[14] <= checksum[15:8];
        reply_bytes[15] <= checksum[7:0];
        reply_pos <= 0;
        reply_length <= 16;
        reply_busy <= 1;
    end
endtask

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state <= H0;
        request_type <= 0;
        request_seq <= 0;
        len_hi <= 0;
        received_crc_hi <= 0;
        payload_length <= 0;
        payload_left <= 0;
        crc <= 16'hffff;
        idle_cycles <= 0;
        reply_busy <= 0;
        reply_pos <= 0;
        reply_length <= 0;
        request_blocked <= 0;
        echo_busy <= 0;
        echo_position <= 0;
        echo_length <= 0;
        echo_sequence <= 0;
        echo_crc <= 16'hffff;
        cmd_start <= 0;
        cmd_stop <= 0;
        cmd_reset <= 0;
        requested_running <= 0;
        crc_error_count <= 0;
        length_error_count <= 0;
        timeout_count <= 0;
        config_frame <= 16'd30;
        config_sync <= 16'd13;
        config_seed <= 32'd20260919;
        for (r = 0; r < 8; r = r + 1) config_input[r] <= 0;
        for (r = 0; r < 16; r = r + 1) reply_bytes[r] <= 0;
    end
    else begin
        cmd_start <= 0;
        cmd_stop <= 0;
        cmd_reset <= 0;
        if (echo_busy && tx_ready) begin
            if (echo_position >= 2 && echo_position < echo_length + 9'd6)
                echo_crc <= crc_byte(echo_crc, echo_data);
            if (echo_position == echo_length + 9'd7) echo_busy <= 0;
            else        echo_position <= echo_position + 1'b1;
        end
        if (reply_busy && tx_ready) begin
            if (reply_pos == reply_length - 1) reply_busy <= 0;
            else        reply_pos <= reply_pos + 1'b1;
        end
        if (state == H0 || rx_valid) idle_cycles <= 0;
        else        idle_cycles <= idle_cycles + 1'b1;

        if (rx_framing_error) begin
            state <= H0;
            idle_cycles <= 0;
        end
        else if (state != H0 && !rx_valid && idle_cycles >= FRAME_TIMEOUT_CYCLES - 1) begin
            state <= H0;
            idle_cycles <= 0;
            timeout_count <= timeout_count + 1'b1;
        end
        else if (rx_valid) begin
            case (state)
                H0: if (rx_data == 8'haa) state <= H1;
                H1: begin
                    if (rx_data == 8'h55) state <= TYPE;
                    else if (rx_data != 8'haa) state <= H0;
                end
                TYPE: begin
                    request_type <= rx_data;
                    crc <= crc_byte(16'hffff, rx_data);
                    state <= SEQ;
                    request_blocked <= sending_reply;
                end
                SEQ: begin
                    request_seq <= rx_data;
                    crc <= crc_byte(crc, rx_data);
                    state <= LEN_H;
                end
                LEN_H: begin
                    len_hi <= rx_data;
                    crc <= crc_byte(crc, rx_data);
                    state <= LEN_L;
                end
                LEN_L: begin
                    crc <= crc_byte(crc, rx_data);
                    if ({len_hi, rx_data} > 16'd256) begin
                        length_error_count <= length_error_count + 1'b1;
                        state <= (rx_data == 8'haa) ? H1 : H0;
                    end
                    else begin
                        payload_length <= {len_hi, rx_data};
                        payload_left <= {len_hi, rx_data};
                        state <= ({len_hi, rx_data} == 0) ? CRC_H : PAYLOAD;
                    end
                end
                PAYLOAD: begin
                    if (!request_blocked && request_type == 8'h32 && payload_length == 8)
                        config_input[8 - payload_left] <= rx_data;
                    crc <= crc_byte(crc, rx_data);
                    if (payload_left == 1) state <= CRC_H;
                    else        payload_left <= payload_left - 1'b1;
                end
                CRC_H: begin
                    received_crc_hi <= rx_data;
                    state <= CRC_L;
                end
                CRC_L: begin
                    state <= H0;
                    if ({received_crc_hi, rx_data} != crc) begin
                        crc_error_count <= crc_error_count + 1'b1;
                        if (rx_data == 8'haa) state <= H1;
                    end
                    else if (!sending_reply && !request_blocked) begin
                        if (request_type != 8'h01 && request_type != 8'h12 && request_type != 8'h13 &&
                            request_type != 8'h14 && request_type != 8'h20 && request_type != 8'h30 &&
                            request_type != 8'h32)
                            make_reply(8'he0, 2, {request_type, 8'd1, 16'd0});
                        else if ((request_type == 8'h32 && payload_length != 8) ||
                                 (payload_length != 0 && request_type != 8'h20 && request_type != 8'h32))
                            make_reply(8'he0, 2, {request_type, 8'd2, 16'd0});
                        else case (request_type)
                            8'h01: make_reply(8'h02, 4, {8'd1, 8'd2, 8'd7, 7'd0, requested_running});
                            8'h30: config_reply({config_frame, config_sync, config_seed});
                            8'h32: begin
                                if (!config_valid) make_reply(8'he0, 2, {request_type, 8'd3, 16'd0});
                                else begin
                                    config_frame <= input_frame;
                                    config_sync <= input_sync;
                                    config_seed <= input_seed;
                                    config_reply({input_frame, input_sync, input_seed});
                                end
                            end
                            8'h20: begin
                                echo_busy <= 1;
                                echo_position <= 0;
                                echo_length <= payload_length[8:0];
                                echo_sequence <= request_seq;
                                echo_crc <= 16'hffff;
                            end
                            8'h12: begin
                                requested_running <= 1;
                                cmd_start <= 1;
                                make_reply(8'h80, 3, {request_type, 8'd0, 8'd1, 8'd0});
                            end
                            8'h13: begin
                                requested_running <= 0;
                                cmd_stop <= 1;
                                make_reply(8'h80, 3, {request_type, 8'd0, 16'd0});
                            end
                            8'h14: begin
                                requested_running <= 0;
                                cmd_reset <= 1;
                                make_reply(8'h80, 3, {request_type, 8'd0, 16'd0});
                            end
                        endcase
                    end
                end
                default: state <= H0;
            endcase
        end
    end
end

endmodule
