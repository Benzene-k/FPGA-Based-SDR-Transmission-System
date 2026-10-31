module message_symbol_tx #(
        parameter   GAP_CYCLES = 64
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    start,
        input   wire    message_ready,
        input   wire    bit_value,
        input   wire    bit_valid,
        input   wire    bit_last,
        input   wire    sym_done,
        input   wire    abort,
        output  reg     message_start,
        output  reg     bit_req,
        output  reg     sym_start,
        output  reg     enable,
        output  reg     tx_bit,
        output  reg     busy,
        output  reg     done,
        output  reg     error
);

localparam  [2:0] S_IDLE = 0, S_ARM = 1, S_REQ = 2, S_BIT = 3, S_SYMBOL = 4, S_GAP = 5;
reg [2:0]  state;
reg last_symbol;
reg [31:0]  gap_count;

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state <= S_IDLE;
        last_symbol <= 0;
        gap_count <= 0;
        message_start <= 0;
        bit_req <= 0;
        sym_start <= 0;
        enable <= 0;
        tx_bit <= 0;
        busy <= 0;
        done <= 0;
        error <= 0;
    end
    else begin
        message_start <= 0;
        bit_req <= 0;
        sym_start <= 0;
        done <= 0;
        error <= 0;
        if (abort) begin
            state <= S_IDLE;
            enable <= 0;
            busy <= 0;
            last_symbol <= 0;
        end
        else begin
            if (start && state!=S_IDLE) error <= 1;
            case (state)
                S_IDLE: begin
                    busy <= 0;
                    enable <= 0;
                    if (start) begin
                        if (message_ready) begin
                            message_start <= 1;
                            busy <= 1;
                            state <= S_ARM;
                        end
                        else        error <= 1;
                    end
                end
                S_ARM: state <= S_REQ;
                S_REQ: begin
                    bit_req <= 1;
                    state <= S_BIT;
                end
                S_BIT: if (bit_valid) begin
                    tx_bit <= bit_value;
                    last_symbol <= bit_last;
                    sym_start <= 1;
                    enable <= 1;
                    state <= S_SYMBOL;
                end
                S_SYMBOL: if (sym_done) begin
                    enable <= 0;
                    if (last_symbol) begin
                        done <= 1;
                        busy <= 0;
                        state <= S_IDLE;
                    end
                    else begin
                        gap_count <= 0;
                        state <= S_GAP;
                    end
                end
                S_GAP: begin
                    if (GAP_CYCLES==0 || gap_count==GAP_CYCLES-1) state <= S_REQ;
                    else        gap_count <= gap_count+1'b1;
                end
                default: begin
                    state <= S_IDLE;
                    busy <= 0;
                    enable <= 0;
                end
            endcase
        end
    end
end
endmodule
