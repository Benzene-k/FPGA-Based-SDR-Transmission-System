module message_tx #(
        parameter   MAX_PAYLOAD = 256
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
        input   wire    send_start,
        input   wire    bit_req,
        input   wire    abort,
        output  wire    busy,
        output  reg     bit_out,
        output  reg     bit_valid,
        output  reg     frame_done,
        output  reg     error_valid,
        output  reg     [2:0]   error_code
);

localparam  [1:0] S_IDLE = 0, S_LOAD = 1, S_READY = 2, S_SEND = 3;
localparam  [2:0] P_PRE = 0, P_SYNC = 1, P_HEADER = 2, P_DATA = 3, P_CRC = 4;
reg [1:0]  state;
reg [2:0]  phase;
reg [2:0]  section_count;
reg [2:0]  bit_left;
reg [15:0]  seq_r;
reg [15:0]  length_r;
reg [15:0]  loaded_count;
reg [15:0]  payload_index;
reg [7:0]  payload_mem[0:MAX_PAYLOAD-1];
reg [7:0]  shift;
reg [15:0]  crc;
reg [15:0]  crc_tail;
wire    [7:0]   payload_read_addr = (phase==P_HEADER)?8'd0:payload_index[7:0]+8'd1;
wire    [7:0]   payload_read_data = payload_mem[payload_read_addr];

function [15:0] crc_step;
    input [15:0] value;
    input sample;
    begin
        crc_step = (value<<1)^((value[15]^sample)?16'h1021:16'h0000);
    end
endfunction

wire    [15:0]  next_crc = crc_step(crc,shift[7]);
assign  load_ready = (state==S_LOAD)&&(loaded_count<length_r);
assign  message_ready = (state==S_READY);
assign  busy = (state==S_SEND);

always  @(posedge clk) begin
    if (rst_n && !abort && !load_start && !send_start && load_valid && load_ready)
        payload_mem[loaded_count[7:0]] <= load_data;
end

always  @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state <= S_IDLE;
        phase <= P_PRE;
        section_count <= 0;
        bit_left <= 7;
        seq_r <= 0;
        length_r <= 0;
        loaded_count <= 0;
        payload_index <= 0;
        shift <= 0;
        crc <= 16'hffff;
        crc_tail <= 0;
        bit_out <= 0;
        bit_valid <= 0;
        frame_done <= 0;
        error_valid <= 0;
        error_code <= 0;
    end
    else begin
        bit_valid <= 0;
        frame_done <= 0;
        error_valid <= 0;
        if (abort) begin
            state <= S_IDLE;
            loaded_count <= 0;
            payload_index <= 0;
        end
        else if (load_start && state!=S_SEND) begin
            if (load_length>MAX_PAYLOAD) begin
                error_valid <= 1;
                error_code <= 2;
            end
            else begin
                seq_r <= load_seq;
                length_r <= load_length;
                loaded_count <= 0;
                state <= (load_length==0)?S_READY:S_LOAD;
            end
        end
        else begin
            case (state)
                S_IDLE: if (send_start || load_valid) begin
                    error_valid <= 1;
                    error_code <= 3;
                end
                S_LOAD: begin
                    if (send_start) begin
                        error_valid <= 1;
                        error_code <= 3;
                    end
                    else if (load_valid && load_ready) begin
                        loaded_count <= loaded_count+1'b1;
                        if (loaded_count+1'b1==length_r) state <= S_READY;
                    end
                end
                S_READY: begin
                    if (load_valid) begin
                        error_valid <= 1;
                        error_code <= 3;
                    end
                    if (send_start) begin
                        state <= S_SEND;
                        phase <= P_PRE;
                        section_count <= 0;
                        bit_left <= 7;
                        shift <= 8'haa;
                        crc <= 16'hffff;
                        payload_index <= 0;
                    end
                end
                S_SEND: begin
                    if (load_start || load_valid || send_start) begin
                        error_valid <= 1;
                        error_code <= 1;
                    end
                    if (bit_req) begin
                        bit_out <= shift[7];
                        bit_valid <= 1;
                        shift <= {shift[6:0],1'b0};
                        if (phase==P_HEADER || phase==P_DATA) crc <= next_crc;
                        if (bit_left!=0) bit_left <= bit_left-1'b1;
                        else begin
                            bit_left <= 7;
                            case (phase)
                                P_PRE: begin
                                    if (section_count==0) begin
                                        section_count <= 1;
                                        shift <= 8'haa;
                                    end
                                    else begin
                                        phase <= P_SYNC;
                                        section_count <= 0;
                                        shift <= 8'hd3;
                                    end
                                end
                                P_SYNC: begin
                                    section_count <= section_count+1'b1;
                                    case (section_count)
                                        0: shift <= 8'h91;
                                        1: shift <= 8'hc5;
                                        2: shift <= 8'ha7;
                                        3: begin
                                            phase <= P_HEADER;
                                            section_count <= 0;
                                            shift <= 8'h01;
                                        end
                                    endcase
                                end
                                P_HEADER: begin
                                    section_count <= section_count+1'b1;
                                    case (section_count)
                                        0: shift <= seq_r[15:8];
                                        1: shift <= seq_r[7:0];
                                        2: shift <= length_r[15:8];
                                        3: shift <= length_r[7:0];
                                        4: begin
                                            section_count <= 0;
                                            if (length_r==0) begin
                                                phase <= P_CRC;
                                                crc_tail <= next_crc;
                                                shift <= next_crc[15:8];
                                            end
                                            else begin
                                                phase <= P_DATA;
                                                shift <= payload_read_data;
                                            end
                                        end
                                    endcase
                                end
                                P_DATA: begin
                                    if (payload_index+1'b1==length_r) begin
                                        phase <= P_CRC;
                                        section_count <= 0;
                                        crc_tail <= next_crc;
                                        shift <= next_crc[15:8];
                                    end
                                    else begin
                                        payload_index <= payload_index+1'b1;
                                        shift <= payload_read_data;
                                    end
                                end
                                P_CRC: begin
                                    if (section_count==0) begin
                                        section_count <= 1;
                                        shift <= crc_tail[7:0];
                                    end
                                    else begin
                                        state <= S_IDLE;
                                        frame_done <= 1;
                                    end
                                end
                            endcase
                        end
                    end
                end
            endcase
        end
    end
end
endmodule
