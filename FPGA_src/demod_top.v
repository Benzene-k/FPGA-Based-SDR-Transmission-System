module demod_top #(
        parameter   N       = 4096,
        parameter   W       = 16,
        parameter   DDS_LAT = 3,
        parameter   INC0    = 32'h0000_0000,
        parameter   STEP    = 32'h0000_1000,
        parameter   USE_RUNTIME_LIMITS = 0,
        parameter   [2*W:0] MIN_PEAK = 1,
        parameter   [2*W:0] MIN_MARGIN = 1
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    sym_start,
        input   wire    signed [W-1:0]   rx_i,
        input   wire    signed [W-1:0]   rx_q,
        input   wire    rx_valid,
        output  wire    bit_out,
        output  reg     bit_valid,
        output  reg     symbol_valid,
        output  reg     decision_rejected,
        output  reg     flow_fault,
        input   wire    [2*W:0]   configured_peak,
        input   wire    [2*W:0]   configured_margin
);

localparam  CW = $clog2(N);

reg sym_start_d;
wire    sym_pulse = sym_start & ~sym_start_d;
wire    load      = sym_pulse;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) sym_start_d <= 1'b0;
    else        sym_start_d <= sym_start;
end

wire    signed [W-1:0]   ref_i, ref_q;
wire    ref_valid;
wire    chirp_done;
chirp_gen #(.N(N), .INC0(INC0), .STEP(STEP))    u_chirp(
        .clk(clk),
        .rst_n(rst_n),
        .load(load),
        .enable(rx_valid),
        .ref_i(ref_i),
        .ref_q(ref_q),
        .ref_valid(ref_valid),
        .done(chirp_done)
);

wire    signed [W-1:0]   a_i, a_q, b_i, b_q;
wire    de_valid, de_fault, fft0_fault, fft1_fault;
dechirp #(.W(W), .DDS_LAT(DDS_LAT))    u_dechirp(
        .clk(clk),
        .rst_n(rst_n),
        .in_valid(rx_valid),
        .rx_i(rx_i),
        .rx_q(rx_q),
        .ref_i(ref_i),
        .ref_q(ref_q),
        .ref_valid(ref_valid),
        .a_i(a_i),
        .a_q(a_q),
        .b_i(b_i),
        .b_q(b_q),
        .out_valid(de_valid),
        .flow_fault(de_fault)
);

reg [CW-1:0]  out_cnt;
wire    fft_last = de_valid && (out_cnt == N-1);

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n)              out_cnt <= {CW{1'b0}};
    else if (de_valid)       out_cnt <= (out_cnt == N-1) ? {CW{1'b0}} : out_cnt + 1'b1;
end

wire    signed [W-1:0]   f0_i, f0_q, f1_i, f1_q;
wire    [15:0]   f0_idx, f1_idx;
wire    f0_v, f0_last, f1_v, f1_last;
wire    f0_rdy, f1_rdy;
wire    fifo0_ready, fifo1_ready, fft0_valid, fft1_valid;
wire    [2*W:0]   fft0_data, fft1_data;
wire    enqueue = de_valid && fifo0_ready && fifo1_ready && !flow_fault;
sample_fifo #(.WIDTH(2*W+1), .DEPTH(2*N))    u_samples0(
        .clk(clk),
        .rst_n(rst_n),
        .in_data({fft_last, a_q, a_i}),
        .in_valid(enqueue),
        .in_ready(fifo0_ready),
        .out_data(fft0_data),
        .out_valid(fft0_valid),
        .out_ready(f0_rdy)
);
sample_fifo #(.WIDTH(2*W+1), .DEPTH(2*N))    u_samples1(
        .clk(clk),
        .rst_n(rst_n),
        .in_data({fft_last, b_q, b_i}),
        .in_valid(enqueue),
        .in_ready(fifo1_ready),
        .out_data(fft1_data),
        .out_valid(fft1_valid),
        .out_ready(f1_rdy)
);

fft #(.W(W))    u_fft0(
        .clk(clk),
        .rst_n(rst_n),
        .din_i(fft0_data[W-1:0]),
        .din_q(fft0_data[2*W-1:W]),
        .din_valid(fft0_valid),
        .din_last(fft0_data[2*W]),
        .din_ready(f0_rdy),
        .dout_i(f0_i),
        .dout_q(f0_q),
        .dout_index(f0_idx),
        .dout_valid(f0_v),
        .dout_last(f0_last),
        .frame_fault(fft0_fault)
);

fft #(.W(W))    u_fft1(
        .clk(clk),
        .rst_n(rst_n),
        .din_i(fft1_data[W-1:0]),
        .din_q(fft1_data[2*W-1:W]),
        .din_valid(fft1_valid),
        .din_last(fft1_data[2*W]),
        .din_ready(f1_rdy),
        .dout_i(f1_i),
        .dout_q(f1_q),
        .dout_index(f1_idx),
        .dout_valid(f1_v),
        .dout_last(f1_last),
        .frame_fault(fft1_fault)
);

