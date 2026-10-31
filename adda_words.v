module adda_words(
        input   wire    sample_clk,
        input   wire    rst_n,
        input   wire    sample_strobe,
        input   wire    [7:0]   adc_data,
        input   wire    adc_otr,
        output  reg     signed [15:0]   adc_sample,
        output  reg     adc_valid,
        output  reg     adc_overrange,
        input   wire    dac_enable,
        input   wire    signed [15:0]   dac_sample,
        output  reg     [7:0]   dac_data
);

always  @(posedge sample_clk or negedge rst_n) begin
    if (!rst_n) begin
        adc_sample <= 0;
        adc_valid <= 0;
        adc_overrange <= 0;
        dac_data <= 128;
    end
    else begin
        adc_valid <= sample_strobe;
        if (sample_strobe) begin
            adc_sample <= {adc_data[7]^1'b1, adc_data[6:0], 8'b0};
            adc_overrange <= adc_otr;
        end
        if (!dac_enable) dac_data <= 128;
        else if (sample_strobe) dac_data <= {dac_sample[15]^1'b1, dac_sample[14:8]};
    end
end

endmodule
