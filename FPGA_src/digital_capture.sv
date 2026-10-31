module digital_capture #(
        parameter   ENABLE_EXTERNAL = 0
)(
        input   wire    ctrl_clk,
        input   wire    cap_clk,
        input   wire    arst_n,
        input   wire    start,
        input   wire    cancel,
        input   wire    release_req,
        input   wire    [12:0]  requested_count,
        input   wire    [1:0]   source,
        input   wire    [7:0]   fixed_code,
        input   wire    [7:0]   external_data,
        input   wire    rd_req,
        input   wire    [12:0]  rd_addr,
        output  reg     busy,
        output  reg     valid,
        output  reg     cancelled,
        output  reg     rejected,
        output  reg     [12:0]  actual_count,
        output  reg     [31:0]  capture_id,
        output  reg     [31:0]  crc32,
        output  reg     rd_valid,
        output  reg     rd_error,
        output  reg     [15:0]  rd_data
);

(* ASYNC_REG="TRUE" *) reg [1:0]   ctrl_reset_sync, cap_reset_sync;

always  @(posedge ctrl_clk or negedge arst_n)
    if (!arst_n) ctrl_reset_sync <= 0;
    else        ctrl_reset_sync <= {ctrl_reset_sync[0], 1'b1};

always  @(posedge cap_clk or negedge arst_n)
    if (!arst_n) cap_reset_sync <= 0;
    else        cap_reset_sync <= {cap_reset_sync[0], 1'b1};

wire    ctrl_rst_n = ctrl_reset_sync[1], cap_rst_n = cap_reset_sync[1];

reg request_toggle, cancel_toggle, cancel_sent, completion_pending;
reg [12:0]  held_count;
reg [1:0]   held_source;
reg [7:0]   held_fixed;
(* ASYNC_REG="TRUE" *) reg [1:0]   request_pipe, cancel_pipe, done_pipe, cancel_ack_pipe;
reg start_seen, cancel_seen, done_toggle, done_seen;
reg cap_active;
reg [12:0]  write_count, cap_limit, result_count;
reg [1:0]   cap_source;
reg [7:0]   cap_fixed;
reg [31:0]  running_crc, result_crc;
reg result_cancelled;
(* ram_style="block" *) reg [15:0]  memory[0:4095];

wire    [7:0]   sample_value = cap_source == 0 ? write_count[7:0] :
                               cap_source == 1 ? cap_fixed : cap_source == 2 ? (8'h01 << write_count[2:0]) : external_data;
wire    cancel_waiting = cancel_pipe[1] != cancel_seen;
wire    valid_count = requested_count == 256 || requested_count == 1024 || requested_count == 4096;
wire    legal_read = !busy && valid && rd_addr < actual_count && !start && !release_req;

function automatic [31:0] crc_byte(input [31:0] seed, input [7:0] value);
        reg [31:0] c;
        integer i;
        begin
            c = seed ^ {24'd0, value};
            for (i = 0; i < 8; i = i + 1) c = c[0] ? (c >> 1) ^ 32'hedb88320 : c >> 1;
            crc_byte = c;
        end
endfunction

wire    [31:0]  next_crc = crc_byte(crc_byte(running_crc, sample_value), 8'd0);

always  @(posedge cap_clk)
    if (cap_active && !cancel_waiting)
        memory[write_count[11:0]] <= {8'd0, sample_value};

always  @(posedge ctrl_clk)
    if (rd_req && legal_read) rd_data <= memory[rd_addr[11:0]];

always  @(posedge cap_clk) begin
    if (!cap_rst_n) begin
        request_pipe <= 0;
        cancel_pipe <= 0;
        start_seen <= 0;
        cancel_seen <= 0;
        done_toggle <= 0;
        cap_active <= 0;
        write_count <= 0;
        cap_limit <= 0;
        cap_source <= 0;
        cap_fixed <= 0;
        running_crc <= 32'hffffffff;
        result_crc <= 0;
        result_count <= 0;
        result_cancelled <= 0;
    end
    else begin
        request_pipe <= {request_pipe[0], request_toggle};
        cancel_pipe <= {cancel_pipe[0], cancel_toggle};
        if (request_pipe[1] != start_seen) begin
            start_seen <= request_pipe[1];
            cap_limit <= held_count;
            cap_source <= held_source;
            cap_fixed <= held_fixed;
            write_count <= 0;
            running_crc <= 32'hffffffff;
            cap_active <= 1;
        end
        else if (cap_active) begin
            if (cancel_waiting) begin
                cancel_seen <= cancel_pipe[1];
                cap_active <= 0;
                result_count <= write_count;
                result_crc <= running_crc ^ 32'hffffffff;
                result_cancelled <= 1;
                done_toggle <= ~done_toggle;
            end
            else begin
                write_count <= write_count + 1'b1;
                running_crc <= next_crc;
                if (write_count == cap_limit - 1'b1) begin
                    cap_active <= 0;
                    result_count <= cap_limit;
                    result_crc <= next_crc ^ 32'hffffffff;
                    result_cancelled <= 0;
                    done_toggle <= ~done_toggle;
                end
            end
        end
        else        cancel_seen <= cancel_pipe[1];
    end
end

always  @(posedge ctrl_clk) begin
    if (!ctrl_rst_n) begin
        done_pipe <= 0;
        cancel_ack_pipe <= 0;
        done_seen <= 0;
        request_toggle <= 0;
        cancel_toggle <= 0;
        cancel_sent <= 0;
        completion_pending <= 0;
        held_count <= 0;
        held_source <= 0;
        held_fixed <= 0;
        busy <= 0;
        valid <= 0;
        cancelled <= 0;
        rejected <= 0;
        actual_count <= 0;
        capture_id <= 0;
        crc32 <= 0;
        rd_valid <= 0;
        rd_error <= 0;
    end
    else begin
        done_pipe <= {done_pipe[0], done_toggle};
        cancel_ack_pipe <= {cancel_ack_pipe[0], cancel_seen};
        rejected <= 0;
        rd_valid <= 0;
        rd_error <= 0;
        if (rd_req) begin
            if (legal_read) rd_valid <= 1;
            else        rd_error <= 1;
        end
        if (start) begin
            if (busy || valid || cancelled || !valid_count ||
                (!ENABLE_EXTERNAL && source == 3) || capture_id == 32'hffffffff)
                rejected <= 1;
            else begin
                held_count <= requested_count;
                held_source <= source;
                held_fixed <= fixed_code;
                capture_id <= capture_id + 1'b1;
                request_toggle <= ~request_toggle;
                busy <= 1;
                valid <= 0;
                cancelled <= 0;
                actual_count <= 0;
                crc32 <= 0;
                cancel_sent <= 0;
                completion_pending <= 0;
            end
        end
        else if (release_req) begin
            if (busy) rejected <= 1;
            else begin
                valid <= 0;
                cancelled <= 0;
                actual_count <= 0;
                crc32 <= 0;
            end
        end
        if (cancel && busy && !cancel_sent) begin
            cancel_toggle <= ~cancel_toggle;
            cancel_sent <= 1;
        end
        if (busy && done_pipe[1] != done_seen) begin
            done_seen <= done_pipe[1];
            completion_pending <= 1;
            actual_count <= result_count;
            crc32 <= result_crc;
            cancelled <= result_cancelled;
        end
        if (busy && completion_pending && !cancel &&
            (!cancel_sent || cancel_ack_pipe[1] == cancel_toggle)) begin
            busy <= 0;
            valid <= actual_count != 0;
            completion_pending <= 0;
        end
    end
end

endmodule
