module sample_fifo #(
        parameter   WIDTH = 33,
        parameter   DEPTH = 8192
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    [WIDTH-1:0]     in_data,
        input   wire    in_valid,
        output  wire    in_ready,
        output  wire    [WIDTH-1:0]     out_data,
        output  reg     out_valid,
        input   wire    out_ready
);

localparam  AW = $clog2(DEPTH);

(* ram_style = "block" *) reg [WIDTH-1:0]  mem[0:DEPTH-1];

reg [AW-1:0]  wr_ptr;
reg [AW-1:0]  rd_ptr;
reg [AW:0]  count;
reg [WIDTH-1:0]  ram_data;
reg [WIDTH-1:0]  bypass_data;
reg select_bypass;

wire    advance = !out_valid || out_ready;
wire    read_ram = advance && count != 0;

assign  in_ready = (count < DEPTH);

wire    bypass = advance && count == 0 && in_valid && in_ready;
wire    write_ram = in_valid && in_ready && !bypass;

always  @(posedge clk) begin
    if (rst_n && write_ram) mem[wr_ptr] <= in_data;
end

always  @(posedge clk) begin
    if (rst_n && read_ram) ram_data <= mem[rd_ptr];
end

always  @(posedge clk) begin
    if (rst_n && bypass) bypass_data <= in_data;
end

assign  out_data = select_bypass ? bypass_data : ram_data;

always  @(posedge clk) begin
    if (!rst_n) begin
        wr_ptr <= 0;
        rd_ptr <= 0;
        count <= 0;
        out_valid <= 0;
        select_bypass <= 0;
    end
    else begin
        if (write_ram) wr_ptr <= wr_ptr + 1'b1;
        if (read_ram) rd_ptr <= rd_ptr + 1'b1;
        case ({write_ram, read_ram})
            2'b10: count <= count + 1'b1;
            2'b01: count <= count - 1'b1;
            default: count <= count;
        endcase
        if (advance) begin
            out_valid <= read_ram || bypass;
            select_bypass <= bypass;
        end
    end
end

endmodule