wire    signed [2*W:0]   peak_pos, peak_neg;
wire    pp_v, pn_v;
peak_detect #(.W(W))    u_pk0(
        .clk(clk),
        .rst_n(rst_n),
        .din_i(f0_i),
        .din_q(f0_q),
        .din_valid(f0_v),
        .din_last(f0_last),
        .peak(peak_pos),
        .peak_valid(pp_v)
);
peak_detect #(.W(W))    u_pk1(
        .clk(clk),
        .rst_n(rst_n),
        .din_i(f1_i),
        .din_q(f1_q),
        .din_valid(f1_v),
        .din_last(f1_last),
        .peak(peak_neg),
        .peak_valid(pn_v)
);

reg pending0, pending1;
reg signed [2*W:0]  saved0, saved1;
wire    signed [2*W:0]   paired0 = pending0 ? saved0 : peak_pos;
wire    signed [2*W:0]   paired1 = pending1 ? saved1 : peak_neg;
wire    [2*W:0]   peak_high = (paired0 > paired1) ? paired0 : paired1;
wire    [2*W:0]   peak_gap = (paired0 > paired1) ?
                        paired0 - paired1 : paired1 - paired0;
wire    decision_ready = (pending0 || pp_v) && (pending1 || pn_v);
wire    pair_overrun = (pending0 && pp_v) || (pending1 && pn_v);
wire    [2*W:0]   active_peak = USE_RUNTIME_LIMITS ? configured_peak : MIN_PEAK;
wire    [2*W:0]   active_margin = USE_RUNTIME_LIMITS ? configured_margin : MIN_MARGIN;
wire    decision_accept = !paired0[2*W] && !paired1[2*W] &&
                       (peak_high != 0) && (paired0 != paired1) &&
                       (peak_high >= active_peak) && (peak_gap >= active_margin);
reg decided_bit;

always  @(posedge clk) begin
    if (!rst_n) begin
        bit_valid <= 1'b0;
        decision_rejected <= 1'b0;
        symbol_valid <= 0;
        flow_fault <= 0;
        pending0 <= 0;
        pending1 <= 0;
        saved0 <= 0;
        saved1 <= 0;
        decided_bit <= 0;
    end
    else begin
        bit_valid <= 0;
        symbol_valid <= 0;
        decision_rejected <= 0;
        if ((de_valid && (!fifo0_ready || !fifo1_ready)) || pair_overrun || de_fault || fft0_fault || fft1_fault) flow_fault <= 1;
        if (!flow_fault && !pair_overrun && !de_fault && !fft0_fault && !fft1_fault && !(de_valid && (!fifo0_ready || !fifo1_ready))) begin
            if (decision_ready) begin
                pending0 <= 0;
                pending1 <= 0;
                decided_bit <= (paired0 > paired1);
                symbol_valid <= 1;
                bit_valid <= decision_accept;
                decision_rejected <= !decision_accept;
            end
            else begin
                if (pp_v) begin
                    saved0 <= peak_pos;
                    pending0 <= 1;
                end
                if (pn_v) begin
                    saved1 <= peak_neg;
                    pending1 <= 1;
                end
            end
        end
    end
end

assign  bit_out = decided_bit;

endmodule
