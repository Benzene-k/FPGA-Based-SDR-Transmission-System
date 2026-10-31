module uart_tx #(
        parameter   CLK_FREQ = 50_000_000,
        parameter   BAUD      = 115_200
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    [7:0]   data,
        input   wire    send,
        output  wire    ready,
        output  reg     tx
);

localparam  [15:0] DIV = (CLK_FREQ / BAUD) - 1;

localparam  [2:0] S_IDLE  = 3'd0;
localparam  [2:0] S_START = 3'd1;
localparam  [2:0] S_DATA  = 3'd2;
localparam  [2:0] S_STOP  = 3'd3;

reg [7:0]  fifo [0:15];
reg [4:0]  wptr;
reg [4:0]  rptr;
reg [4:0]  fifo_cnt;

wire    fifo_full  = (fifo_cnt == 5'd16);
wire    fifo_empty = (fifo_cnt == 5'd0);

assign  ready = !fifo_full;

reg [2:0]  state;
reg [15:0] clk_cnt;
reg [2:0]  bit_idx;
reg [7:0]  data_reg;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        wptr     <= 5'd0;
        rptr     <= 5'd0;
        fifo_cnt <= 5'd0;
    end
    else begin
        if (send && !fifo_full) begin
            fifo[wptr[3:0]] <= data;
            wptr            <= wptr + 5'd1;
            fifo_cnt        <= fifo_cnt + 5'd1;
        end
        if (state == S_IDLE && !fifo_empty) begin
            rptr     <= rptr + 5'd1;
            fifo_cnt <= fifo_cnt - 5'd1;
        end
    end
end

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state    <= S_IDLE;
        clk_cnt  <= 16'd0;
        bit_idx  <= 3'd0;
        data_reg <= 8'd0;
        tx       <= 1'b1;
    end
    else begin
        case (state)
            S_IDLE: begin
                tx <= 1'b1;
                if (!fifo_empty) begin
                    data_reg <= fifo[rptr[3:0]];
                    clk_cnt  <= 16'd0;
                    state    <= S_START;
                end
            end

            S_START: begin
                tx <= 1'b0;
                if (clk_cnt == DIV) begin
                    clk_cnt <= 16'd0;
                    bit_idx <= 3'd0;
                    state   <= S_DATA;
                end
                else begin
                    clk_cnt <= clk_cnt + 16'd1;
                end
            end

            S_DATA: begin
                tx <= data_reg[bit_idx];
                if (clk_cnt == DIV) begin
                    clk_cnt <= 16'd0;
                    if (bit_idx == 3'd7) begin
                        state <= S_STOP;
                    end
                    else begin
                        bit_idx <= bit_idx + 3'd1;
                    end
                end
                else begin
                    clk_cnt <= clk_cnt + 16'd1;
                end
            end

            S_STOP: begin
                tx <= 1'b1;
                if (clk_cnt == DIV) begin
                    clk_cnt <= 16'd0;
                    state   <= S_IDLE;
                end
                else begin
                    clk_cnt <= clk_cnt + 16'd1;
                end
            end

            default: state <= S_IDLE;
        endcase
    end
end

endmodule
