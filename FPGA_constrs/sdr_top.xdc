create_clock -period 20.000 -name clk [get_ports clk]

set_property IOSTANDARD LVCMOS33 [get_ports clk]
set_property PACKAGE_PIN U18 [get_ports clk]

set_property IOSTANDARD LVCMOS33 [get_ports rst_n]
set_property PACKAGE_PIN N16 [get_ports rst_n]

set_property IOSTANDARD LVCMOS33 [get_ports uart_rx_pin]
set_property PACKAGE_PIN T19 [get_ports uart_rx_pin]
set_property PULLUP TRUE [get_ports uart_rx_pin]

set_property IOSTANDARD LVCMOS33 [get_ports uart_tx_pin]
set_property PACKAGE_PIN J15 [get_ports uart_tx_pin]

set_property IOSTANDARD LVCMOS33 [get_ports {ad_data[7]}]
set_property PACKAGE_PIN U17 [get_ports {ad_data[7]}]

set_property IOSTANDARD LVCMOS33 [get_ports {ad_data[6]}]
set_property PACKAGE_PIN T16 [get_ports {ad_data[6]}]

set_property IOSTANDARD LVCMOS33 [get_ports {ad_data[5]}]
set_property PACKAGE_PIN Y16 [get_ports {ad_data[5]}]

set_property IOSTANDARD LVCMOS33 [get_ports {ad_data[4]}]
set_property PACKAGE_PIN Y17 [get_ports {ad_data[4]}]

set_property IOSTANDARD LVCMOS33 [get_ports {ad_data[3]}]
set_property PACKAGE_PIN T15 [get_ports {ad_data[3]}]

set_property IOSTANDARD LVCMOS33 [get_ports {ad_data[2]}]
set_property PACKAGE_PIN T14 [get_ports {ad_data[2]}]

set_property IOSTANDARD LVCMOS33 [get_ports {ad_data[1]}]
set_property PACKAGE_PIN W16 [get_ports {ad_data[1]}]

set_property IOSTANDARD LVCMOS33 [get_ports {ad_data[0]}]
set_property PACKAGE_PIN V16 [get_ports {ad_data[0]}]

set_property IOSTANDARD LVCMOS33 [get_ports ad_clk]
set_property PACKAGE_PIN V18 [get_ports ad_clk]

set_property IOSTANDARD LVCMOS33 [get_ports ad_otr]
set_property PACKAGE_PIN V17 [get_ports ad_otr]

set_property IOSTANDARD LVCMOS33 [get_ports {da_data[7]}]
set_property PACKAGE_PIN Y18 [get_ports {da_data[7]}]

set_property IOSTANDARD LVCMOS33 [get_ports {da_data[6]}]
set_property PACKAGE_PIN Y19 [get_ports {da_data[6]}]

set_property IOSTANDARD LVCMOS33 [get_ports {da_data[5]}]
set_property PACKAGE_PIN P15 [get_ports {da_data[5]}]

set_property IOSTANDARD LVCMOS33 [get_ports {da_data[4]}]
set_property PACKAGE_PIN P16 [get_ports {da_data[4]}]

set_property IOSTANDARD LVCMOS33 [get_ports {da_data[3]}]
set_property PACKAGE_PIN W18 [get_ports {da_data[3]}]

set_property IOSTANDARD LVCMOS33 [get_ports {da_data[2]}]
set_property PACKAGE_PIN W19 [get_ports {da_data[2]}]

set_property IOSTANDARD LVCMOS33 [get_ports {da_data[1]}]
set_property PACKAGE_PIN R16 [get_ports {da_data[1]}]

set_property IOSTANDARD LVCMOS33 [get_ports {da_data[0]}]
set_property PACKAGE_PIN R17 [get_ports {da_data[0]}]

set_property IOSTANDARD LVCMOS33 [get_ports da_clk]
set_property PACKAGE_PIN R18 [get_ports da_clk]

set_property DRIVE 8 [get_ports {da_data[*] ad_clk da_clk uart_tx_pin}]
set_property SLEW FAST [get_ports {da_data[*] ad_clk da_clk}]

create_generated_clock -name adc_forward -source [get_pins u_ad_forward/C] -divide_by 1 [get_ports ad_clk]
create_generated_clock -name dac_forward -source [get_pins u_da_forward/C] -divide_by 1 [get_ports da_clk]

set_input_delay -clock adc_forward -max 32.000 [get_ports {ad_data[*] ad_otr}]
set_input_delay -clock adc_forward -min 0.000 [get_ports {ad_data[*] ad_otr}]
set_output_delay -clock dac_forward -max 3.000 [get_ports {da_data[*]}]
set_output_delay -clock dac_forward -min -2.500 [get_ports {da_data[*]}]
set_clock_uncertainty 0.200 [get_clocks -include_generated_clocks clk]

set_false_path -from [get_ports uart_rx_pin] -to [get_pins -hier -filter {NAME =~ */u_uart_rx/rx_meta_reg/D}]
set_false_path -from [get_ports rst_n] -to [get_pins -hier -filter {NAME =~ *u_epoch/reset_release_reg*/CLR}]
set_max_delay -datapath_only -from [get_clocks -include_generated_clocks clk] -to [get_ports uart_tx_pin] 40.000
