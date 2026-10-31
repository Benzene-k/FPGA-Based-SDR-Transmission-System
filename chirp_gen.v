module chirp_gen #(
        parameter   N        = 4096,
        parameter   PHASE_W  = 32,
        parameter   INC0     = 32'h0000_0000,
        parameter   STEP     = 32'h0000_1000,
        parameter   USE_DDS1 = 0,
        parameter   DDS_LAT  = 3
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    load,
        input   wire    enable,
        output  wire    signed [15:0]   ref_i,
        output  wire    signed [15:0]   ref_q,
        output  wire    ref_valid,
        output  wire    done
);

reg [PHASE_W-1:0]  inc_acc;
reg [$clog2(N)-1:0]  cnt;
reg symbol_full;
reg [DDS_LAT-1:0]  valid_pipe;
reg [DDS_LAT-1:0]  last_pipe;
integer p;

wire    sample_valid = enable && !load && !symbol_full;
wire    sample_last  = sample_valid && (cnt == N-1);
wire    [PHASE_W-1:0]   phase_step = sample_valid ? inc_acc : {PHASE_W{1'b0}};
wire    dds_valid;
assign  ref_valid = valid_pipe[DDS_LAT-1] && dds_valid;
assign  done = last_pipe[DDS_LAT-1] && ref_valid;

wire    [15:0]   mdata;
wire    [7:0]   cos_out = mdata[7:0];
wire    [7:0]   sin_out = mdata[15:8];

assign  ref_i = {cos_out[7], cos_out, 7'b0};
assign  ref_q = {sin_out[7], sin_out, 7'b0};

generate
    if (USE_DDS1) begin : g_dds1
        dds_compiler_1 u_dds(
            .aclk(clk),
            .aresetn(rst_n),
            .s_axis_phase_tdata(phase_step),
            .s_axis_phase_tvalid(1'b1),
            .m_axis_data_tdata(mdata),
            .m_axis_data_tvalid(dds_valid)
        );
    end
    else begin : g_dds0
        dds_compiler_0 u_dds(
            .aclk(clk),
            .aresetn(rst_n),
            .s_axis_phase_tdata(phase_step),
            .s_axis_phase_tvalid(1'b1),
            .m_axis_data_tdata(mdata),
            .m_axis_data_tvalid(dds_valid)
        );
    end
endgenerate

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        inc_acc <= INC0;
        cnt     <= {$clog2(N){1'b0}};
        symbol_full <= 1'b0;
    end
    else if (load) begin
        inc_acc <= INC0;
        cnt     <= {$clog2(N){1'b0}};
        symbol_full <= 1'b0;
    end
    else if (sample_valid) begin
        inc_acc <= inc_acc + STEP;
        if (sample_last) symbol_full <= 1'b1;
        else             cnt <= cnt + 1'b1;
    end
end

always  @(posedge clk) begin
    if (!rst_n) begin
        valid_pipe <= {DDS_LAT{1'b0}};
        last_pipe  <= {DDS_LAT{1'b0}};
    end
    else begin
        valid_pipe[0] <= sample_valid;
        last_pipe[0] <= sample_last;
        for (p = 1; p < DDS_LAT; p = p + 1) begin
            valid_pipe[p] <= valid_pipe[p-1];
            last_pipe[p] <= last_pipe[p-1];
        end
    end
end

endmodule
