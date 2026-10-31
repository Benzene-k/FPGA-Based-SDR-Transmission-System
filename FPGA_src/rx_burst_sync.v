module rx_burst_sync #(
        parameter   integer N = 4096,
        parameter   integer QUIET_SAMPLES = 8,
        parameter   integer HIGH_LEVEL = 1024,
        parameter   integer LOW_LEVEL = 512,
        parameter   integer MAX_GAP_SAMPLES = 8192
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    abort,
        input   wire    signed [15:0]   i_in,
        input   wire    signed [15:0]   q_in,
        input   wire    sample_valid,
        output  wire    signed [15:0]   i_out,
        output  wire    signed [15:0]   q_out,
        output  wire    out_valid,
        output  reg     symbol_start,
        output  reg     locked,
        output  reg     lost
);

localparam  SEARCH = 0;
localparam  CAPTURE = 1;
localparam  GAP = 2;

reg [1:0]  state;
integer quiet_count;
integer sample_count;
integer gap_count;
reg armed;

wire    [15:0]  ai = i_in[15] ? -i_in : i_in;
wire    [15:0]  aq = q_in[15] ? -q_in : q_in;
wire    [16:0]  level = {1'b0, ai} + {1'b0, aq};

reg [31:0]  data0;
reg [31:0]  data1;
reg valid0;
reg valid1;

assign  {i_out, q_out} = data1;
assign  out_valid = valid1;

always  @(posedge clk) begin
    if (!rst_n || abort) begin
        state <= SEARCH;
        quiet_count <= 0;
        sample_count <= 0;
        gap_count <= 0;
        armed <= 0;
        symbol_start <= 0;
        locked <= 0;
        lost <= 0;
        data0 <= 0;
        data1 <= 0;
        valid0 <= 0;
        valid1 <= 0;
    end
    else begin
        symbol_start <= 0;
        lost <= 0;
        valid0 <= 0;
        valid1 <= valid0;
        data1 <= data0;
        if (sample_valid) begin
            case (state)
                SEARCH: begin
                    if (level <= LOW_LEVEL) begin
                        if (quiet_count < QUIET_SAMPLES) quiet_count <= quiet_count + 1;
                        if (quiet_count >= QUIET_SAMPLES - 1) armed <= 1;
                    end
                    else begin
                        quiet_count <= 0;
                        if (armed && level >= HIGH_LEVEL) begin
                            armed <= 0;
                            symbol_start <= 1;
                            sample_count <= 1;
                            quiet_count <= 0;
                            data0 <= {i_in, q_in};
                            valid0 <= 1;
                            if (N == 1) begin
                                state <= GAP;
                                locked <= 1;
                                gap_count <= 0;
                            end
                            else state <= CAPTURE;
                        end
                    end
                end
                CAPTURE: begin
                    data0 <= {i_in, q_in};
                    valid0 <= 1;
                    sample_count <= sample_count + 1;
                    if (level <= LOW_LEVEL) quiet_count <= quiet_count + 1;
                    else quiet_count <= 0;
                    if (level <= LOW_LEVEL && quiet_count >= QUIET_SAMPLES - 1) begin
                        state <= SEARCH;
                        armed <= 1;
                        quiet_count <= QUIET_SAMPLES;
                        locked <= 0;
                        lost <= 1;
                        valid0 <= 0;
                        valid1 <= 0;
                    end
                    else if (sample_count == N - 1) begin
                        state <= GAP;
                        gap_count <= 0;
                        quiet_count <= 0;
                        locked <= 1;
                    end
                end
                GAP: begin
                    if (level <= LOW_LEVEL) begin
                        if (quiet_count < QUIET_SAMPLES) quiet_count <= quiet_count + 1;
                        if (quiet_count >= QUIET_SAMPLES - 1) armed <= 1;
                    end
                    else quiet_count <= 0;
                    if (armed && level >= HIGH_LEVEL) begin
                        armed <= 0;
                        symbol_start <= 1;
                        sample_count <= 1;
                        quiet_count <= 0;
                        data0 <= {i_in, q_in};
                        valid0 <= 1;
                        if (N == 1) gap_count <= 0;
                        else state <= CAPTURE;
                    end
                    else if (gap_count >= MAX_GAP_SAMPLES - 1) begin
                        state <= SEARCH;
                        locked <= 0;
                        lost <= 1;
                        gap_count <= 0;
                    end
                    else gap_count <= gap_count + 1;
                end
                default: state <= SEARCH;
            endcase
        end
    end
end

endmodule
