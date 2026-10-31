module message_rx #(
        parameter   MAX_PAYLOAD = 256,
        parameter   GAP_TIMEOUT = 1000000
)(
        input   wire    clk,
        input   wire    rst_n,
        input   wire    bit_in,
        input   wire    bit_valid,
        input   wire    abort,
        input   wire    release_packet,
        input   wire    [7:0]   read_addr,
        output  wire    [7:0]   read_data,
        output  wire    read_valid,
        output  reg     packet_ready,
        output  reg     packet_valid,
        output  reg     [15:0]  packet_seq,
        output  reg     [15:0]  packet_length,
        output  reg     error_valid,
        output  reg     [2:0]   error_code,
        output  reg     overrun
);

localparam  [1:0] S_SEARCH = 0, S_HEADER = 1, S_DATA = 2, S_CRC = 3;
reg [1:0]  state;
reg [47:0]  sync_shift;
reg [7:0]  shift;
reg [7:0]  crc_high;
reg [7:0]  length_high;
reg [2:0]  bit_count;
reg [2:0]  header_index;
reg crc_low;
reg [15:0]  seq_r;
reg [15:0]  length_r;
reg [15:0]  payload_index;
reg [15:0]  crc;
reg [31:0]  gap_count;
reg [7:0]  payload_mem[0:MAX_PAYLOAD-1];

function [15:0] crc_step;
    input [15:0] value;
    input sample;
    begin
        crc_step = (value<<1)^((value[15]^sample)?16'h1021:16'h0000);
    end
endfunction

wire    [7:0]   next_byte = {shift[6:0],bit_in};
wire    [47:0]  next_sync = {sync_shift[46:0],bit_in};
wire    [15:0]  next_length = {length_high,next_byte};
assign  read_valid = packet_ready && ({8'd0,read_addr}<packet_length);
assign  read_data = read_valid?payload_mem[read_addr]:8'd0;

always  @(posedge clk) begin
    if (rst_n && !abort && !release_packet && !packet_ready &&
       state==S_DATA && bit_valid && bit_count==7)
        payload_mem[payload_index[7:0]] <= next_byte;
end

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state <= S_SEARCH;
        sync_shift <= 0;
        shift <= 0;
        crc_high <= 0;
        length_high <= 0;
        bit_count <= 0;
        header_index <= 0;
        crc_low <= 0;
        seq_r <= 0;
        length_r <= 0;
        payload_index <= 0;
        crc <= 16'hffff;
        gap_count <= 0;
        packet_ready <= 0;
        packet_valid <= 0;
        packet_seq <= 0;
        packet_length <= 0;
        error_valid <= 0;
        error_code <= 0;
        overrun <= 0;
    end
    else begin
        packet_valid <= 0;
        error_valid <= 0;
        if (abort || release_packet) begin
            state <= S_SEARCH;
            sync_shift <= 0;
            gap_count <= 0;
            packet_ready <= 0;
            packet_seq <= 0;
            packet_length <= 0;
            overrun <= 0;
        end
        else if (packet_ready) begin
            if (bit_valid) overrun <= 1;
        end
        else if (state!=S_SEARCH && !bit_valid && gap_count==GAP_TIMEOUT-1) begin
            state <= S_SEARCH;
            sync_shift <= 0;
            gap_count <= 0;
            error_valid <= 1;
            error_code <= 5;
        end
        else begin
            if (bit_valid || state==S_SEARCH) gap_count <= 0;
            else        gap_count <= gap_count+1'b1;
            if (bit_valid) begin
                if (state==S_SEARCH) begin
                    sync_shift <= next_sync;
                    if (next_sync==48'haaaa_d391_c5a7) begin
                        state <= S_HEADER;
                        header_index <= 0;
                        bit_count <= 0;
                        shift <= 0;
                        crc <= 16'hffff;
                        payload_index <= 0;
                        seq_r <= 0;
                        length_r <= 0;
                    end
                end
                else begin
                    shift <= next_byte;
                    if (state==S_HEADER || state==S_DATA) crc <= crc_step(crc,bit_in);
                    if (bit_count!=7) bit_count <= bit_count+1'b1;
                    else begin
                        bit_count <= 0;
                        case (state)
                            S_HEADER: begin
                                header_index <= header_index+1'b1;
                                case (header_index)
                                    0: if (next_byte!=1) begin
                                        state <= S_SEARCH;
                                        sync_shift <= 0;
                                        error_valid <= 1;
                                        error_code <= 3;
                                    end
                                    1: seq_r[15:8] <= next_byte;
                                    2: seq_r[7:0] <= next_byte;
                                    3: length_high <= next_byte;
                                    4: begin
                                        if (next_length>MAX_PAYLOAD) begin
                                            state <= S_SEARCH;
                                            sync_shift <= 0;
                                            error_valid <= 1;
                                            error_code <= 2;
                                        end
                                        else begin
                                            length_r <= next_length;
                                            crc_low <= 0;
                                            state <= (next_length==0)?S_CRC:S_DATA;
                                        end
                                    end
                                endcase
                            end
                            S_DATA: begin
                                if (payload_index+1'b1==length_r) begin
                                    state <= S_CRC;
                                    crc_low <= 0;
                                end
                                else        payload_index <= payload_index+1'b1;
                            end
                            S_CRC: begin
                                if (!crc_low) begin
                                    crc_high <= next_byte;
                                    crc_low <= 1;
                                end
                                else begin
                                    state <= S_SEARCH;
                                    sync_shift <= 0;
                                    if ({crc_high,next_byte}==crc) begin
                                        packet_ready <= 1;
                                        packet_valid <= 1;
                                        packet_seq <= seq_r;
                                        packet_length <= length_r;
                                    end
                                    else begin
                                        error_valid <= 1;
                                        error_code <= 4;
                                    end
                                end
                            end
                        endcase
                    end
                end
            end
        end
    end
end
endmodule
