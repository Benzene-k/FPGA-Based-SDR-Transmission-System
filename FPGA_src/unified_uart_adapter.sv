module unified_uart_adapter #(
        parameter   FRAME_TIMEOUT_CYCLES = 5000000,
        parameter   ENABLE_EXTERNAL = 0,
        parameter   CAPTURE_RATE = 50000000,
        parameter   ENABLE_MESSAGE = 0
)(
        input   wire    clk,
        input   wire    cap_clk,
        input   wire    rst_n,
        input   wire    [31:0]  session_id,
        input   wire    [7:0]   external_data,
        input   wire    [7:0]   rx_data,
        input   wire    rx_valid,
        input   wire    rx_framing_error,
        output  wire    [7:0]   tx_data,
        output  wire    tx_valid,
        input   wire    tx_ready,
        output  wire    cmd_start,
        output  wire    cmd_stop,
        output  wire    cmd_reset,
        output  wire    requested_running,
        output  reg     [15:0]  crc_errors,
        output  reg     [15:0]  length_errors,
        output  reg     [15:0]  timeouts,
        output  wire    [7:0]   message_rx_data,
        output  wire    message_rx_valid,
        input   wire    [7:0]   message_tx_data,
        input   wire    message_tx_valid,
        output  wire    message_tx_ready
);

(* ASYNC_REG="TRUE" *) reg [1:0]   reset_pipe;

