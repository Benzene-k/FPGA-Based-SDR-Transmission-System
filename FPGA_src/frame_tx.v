module frame_tx #(
        parameter   SEED = 15'h7FFF
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    frame_start,
        input   wire    bit_req,
        output  reg     bit_out,
        output  reg     bit_valid,
        output  reg     frame_done
);

localparam  [7:0] SYNC_WORD = 8'hA7;

localparam  [3:0] S_IDLE    = 4'd0;
localparam  [3:0] S_PRE     = 4'd1;
localparam  [3:0] S_SYNC    = 4'd2;
localparam  [3:0] S_LEN     = 4'd3;
localparam  [3:0] S_PAYLOAD = 4'd4;
localparam  [3:0] S_CRC     = 4'd5;
localparam  [3:0] S_DONE    = 4'd6;

reg [3:0]  state;
reg [5:0]  bit_cnt;
reg [15:0] crc;
reg [15:0] crc_final;
reg        pre_bit;
reg [7:0]  sync_shift;

wire    prbs_bit;
wire    prbs_en = (state == S_PAYLOAD);

prbs_gen #(.SEED(SEED)) u_prbs(
        .clk(clk),
        .rst_n(rst_n),
        .en(prbs_en),
        .load(frame_start),
        .seed_val(SEED),
        .bit_out(prbs_bit)
);

wire    crc_in_bit = (state == S_PAYLOAD) ? prbs_bit : 1'b0;
wire    crc_msb = crc[15];
wire    [15:0]   crc_next = (crc << 1) ^ ((crc_msb ^ crc_in_bit) ? 16'h1021 : 16'h0);

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state      <= S_IDLE;
        bit_cnt    <= 6'd0;
        crc        <= 16'hFFFF;
        crc_final  <= 16'h0;
        pre_bit    <= 1'b0;
        sync_shift <= SYNC_WORD;
        bit_out    <= 1'b0;
        bit_valid  <= 1'b0;
        frame_done <= 1'b0;
    end
    else begin
        bit_valid  <= 1'b0;
        frame_done <= 1'b0;

        case (state)
            S_IDLE: begin
                if (frame_start) begin
                    state      <= S_PRE;
                    bit_cnt    <= 6'd0;
                    pre_bit    <= 1'b1;
                    crc        <= 16'hFFFF;
                    sync_shift <= SYNC_WORD;
                end
            end

            S_PRE: begin
                if (bit_req) begin
                    bit_out   <= pre_bit;
                    bit_valid <= 1'b1;
                    pre_bit   <= ~pre_bit;
                    bit_cnt   <= bit_cnt + 6'd1;
                    if (bit_cnt == 6'd3) begin
                        state   <= S_SYNC;
                        bit_cnt <= 6'd0;
                    end
                end
            end

            S_SYNC: begin
                if (bit_req) begin
                    bit_out    <= sync_shift[7];
                    bit_valid  <= 1'b1;
                    sync_shift <= {sync_shift[6:0], 1'b0};
                    bit_cnt    <= bit_cnt + 6'd1;
                    if (bit_cnt == 6'd7) begin
                        state   <= S_LEN;
                        bit_cnt <= 6'd0;
                    end
                end
            end

            S_LEN: begin
                if (bit_req) begin
                    bit_out   <= 1'b0;
                    bit_valid <= 1'b1;
                    crc       <= crc_next;
                    bit_cnt   <= bit_cnt + 6'd1;
                    if (bit_cnt == 6'd1) begin
                        state   <= S_PAYLOAD;
                        bit_cnt <= 6'd0;
                    end
                end
            end

            S_PAYLOAD: begin
                if (bit_req) begin
                    bit_out   <= prbs_bit;
                    bit_valid <= 1'b1;
                    crc       <= crc_next;
                    bit_cnt   <= bit_cnt + 6'd1;
                    if (bit_cnt == 6'd31) begin
                        state     <= S_CRC;
                        bit_cnt   <= 6'd0;
                        crc_final <= crc_next;
                    end
                end
            end

            S_CRC: begin
                if (bit_req) begin
                    bit_out   <= ~crc_final[15];
                    bit_valid <= 1'b1;
                    crc_final <= {crc_final[14:0], 1'b0};
                    bit_cnt   <= bit_cnt + 6'd1;
                    if (bit_cnt == 6'd15) begin
                        state <= S_DONE;
                    end
                end
            end

            S_DONE: begin
                frame_done <= 1'b1;
                state      <= S_IDLE;
            end

            default: state <= S_IDLE;
        endcase
    end
end

endmodule
