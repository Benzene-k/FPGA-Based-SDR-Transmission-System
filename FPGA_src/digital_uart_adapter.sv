module digital_uart_adapter #(
        parameter   FRAME_TIMEOUT_CYCLES = 5000000,
        parameter   ENABLE_EXTERNAL = 0,
        parameter   CAPTURE_RATE = 50000000
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
        output  reg     [15:0]  crc_errors,
        output  reg     [15:0]  length_errors,
        output  reg     [15:0]  timeouts
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

reg [3:0]   parser;
reg [7:0]   request_type, request_seq, crc_high;
reg [15:0]  request_length, rx_crc;
reg [8:0]   rx_pos;
reg [7:0]   arguments[0:11];
reg blocked, request_pending;
reg [31:0]  timer;
integer argument_reset;
wire    active;

always  @(posedge clk or negedge reset_ready) begin
    if (!reset_ready) begin
        parser <= H0;
        request_type <= 0;
        request_seq <= 0;
        request_length <= 0;
        rx_crc <= 16'hffff;
        rx_pos <= 0;
        crc_high <= 0;
        blocked <= 0;
        request_pending <= 0;
        timer <= 0;
        crc_errors <= 0;
        length_errors <= 0;
        timeouts <= 0;
        for (argument_reset = 0; argument_reset < 12; argument_reset = argument_reset + 1) arguments[argument_reset] <= 0;
    end
    else begin
        request_pending <= 0;
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
                end
                SEQ: begin
                    request_seq <= rx_data;
                    rx_crc <= crc_byte(rx_crc, rx_data);
                    parser <= LH;
                end
                LH: begin
                    request_length[15:8] <= rx_data;
                    rx_crc <= crc_byte(rx_crc, rx_data);
                    parser <= LL;
                end
                LL: begin
                    request_length[7:0] <= rx_data;
                    rx_crc <= crc_byte(rx_crc, rx_data);
                    rx_pos <= 0;
                    if ({request_length[15:8], rx_data} > 256) begin
                        length_errors <= length_errors + 1'b1;
                        parser <= H0;
                    end
                    else        parser <= rx_data == 0 && request_length[15:8] == 0 ? CH : PAYLOAD;
                end
                PAYLOAD: begin
                    if (!blocked && rx_pos < 12) arguments[rx_pos] <= rx_data;
                    rx_crc <= crc_byte(rx_crc, rx_data);
                    rx_pos <= rx_pos + 1'b1;
                    if (rx_pos == request_length - 1'b1) parser <= CH;
                end
                CH: begin
                    crc_high <= rx_data;
                    parser <= CL;
                end
                CL: begin
                    parser <= H0;
                    if ({crc_high, rx_data} != rx_crc) crc_errors <= crc_errors + 1'b1;
                    else if (!blocked && !active) request_pending <= 1;
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

reg start, cancel, release_req, rd_req;
reg [12:0]  planned, rd_addr;
reg [1:0]   source;
reg [7:0]   fixed_code;
wire    busy, valid, cancelled, rejected, rd_valid, rd_error;
wire    [12:0]  actual_count;
wire    [31:0]  capture_id, crc32;
wire    [15:0]  rd_data;

digital_capture #(.ENABLE_EXTERNAL(ENABLE_EXTERNAL)) capture(
        .external_data(external_data),
        .ctrl_clk(clk),
        .cap_clk(cap_clk),
        .arst_n(rst_n),
        .start(start),
        .cancel(cancel),
        .release_req(release_req),
        .requested_count(planned),
        .source(source),
        .fixed_code(fixed_code),
        .rd_req(rd_req),
        .rd_addr(rd_addr),
        .busy(busy),
        .valid(valid),
        .cancelled(cancelled),
        .rejected(rejected),
        .actual_count(actual_count),
        .capture_id(capture_id),
        .crc32(crc32),
        .rd_valid(rd_valid),
        .rd_error(rd_error),
        .rd_data(rd_data)
);