always  @(posedge clk or negedge rst_n)
    if (!rst_n) reset_pipe <= 0;
    else        reset_pipe <= {reset_pipe[0], 1'b1};

wire    reset_ready = reset_pipe[1];

function automatic [15:0] crc_byte(input [15:0] seed, input [7:0] value);
        reg [15:0] c;
        integer i;
        begin
            c = seed ^ {value, 8'd0};
            for (i = 0; i < 8; i = i + 1) c = c[15] ? (c << 1) ^ 16'h1021 : c << 1;
            crc_byte = c;
        end
endfunction

localparam  H0 = 0, H1 = 1, TYPE = 2, SEQ = 3, LH = 4, LL = 5, PAYLOAD = 6, CH = 7, CL = 8;
localparam  IDLE = 0, FORWARD = 1, REPLY = 2;

reg [3:0]   parser;
reg [1:0]   engine;
reg [7:0]   packet[0:263];
reg [7:0]   request_type, crc_high;
reg [15:0]  length, rx_crc;
reg [8:0]   write_pos, accepted_length, replay_pos, tx_pos;
reg [15:0]  reply_length;
reg [31:0]  timer;
reg blocked, pending;
reg [1:0]   accepted_target, target;

wire    active = engine != IDLE || pending;

integer i;

always  @(posedge clk or negedge reset_ready) begin
    if (!reset_ready) begin
        parser <= H0;
        request_type <= 0;
        crc_high <= 0;
        length <= 0;
        rx_crc <= 16'hffff;
        write_pos <= 0;
        accepted_length <= 0;
        timer <= 0;
        blocked <= 0;
        pending <= 0;
        accepted_target <= 0;
        crc_errors <= 0;
        length_errors <= 0;
        timeouts <= 0;
        for (i = 0; i < 264; i = i + 1) packet[i] <= 0;
    end
    else begin
        pending <= 0;
        if (rx_framing_error) begin
            parser <= H0;
            timer <= 0;
        end
        else if (rx_valid) begin
            timer <= 0;
            case (parser)
                H0: if (rx_data == 8'haa) parser <= H1;
                H1: begin
                    if (rx_data == 8'h55) parser <= TYPE;
                    else if (rx_data != 8'haa) parser <= H0;
                end
                TYPE: begin
                    request_type <= rx_data;
                    rx_crc <= crc_byte(16'hffff, rx_data);
                    blocked <= active;
                    parser <= SEQ;
                    if (!active) begin
                        packet[0] <= 8'haa;
                        packet[1] <= 8'h55;
                        packet[2] <= rx_data;
                    end
                end
                SEQ: begin
                    if (!blocked) packet[3] <= rx_data;
                    rx_crc <= crc_byte(rx_crc, rx_data);
                    parser <= LH;
                end
                LH: begin
                    if (!blocked) packet[4] <= rx_data;
                    length[15:8] <= rx_data;
                    rx_crc <= crc_byte(rx_crc, rx_data);
                    parser <= LL;
                end
                LL: begin
                    if (!blocked) packet[5] <= rx_data;
                    length[7:0] <= rx_data;
                    rx_crc <= crc_byte(rx_crc, rx_data);
                    write_pos <= 6;
                    if ({length[15:8], rx_data} > 256) begin
                        length_errors <= length_errors + 1'b1;
                        parser <= rx_data == 8'haa ? H1 : H0;
                    end
                    else        parser <= {length[15:8], rx_data} == 0 ? CH : PAYLOAD;
                end
                PAYLOAD: begin
                    if (!blocked) packet[write_pos] <= rx_data;
                    rx_crc <= crc_byte(rx_crc, rx_data);
                    write_pos <= write_pos + 1'b1;
                    if (write_pos == length + 5) parser <= CH;
                end
                CH: begin
                    if (!blocked) packet[write_pos] <= rx_data;
                    write_pos <= write_pos + 1'b1;
                    crc_high <= rx_data;
                    parser <= CL;
                end
                CL: begin
                    parser <= H0;
                    if ({crc_high, rx_data} != rx_crc) begin
                        crc_errors <= crc_errors + 1'b1;
                        if (rx_data == 8'haa) parser <= H1;
                    end
                    else if (!blocked && !active) begin
                        packet[write_pos] <= rx_data;
                        accepted_length <= length + 8;
                        accepted_target <= (ENABLE_MESSAGE && request_type >= 8'h50 && request_type <= 8'h58) ? 2 :
                            ((request_type >= 8'h40 && request_type <= 8'h4b) ? 1 : 0);
                        pending <= 1;
                    end
                end
                default: parser <= H0;
            endcase
        end
        else if (parser != H0) begin
            if (timer == FRAME_TIMEOUT_CYCLES - 1) begin
                parser <= H0;
                timer <= 0;
                timeouts <= timeouts + 1'b1;
            end
            else        timer <= timer + 1'b1;
        end
    end
end

wire    [7:0]   legacy_data, digital_data;
wire    legacy_valid, digital_valid;
wire    replay_valid = engine == FORWARD;
wire    [7:0]   replay_data = packet[replay_pos];

uart_protocol #(.FRAME_TIMEOUT_CYCLES(FRAME_TIMEOUT_CYCLES)) legacy(
        .clk(clk),
        .rst_n(reset_ready),
        .rx_data(replay_data),
        .rx_valid(replay_valid && target == 0),
        .rx_framing_error(1'b0),
        .tx_data(legacy_data),
        .tx_valid(legacy_valid),
        .tx_ready(tx_ready && engine == REPLY && target == 0),
        .cmd_start(cmd_start),
        .cmd_stop(cmd_stop),
        .cmd_reset(cmd_reset),
        .requested_running(requested_running),
        .crc_error_count(),
        .length_error_count(),
        .timeout_count()
);

digital_uart_adapter #(.FRAME_TIMEOUT_CYCLES(FRAME_TIMEOUT_CYCLES), .ENABLE_EXTERNAL(ENABLE_EXTERNAL), .CAPTURE_RATE(CAPTURE_RATE)) digital(
        .clk(clk),
        .cap_clk(cap_clk),
        .external_data(external_data),
        .rst_n(reset_ready),
        .session_id(session_id),
        .rx_data(replay_data),
        .rx_valid(replay_valid && target == 1),
        .rx_framing_error(1'b0),
        .tx_data(digital_data),
        .tx_valid(digital_valid),
        .tx_ready(tx_ready && engine == REPLY && target == 1),
        .crc_errors(),
        .length_errors(),
        .timeouts()
);

assign  message_rx_data = replay_data;
assign  message_rx_valid = ENABLE_MESSAGE && replay_valid && target == 2;
assign  message_tx_ready = ENABLE_MESSAGE && tx_ready && engine == REPLY && target == 2;
assign  tx_data = (target == 2) ? message_tx_data : ((target == 1) ? digital_data : legacy_data);
assign  tx_valid = engine == REPLY && ((target == 2) ? message_tx_valid : ((target == 1) ? digital_valid : legacy_valid));

always  @(posedge clk or negedge reset_ready) begin
    if (!reset_ready) begin
        engine <= IDLE;
        target <= 0;
        replay_pos <= 0;
        tx_pos <= 0;
        reply_length <= 0;
    end
    else begin
        case (engine)
            IDLE: if (pending) begin
                target <= accepted_target;
                replay_pos <= 0;
                engine <= FORWARD;
            end
            FORWARD: if (replay_pos == accepted_length - 1'b1) begin
                engine <= REPLY;
                tx_pos <= 0;
                reply_length <= 0;
            end
            else        replay_pos <= replay_pos + 1'b1;
            REPLY: if (tx_valid && tx_ready) begin
                if (tx_pos == 4) reply_length[15:8] <= tx_data;
                if (tx_pos == 5) reply_length[7:0] <= tx_data;
                if (tx_pos >= 7 && tx_pos == reply_length + 7) engine <= IDLE;
                else        tx_pos <= tx_pos + 1'b1;
            end
            default: engine <= IDLE;
        endcase
    end
end

endmodule
