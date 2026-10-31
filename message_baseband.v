module message_baseband #(
        parameter   N = 4096,
        parameter   INC0 = 32'h0000_0000,
        parameter   STEP = 32'h0000_1000,
        parameter   GAP_CYCLES = 64,
        parameter   TX_SAMPLE_DIV = 1,
        parameter   RX_GAP_TIMEOUT = 1000000,
        parameter   ENABLE_RECOVERY = 0,
        parameter   USE_RUNTIME_LIMITS = 0,
        parameter   [32:0] MIN_PEAK = 1,
        parameter   [32:0] MIN_MARGIN = 1
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    load_start,
        input   wire    [15:0]  load_seq,
        input   wire    [15:0]  load_length,
        input   wire    load_valid,
        input   wire    [7:0]   load_data,
        output  wire    load_ready,
        output  wire    message_ready,
        input   wire    tx_start,
        input   wire    tx_abort,
        output  wire    tx_busy,
        output  wire    tx_done,
        output  wire    tx_error,
        output  wire    [2:0]   tx_error_code,
        output  wire    tx_symbol_start,
        output  wire    signed [15:0]   tx_i,
        output  wire    signed [15:0]   tx_q,
        output  wire    tx_valid,
        input   wire    rx_symbol_start,
        input   wire    signed [15:0]   rx_i,
        input   wire    signed [15:0]   rx_q,
        input   wire    rx_valid,
        input   wire    rx_abort,
        input   wire    release_packet,
        input   wire    rx_recover,
        input   wire    [7:0]   read_addr,
        output  wire    [7:0]   read_data,
        output  wire    read_valid,
        output  wire    packet_ready,
        output  wire    packet_valid,
        output  wire    [15:0]  packet_seq,
        output  wire    [15:0]  packet_length,
        output  wire    rx_error,
        output  wire    [2:0]   rx_error_code,
        output  wire    overrun,
        output  wire    rx_flow_fault,
        input   wire    [32:0]  configured_peak,
        input   wire    [32:0]  configured_margin
);

wire    message_start;
wire    bit_req;
wire    bit_value;
wire    bit_valid;
wire    bit_last;
wire    message_busy;
wire    enable;
wire    tx_bit;
wire    sym_done;
wire    controller_error;
wire    message_error;
wire    [2:0]   message_error_code;
wire    tx_rst_n = rst_n && !tx_abort;
localparam  TW = (TX_SAMPLE_DIV<2)?1:$clog2(TX_SAMPLE_DIV);
reg [TW-1:0]  sample_phase;

always  @(posedge clk) begin
    if (!tx_rst_n) sample_phase <= 0;
    else        sample_phase <= sample_phase==TX_SAMPLE_DIV-1?0:sample_phase+1'b1;
end

wire    tx_sample_tick = (TX_SAMPLE_DIV==1)||(sample_phase==0);
wire    recover = ENABLE_RECOVERY ? rx_recover : 1'b0;
wire    rx_rst_n = rst_n && !(rx_abort || recover);

message_tx  u_message_tx(
        .clk(clk),
        .rst_n(rst_n),
        .load_start(load_start),
        .load_seq(load_seq),
        .load_length(load_length),
        .load_valid(load_valid),
        .load_data(load_data),
        .load_ready(load_ready),
        .message_ready(message_ready),
        .send_start(message_start),
        .bit_req(bit_req),
        .abort(tx_abort),
        .busy(message_busy),
        .bit_out(bit_value),
        .bit_valid(bit_valid),
        .frame_done(bit_last),
        .error_valid(message_error),
        .error_code(message_error_code)
);

message_symbol_tx #(.GAP_CYCLES(GAP_CYCLES))   u_symbols(
        .clk(clk),
        .rst_n(rst_n),
        .start(tx_start),
        .message_ready(message_ready),
        .bit_value(bit_value),
        .bit_valid(bit_valid),
        .bit_last(bit_last),
        .sym_done(sym_done),
        .abort(tx_abort),
        .message_start(message_start),
        .bit_req(bit_req),
        .sym_start(tx_symbol_start),
        .enable(enable),
        .tx_bit(tx_bit),
        .busy(tx_busy),
        .done(tx_done),
        .error(controller_error)
);

chirp_mod #(.N(N), .INC0(INC0), .STEP(STEP))   u_mod(
        .clk(clk),
        .rst_n(tx_rst_n),
        .sym_start(tx_symbol_start),
        .enable(enable && tx_sample_tick),
        .tx_bit(tx_bit),
        .tx_i(tx_i),
        .tx_q(tx_q),
        .tx_valid(tx_valid),
        .sym_done(sym_done)
);

assign  tx_error = message_error || controller_error;
assign  tx_error_code = message_error?message_error_code:(tx_busy?3'd1:3'd3);

wire    decoded_bit;
wire    decoded_valid;
wire    decision_rejected;
wire    symbol_valid;

demod_top #(.N(N), .INC0(INC0), .STEP(STEP), .MIN_PEAK(MIN_PEAK), .MIN_MARGIN(MIN_MARGIN), .USE_RUNTIME_LIMITS(USE_RUNTIME_LIMITS))   u_demod(
        .clk(clk),
        .rst_n(rx_rst_n),
        .sym_start(rx_symbol_start),
        .rx_i(rx_i),
        .rx_q(rx_q),
        .rx_valid(rx_valid),
        .bit_out(decoded_bit),
        .bit_valid(decoded_valid),
        .symbol_valid(symbol_valid),
        .decision_rejected(decision_rejected),
        .flow_fault(rx_flow_fault),
        .configured_peak(configured_peak),
        .configured_margin(configured_margin)
);

wire    parser_error;
wire    [2:0]   parser_error_code;
reg rejected_d;
reg fault_d;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        rejected_d <= 0;
        fault_d <= 0;
    end
    else begin
        rejected_d <= decision_rejected;
        fault_d <= rx_flow_fault;
    end
end

wire    discard_tentative = (decision_rejected || rx_flow_fault) && !packet_ready;

message_rx #(.GAP_TIMEOUT(RX_GAP_TIMEOUT))   u_message_rx(
        .clk(clk),
        .rst_n(rst_n),
        .bit_in(decoded_bit),
        .bit_valid(decoded_valid && !rx_flow_fault && !decision_rejected && !recover),
        .abort(rx_abort || discard_tentative || (recover && !packet_ready)),
        .release_packet(release_packet),
        .read_addr(read_addr),
        .read_data(read_data),
        .read_valid(read_valid),
        .packet_ready(packet_ready),
        .packet_valid(packet_valid),
        .packet_seq(packet_seq),
        .packet_length(packet_length),
        .error_valid(parser_error),
        .error_code(parser_error_code),
        .overrun(overrun)
);

assign  rx_error = parser_error || rejected_d || (rx_flow_fault && !fault_d) || recover;
assign  rx_error_code = parser_error?parser_error_code:(recover?3'd5:(rejected_d?3'd6:3'd7));
endmodule
