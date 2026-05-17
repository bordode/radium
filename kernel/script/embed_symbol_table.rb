RECORD_SIZE = 32
TABLE_SIZE = 65536

bin = File.binread("radium.bin")
i = bin.index("@@@ PANIC SYMBOL TABLE @@@".b)

`nm radium.bin`.lines.map { |line|
  hex_addr, _, name = line.chomp.split
  bin[i, RECORD_SIZE] = [hex_addr.to_i(16), name].pack("L<a#{RECORD_SIZE - 5}") + "\0"
  i += RECORD_SIZE
  if i >= TABLE_SIZE
    fail "symbol table overflow"
  end
}

bin[i, 4] = "\0\0\0\0".b

File.open("radium.bin", "wb") do |f|
  f.write bin
end

puts "Wrote #{i / RECORD_SIZE} symbols"