localparam  IDLE = 0, WAIT_START = 1, CANCEL_SETTLE = 2, WAIT_CANCEL = 3, WAIT_READ = 4, SEND = 5;

reg [2:0]   state;

assign  active = state != IDLE;

reg [31:0]  session;
reg session_latched;
reg [7:0]   reply_type, reply_seq;
reg [8:0]   reply_length, tx_pos;
reg [15:0]  tx_crc;
reg [7:0]   reply[0:251];
reg [6:0]   sample_index, block_count;
reg [12:0]  block_offset;

wire    [31:0]  arg_session = {arguments[0], arguments[1], arguments[2], arguments[3]};
wire    [31:0]  arg_capture = {arguments[4], arguments[5], arguments[6], arguments[7]};
wire    [15:0]  arg_offset = {arguments[8], arguments[9]};
wire    [15:0]  arg_count = {arguments[10], arguments[11]};
wire    [16:0]  block_end = {1'b0, arg_offset} + {1'b0, arg_count};
wire    [15:0]  arg_planned = {arguments[0], arguments[1]};
wire    [7:0]   capture_state = busy ? 1 : cancelled ? 3 : valid ? 2 : 0;

task identity_reply;
        begin
            {reply[0], reply[1], reply[2], reply[3]} <= session;
            {reply[4], reply[5], reply[6], reply[7]} <= capture_id;
        end
endtask

task send_reply(input [7:0] kind, input [8:0] length);
        begin
            reply_type <= kind;
            reply_length <= length;
            tx_pos <= 0;
            tx_crc <= 16'hffff;
            state <= SEND;
        end
endtask

