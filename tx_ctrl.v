module tx_ctrl #(
        parameter   N = 4096
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    ext_start,
        input   wire    sym_done,
        input   wire    frame_done,
        input   wire    bit_valid,
        output  reg     frame_start,
        output  reg     bit_req,
        output  reg     sym_start,
        output  reg     tx_enable,
        output  reg     [7:0]   frame_seq,
        output  reg     busy
);

localparam  [2:0] S_IDLE     = 3'd0;
localparam  [2:0] S_FSTART   = 3'd1;
localparam  [2:0] S_REQ      = 3'd2;
localparam  [2:0] S_SYM_WAIT = 3'd3;
localparam  [2:0] S_GAP      = 3'd4;
localparam  [2:0] S_NEXT     = 3'd5;

reg [2:0]  state;
reg [15:0] gap_cnt;
reg        frame_done_latch;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state            <= S_IDLE;
        frame_start      <= 1'b0;
        bit_req          <= 1'b0;
        sym_start        <= 1'b0;
        tx_enable        <= 1'b0;
        gap_cnt          <= 16'd0;
        frame_seq        <= 8'd0;
        busy             <= 1'b0;
        frame_done_latch <= 1'b0;
    end
    else begin
        frame_start <= 1'b0;
        bit_req     <= 1'b0;
        sym_start   <= 1'b0;
        tx_enable   <= 1'b0;

        if (frame_done) frame_done_latch <= 1'b1;

        busy <= 1'b1;

        case (state)
            S_IDLE: begin
                busy <= 1'b0;
                if (ext_start) begin
                    frame_start      <= 1'b1;
                    frame_done_latch <= 1'b0;
                    state            <= S_FSTART;
                end
            end

            S_FSTART: begin
                state <= S_REQ;
            end

            S_REQ: begin
                bit_req <= 1'b1;
                if (bit_valid) begin
                    sym_start <= 1'b1;
                    tx_enable <= 1'b1;
                    state     <= S_SYM_WAIT;
                end
            end

            S_SYM_WAIT: begin
                tx_enable <= 1'b1;
                if (sym_done) begin
                    tx_enable <= 1'b0;
                    gap_cnt   <= 16'd0;
                    state     <= S_GAP;
                end
            end

            S_GAP: begin
                if (gap_cnt == 16'd63) begin
                    state <= S_NEXT;
                end
                else begin
                    gap_cnt <= gap_cnt + 16'd1;
                end
            end

            S_NEXT: begin
                if (frame_done_latch) begin
                    frame_seq        <= frame_seq + 8'd1;
                    frame_done_latch <= 1'b0;
                    state            <= S_IDLE;
                end
                else begin
                    state <= S_REQ;
                end
            end

            default: state <= S_IDLE;
        endcase
    end
end

endmodule
