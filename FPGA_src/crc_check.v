module crc_check (
        input   wire        clk,
        input   wire        rst_n,
        input   wire        sync_found,
        input   wire        bit_in,
        input   wire        bit_valid,
        output  reg         crc_ok,
        output  reg  [15:0] crc_reg
);

localparam  [15:0] CRC_INIT = 16'hFFFF;
localparam  [15:0] CRC_RES  = 16'h1D0F;
localparam  [15:0] POLY     = 16'h1021;

reg [5:0]  bit_idx;
reg        in_frame;

wire    msb = crc_reg[15];
wire    [15:0]   next_crc = (crc_reg << 1) ^ (msb ^ bit_in ? POLY : 16'h0);

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        crc_reg  <= CRC_INIT;
        bit_idx  <= 6'd0;
        in_frame <= 1'b0;
        crc_ok   <= 1'b0;
    end
    else begin
        if (sync_found) begin
            crc_reg  <= CRC_INIT;
            bit_idx  <= 6'd0;
            in_frame <= 1'b1;
            crc_ok   <= 1'b0;
        end
        else if (in_frame && bit_valid) begin
            crc_reg <= next_crc;
            bit_idx <= bit_idx + 6'd1;
            if (bit_idx == 6'd49) begin
                in_frame <= 1'b0;
                crc_ok   <= (next_crc == CRC_RES);
            end
        end
    end
end

endmodule
