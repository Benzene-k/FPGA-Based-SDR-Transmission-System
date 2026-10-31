module uart_tx_byte #(
        parameter   CLK_FREQ = 50_000_000,
        parameter   BAUD = 115_200
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    [7:0]   data,
        input   wire    valid,
        output  wire    ready,
        output  wire    tx
);

localparam  BIT_CYCLES = CLK_FREQ / BAUD;
localparam  CW = $clog2(BIT_CYCLES);

reg busy;
reg [9:0]   shift;
reg [3:0]   bit_index;
reg [CW-1:0]    timer;

assign  ready = !busy;
assign  tx = busy ? shift[0] : 1'b1;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        busy <= 0;
        shift <= 10'h3ff;
        bit_index <= 0;
        timer <= 0;
    end
    else if (!busy) begin
        if (valid) begin
            shift <= {1'b1, data, 1'b0};
            busy <= 1;
            bit_index <= 0;
            timer <= 0;
        end
    end
    else if (timer == BIT_CYCLES - 1) begin
        timer <= 0;
        if (bit_index == 9) busy <= 0;
        else begin
            shift <= {1'b1, shift[9:1]};
            bit_index <= bit_index + 1'b1;
        end
    end
    else        timer <= timer + 1'b1;
end

endmodule