task fail_reply(input [7:0] code);
        begin
            reply[0] <= request_type;
            reply[1] <= code;
            send_reply(8'he0, 2);
        end
endtask

task status_reply(input [7:0] kind);
        begin
            identity_reply();
            reply[8] <= capture_state;
            {reply[9], reply[10]} <= {3'd0, planned};
            {reply[11], reply[12]} <= {3'd0, actual_count};
            {reply[13], reply[14], reply[15], reply[16]} <= crc32;
            reply[17] <= {6'd0, source};
            reply[18] <= fixed_code;
            send_reply(kind, 19);
        end
endtask

reg [7:0]   outgoing;

always  @* begin
    case (tx_pos)
        0: outgoing = 8'haa;
        1: outgoing = 8'h55;
        2: outgoing = reply_type;
        3: outgoing = reply_seq;
        4: outgoing = {7'd0, reply_length[8]};
        5: outgoing = reply_length[7:0];
        default: begin
            if (tx_pos < reply_length + 6) outgoing = reply[tx_pos - 6];
            else if (tx_pos == reply_length + 6) outgoing = tx_crc[15:8];
            else        outgoing = tx_crc[7:0];
        end
    endcase
end

assign  tx_valid = state == SEND;
assign  tx_data = outgoing;

integer i;

always  @(posedge clk) begin
    if (!reset_ready) begin
        state <= IDLE;
        session <= 0;
        session_latched <= 0;
        start <= 0;
        cancel <= 0;
        release_req <= 0;
        rd_req <= 0;
        planned <= 0;
        source <= 0;
        fixed_code <= 0;
        rd_addr <= 0;
        reply_type <= 0;
        reply_seq <= 0;
        reply_length <= 0;
        tx_pos <= 0;
        tx_crc <= 16'hffff;
        sample_index <= 0;
        block_count <= 0;
        block_offset <= 0;
        for (i = 0; i < 252; i = i + 1) reply[i] <= 0;
    end
    else begin
        start <= 0;
        cancel <= 0;
        release_req <= 0;
        rd_req <= 0;
        if (!session_latched) begin
            session <= session_id;
            session_latched <= 1;
        end
        case (state)
            IDLE: if (request_pending) begin
                reply_seq <= request_seq;
                if (session == 0) fail_reply(3);
                else if (request_type == 8'h40) begin
                    if (request_length != 0) fail_reply(1);
                    else begin
                        {reply[0], reply[1], reply[2], reply[3]} <= 32'h41444454;
                        reply[4] <= 1;
                        reply[5] <= ENABLE_EXTERNAL ? 1 : 0;
                        {reply[6], reply[7], reply[8], reply[9]} <= session;
                        {reply[10], reply[11], reply[12], reply[13]} <= capture_id;
                        {reply[14], reply[15], reply[16], reply[17]} <= ENABLE_EXTERNAL ? 32'd3 : 32'd1;
                        reply[18] <= 8;
                        reply[19] <= 16;
                        reply[20] <= 0;
                        {reply[21], reply[22], reply[23], reply[24]} <= CAPTURE_RATE;
                        send_reply(8'h41, ENABLE_EXTERNAL ? 25 : 21);
                    end
                end
                else if (request_type == 8'h42) begin
                    if (request_length != 4 || (arg_planned != 256 && arg_planned != 1024 && arg_planned != 4096) ||
                        arguments[2] > (ENABLE_EXTERNAL ? 3 : 2) || (arguments[2] == 3 && arguments[3] != 0))
                        fail_reply(1);
                    else if (busy) fail_reply(2);
                    else if (valid || cancelled) fail_reply(5);
                    else if (capture_id == 32'hffffffff) fail_reply(8);
                    else begin
                        planned <= arg_planned[12:0];
                        source <= arguments[2][1:0];
                        fixed_code <= arguments[3];
                        start <= 1;
                        state <= WAIT_START;
                    end
                end
                else if (request_type != 8'h44 && request_type != 8'h46 &&
                    request_type != 8'h48 && request_type != 8'h4a) fail_reply(7);
                else if (request_length != (request_type == 8'h46 ? 12 : 8)) fail_reply(1);
                else if (arg_session != session) fail_reply(3);
                else if (arg_capture == 0 || arg_capture != capture_id) fail_reply(4);
                else if (!busy && !valid && !cancelled) fail_reply(5);
                else if (request_type == 8'h44) status_reply(8'h45);
                else if (request_type == 8'h48) begin
                    if (busy) begin
                        cancel <= 1;
                        state <= CANCEL_SETTLE;
                    end
                    else        status_reply(8'h49);
                end
                else if (busy) fail_reply(2);
                else if (request_type == 8'h4a) begin
                    release_req <= 1;
                    identity_reply();
                    send_reply(8'h4b, 8);
                end
                else if (arg_count == 0 || arg_count > 120 || block_end > {4'd0, actual_count}) fail_reply(6);
                else begin
                    identity_reply();
                    for (i = 8; i < 12; i = i + 1) reply[i] <= arguments[i];
                    block_offset <= arg_offset[12:0];
                    block_count <= arg_count[6:0];
                    sample_index <= 0;
                    rd_addr <= arg_offset[12:0];
                    rd_req <= 1;
                    state <= WAIT_READ;
                end
            end
            WAIT_START: if (busy) begin
                identity_reply();
                send_reply(8'h43, 8);
            end
            CANCEL_SETTLE: state <= WAIT_CANCEL;
            WAIT_CANCEL: if (!busy) status_reply(8'h49);
            WAIT_READ: begin
                if (rd_error) fail_reply(5);
                else if (rd_valid) begin
                    reply[12 + {sample_index, 1'b0}] <= rd_data[7:0];
                    reply[13 + {sample_index, 1'b0}] <= rd_data[15:8];
                    if (sample_index == block_count - 1'b1) send_reply(8'h47, 9'd12 + {block_count, 1'b0});
                    else begin
                        sample_index <= sample_index + 1'b1;
                        rd_addr <= block_offset + sample_index + 1'b1;
                        rd_req <= 1;
                    end
                end
            end
            SEND: if (tx_ready) begin
                if (tx_pos >= 2 && tx_pos < reply_length + 6) tx_crc <= crc_byte(tx_crc, outgoing);
                if (tx_pos == reply_length + 7) state <= IDLE;
                else        tx_pos <= tx_pos + 1'b1;
            end
            default: state <= IDLE;
        endcase
    end
end

endmodule
