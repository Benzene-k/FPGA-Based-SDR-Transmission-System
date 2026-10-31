module sdr_top #(
        parameter   N = 4096,
        parameter   W = 16,
        parameter   DDS_LAT = 3,
        parameter   INC0 = 32'h0000_0000,
        parameter   STEP = 32'h0000_1000
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    ext_start,
        output  wire    uart_tx_pin,
        output  wire    [3:0]   led
);

localparam  SEED = 15'h7FFF;

wire    tx_busy;
wire    frame_start;
wire    bit_req;
wire    sym_start;
wire    tx_enable;
wire    [7:0]   tx_frame_seq;

wire    frame_bit_out;
wire    frame_bit_valid;
wire    frame_done;

wire    signed [W-1:0]  tx_i;
wire    signed [W-1:0]  tx_q;
wire    tx_valid;
wire    sym_done;

wire    rx_sym_start = sym_start;
wire    signed  [W-1:0] rx_i = tx_i;
wire    signed  [W-1:0] rx_q = tx_q;
wire    rx_valid = tx_valid;

wire    bit_out;
wire    bit_valid;

wire    sync_found;
wire    [5:0]   bit_idx;
wire    crc_ok;
wire    [15:0]  crc_reg;
wire    ber_valid;
wire    [15:0]  err_count;
wire    [15:0]  bit_count;

wire    [7:0]   uart_data;
wire    uart_send;
wire    uart_ready;

reg sync_latch;
reg crc_latch;
reg [23:0]  hb_cnt;
wire    heartbeat;

frame_tx #(.SEED(SEED)) u_frame_tx(
        .clk(clk),
        .rst_n(rst_n),
        .frame_start(frame_start),
        .bit_req(bit_req),
        .bit_out(frame_bit_out),
        .bit_valid(frame_bit_valid),
        .frame_done(frame_done)
);

chirp_mod #(.N(N), .INC0(INC0), .STEP(STEP))    u_chirp_mod(
        .clk(clk),
        .rst_n(rst_n),
        .sym_start(sym_start),
        .enable(tx_enable),
        .tx_bit(frame_bit_out),
        .tx_i(tx_i),
        .tx_q(tx_q),
        .tx_valid(tx_valid),
        .sym_done(sym_done)
);

tx_ctrl #(.N(N))    u_tx_ctrl(
        .clk(clk),
        .rst_n(rst_n),
        .ext_start(ext_start),
        .sym_done(sym_done),
        .frame_done(frame_done),
        .bit_valid(frame_bit_valid),
        .frame_start(frame_start),
        .bit_req(bit_req),
        .sym_start(sym_start),
        .tx_enable(tx_enable),
        .frame_seq(tx_frame_seq),
        .busy(tx_busy)
    );

demod_top #(.N(N), .W(W), .DDS_LAT(DDS_LAT), .STEP(STEP))   u_demod(
        .clk(clk),
        .rst_n(rst_n),
        .sym_start(rx_sym_start),
        .rx_i(rx_i),
        .rx_q(rx_q),
        .rx_valid(rx_valid),
        .bit_out(bit_out),
        .bit_valid(bit_valid)
);

frame_sync #(.SYNC_WORD(8'hA7)) u_frame_sync(
        .clk(clk),
        .rst_n(rst_n),
        .bit_in(bit_out),
        .bit_valid(bit_valid),
        .sync_found(sync_found),
        .bit_idx(bit_idx)
);

crc_check   u_crc_check(
        .clk(clk),
        .rst_n(rst_n),
        .sync_found(sync_found),
        .bit_in(bit_out),
        .bit_valid(bit_valid),
        .crc_ok(crc_ok),
        .crc_reg(crc_reg)
);

ber_counter #(.SEED(SEED))  u_ber (
        .clk(clk),
        .rst_n(rst_n),
        .sync_found(sync_found),
        .bit_in(bit_out),
        .bit_valid(bit_valid),
        .err_count(err_count),
        .bit_count(bit_count),
        .result_valid(ber_valid)
);

rx_ctrl u_rx_ctrl(
        .clk(clk),
        .rst_n(rst_n),
        .tx_frame_seq(tx_frame_seq),
        .crc_ok(crc_ok),
        .ber_valid(ber_valid),
        .err_count(err_count),
        .bit_count(bit_count),
        .uart_ready(uart_ready),
        .uart_data(uart_data),
        .uart_send(uart_send)
);

uart_tx #(.CLK_FREQ(50_000_000), .BAUD(115_200))    u_uart(
        .clk(clk),
        .rst_n(rst_n),
        .data(uart_data),
        .send(uart_send),
        .ready(uart_ready),
        .tx(uart_tx_pin)
);

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        sync_latch <= 1'b0;
        crc_latch  <= 1'b0;
        hb_cnt     <= 24'd0;
    end 
    else begin
        if (sync_found)  sync_latch <= 1'b1;
        if (crc_ok)      crc_latch  <= 1'b1;
        hb_cnt <= hb_cnt + 24'd1;
    end
end

assign  heartbeat = hb_cnt[23];

assign  led[0] = tx_busy;
assign  led[1] = sync_latch;
assign  led[2] = crc_latch;
assign  led[3] = heartbeat;

endmodule
