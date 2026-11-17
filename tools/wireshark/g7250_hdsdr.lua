-- g7250_hdsdr.lua - Wireshark dissector for the Xiegu G7250 HDSDR/IQ LAN mode
--
-- Independent implementation written from the repository documentation
-- (main_unit/docs/network.md, main_unit/analysis/peripherals/ch394_network.csv).
-- See README.md in this directory.
--
-- Documented facts used here:
--   * UDP only, radio local port 50002, default PC destination port 50001.
--   * Every packet: magic AA 55 55 AA, then a 16-bit big-endian command.
--   * 0x0101 discover   PC->radio  PC IPv4 + port (IPv4 0 = use source addr)
--   * 0x0102 heartbeat  PC->radio
--   * 0x0103 set LO     PC->radio  64-bit Hz, accepted 0.5-108 MHz
--   * 0x0201 report     radio->PC  radio IPv4, port 50002, 4-byte device id
--   * 0x0202 IQ         radio->PC  192 complex int16 (I,Q interleaved), 774 B
--   * Session drops after 10 s without heartbeat or discover.
--
-- NOT documented (and therefore preferences / assumptions):
--   * Byte order of the IPv4, port and LO payload fields (default: big-endian,
--     like the command word).
--   * Byte order of the IQ samples (default: little-endian, native order of
--     the radio's MCU).
--   * Exact payload sizes other than the IQ packet; lengths below are the
--     minimum that holds the documented fields. Extra bytes are shown as
--     unknown.

local HDSDR_PORT      = 50002
local HDSDR_DEST_PORT = 50001
local MAGIC           = 0xAA5555AA
local HDR_LEN         = 6
local IQ_SAMPLES      = 192
local IQ_LEN          = HDR_LEN + IQ_SAMPLES * 4   -- 774
local LO_MIN          = 500000
local LO_MAX          = 108000000

local p = Proto("g7250_hdsdr", "Xiegu G7250 HDSDR/IQ LAN")

local cmd_names = {
    [0x0101] = "Discover",
    [0x0102] = "Heartbeat",
    [0x0103] = "Set LO",
    [0x0201] = "Report",
    [0x0202] = "IQ data",
}

local cmd_dir = {
    [0x0101] = "PC->radio",
    [0x0102] = "PC->radio",
    [0x0103] = "PC->radio",
    [0x0201] = "radio->PC",
    [0x0202] = "radio->PC",
}

local f = {
    magic     = ProtoField.uint32("g7250_hdsdr.magic", "Magic", base.HEX),
    cmd       = ProtoField.uint16("g7250_hdsdr.cmd", "Command", base.HEX, cmd_names),
    pc_ip     = ProtoField.ipv4("g7250_hdsdr.pc_ip", "PC IPv4"),
    pc_port   = ProtoField.uint16("g7250_hdsdr.pc_port", "PC port", base.DEC),
    lo_hz     = ProtoField.uint64("g7250_hdsdr.lo_hz", "LO frequency (Hz)", base.DEC),
    radio_ip  = ProtoField.ipv4("g7250_hdsdr.radio_ip", "Radio IPv4"),
    radio_port= ProtoField.uint16("g7250_hdsdr.radio_port", "Radio port", base.DEC),
    dev_id    = ProtoField.uint32("g7250_hdsdr.device_id", "Device id", base.HEX),
    iq        = ProtoField.bytes("g7250_hdsdr.iq", "IQ samples"),
    iq_count  = ProtoField.uint16("g7250_hdsdr.iq_count", "Complex sample count", base.DEC),
    i_peak    = ProtoField.int16("g7250_hdsdr.i_peak", "I peak |value|", base.DEC),
    q_peak    = ProtoField.int16("g7250_hdsdr.q_peak", "Q peak |value|", base.DEC),
    sample_i  = ProtoField.int16("g7250_hdsdr.i", "I", base.DEC),
    sample_q  = ProtoField.int16("g7250_hdsdr.q", "Q", base.DEC),
    unknown   = ProtoField.bytes("g7250_hdsdr.unknown", "Unknown bytes"),
}
p.fields = f

local e = {
    bad_magic = ProtoExpert.new("g7250_hdsdr.bad_magic", "Bad magic (expected AA 55 55 AA)",
                                expert.group.MALFORMED, expert.severity.ERROR),
    short     = ProtoExpert.new("g7250_hdsdr.short", "Packet shorter than the documented layout",
                                expert.group.MALFORMED, expert.severity.ERROR),
    iq_len    = ProtoExpert.new("g7250_hdsdr.iq_len", "IQ packet is not 774 bytes",
                                expert.group.MALFORMED, expert.severity.WARN),
    extra     = ProtoExpert.new("g7250_hdsdr.extra", "Trailing bytes beyond the documented fields",
                                expert.group.PROTOCOL, expert.severity.NOTE),
    unk_cmd   = ProtoExpert.new("g7250_hdsdr.unknown_cmd", "Undocumented command",
                                expert.group.UNDECODED, expert.severity.WARN),
    lo_range  = ProtoExpert.new("g7250_hdsdr.lo_range", "LO outside the accepted 0.5-108 MHz range (radio ignores it)",
                                expert.group.PROTOCOL, expert.severity.WARN),
    ip_zero   = ProtoExpert.new("g7250_hdsdr.ip_zero", "PC IPv4 is 0: radio uses the packet source address",
                                expert.group.PROTOCOL, expert.severity.CHAT),
    port_mis  = ProtoExpert.new("g7250_hdsdr.port_mismatch", "Report port is not the documented 50002",
                                expert.group.PROTOCOL, expert.severity.NOTE),
}
p.experts = { e.bad_magic, e.short, e.iq_len, e.extra, e.unk_cmd, e.lo_range, e.ip_zero, e.port_mis }

p.prefs.payload_le = Pref.bool("Payload fields little-endian", false,
    "Byte order of the port / LO / device-id fields is not documented. " ..
    "Default: big-endian, like the command word.")
p.prefs.iq_be = Pref.bool("IQ samples big-endian", false,
    "Byte order of the int16 IQ samples is not documented. Default: little-endian.")
p.prefs.list_samples = Pref.bool("List individual IQ samples", false,
    "Add every I/Q pair to the tree (192 items per packet).")

-- Add a numeric field honouring the payload byte-order preference.
local function add_num(tree, field, tvbr)
    if p.prefs.payload_le then
        return tree:add_le(field, tvbr)
    end
    return tree:add(field, tvbr)
end

local function num(tvbr)
    if p.prefs.payload_le then
        return tvbr:le_uint64()
    end
    return tvbr:uint64()
end

local function need(tree, tvb, len, item)
    if tvb:len() < len then
        item:add_proto_expert_info(e.short,
            string.format("Packet is %d bytes, at least %d expected", tvb:len(), len))
        return false
    end
    return true
end

local function trailing(tree, tvb, used, item)
    if tvb:len() > used then
        local ti = tree:add(f.unknown, tvb(used))
        ti:add_proto_expert_info(e.extra)
    end
end

local function dissect_iq(tree, tvb, item, pinfo)
    if tvb:len() ~= IQ_LEN then
        item:add_proto_expert_info(e.iq_len,
            string.format("IQ packet is %d bytes, expected %d", tvb:len(), IQ_LEN))
    end
    local avail = tvb:len() - HDR_LEN
    local n = math.floor(avail / 4)
    if n <= 0 then
        item:add_proto_expert_info(e.short)
        return
    end
    local st = tree:add(f.iq, tvb(HDR_LEN, n * 4))
    st:add(f.iq_count, n):set_generated()
    local ip, qp = 0, 0
    for k = 0, n - 1 do
        local o = HDR_LEN + k * 4
        local iv, qv
        if p.prefs.iq_be then
            iv, qv = tvb(o, 2):int(), tvb(o + 2, 2):int()
        else
            iv, qv = tvb(o, 2):le_int(), tvb(o + 2, 2):le_int()
        end
        if math.abs(iv) > ip then ip = math.abs(iv) end
        if math.abs(qv) > qp then qp = math.abs(qv) end
        if p.prefs.list_samples then
            local s = st:add(tvb(o, 4), string.format("Sample %d: I=%d Q=%d", k, iv, qv))
            if p.prefs.iq_be then
                s:add(f.sample_i, tvb(o, 2)); s:add(f.sample_q, tvb(o + 2, 2))
            else
                s:add_le(f.sample_i, tvb(o, 2)); s:add_le(f.sample_q, tvb(o + 2, 2))
            end
        end
    end
    st:add(f.i_peak, math.min(ip, 32767)):set_generated()
    st:add(f.q_peak, math.min(qp, 32767)):set_generated()
    trailing(tree, tvb, HDR_LEN + n * 4, item)
    pinfo.cols.info:append(string.format(" (%d samples)", n))
end

local function dissect(tvb, pinfo, root)
    local len = tvb:len()
    pinfo.cols.protocol = "G7250-HDSDR"
    local tree = root:add(p, tvb())

    if len < 4 then
        tree:add_proto_expert_info(e.short)
        pinfo.cols.info = "Malformed (too short)"
        return len
    end
    local mi = tree:add(f.magic, tvb(0, 4))
    if tvb(0, 4):uint() ~= MAGIC then
        mi:add_proto_expert_info(e.bad_magic)
        pinfo.cols.info = "Bad magic"
        tree:add(f.unknown, tvb(4))
        return len
    end
    if len < HDR_LEN then
        tree:add_proto_expert_info(e.short)
        pinfo.cols.info = "Malformed (no command word)"
        return len
    end

    local cmd = tvb(4, 2):uint()
    local ci = tree:add(f.cmd, tvb(4, 2))
    local name = cmd_names[cmd]
    if not name then
        ci:add_proto_expert_info(e.unk_cmd)
        pinfo.cols.info = string.format("Unknown command 0x%04X", cmd)
        trailing(tree, tvb, HDR_LEN, ci)
        return len
    end
    tree:append_text(string.format(", %s (%s)", name, cmd_dir[cmd]))
    pinfo.cols.info = name

    if cmd == 0x0101 then
        if need(tree, tvb, HDR_LEN + 6, ci) then
            local ipi = tree:add(f.pc_ip, tvb(6, 4))
            if tvb(6, 4):uint() == 0 then ipi:add_proto_expert_info(e.ip_zero) end
            add_num(tree, f.pc_port, tvb(10, 2))
            local port = p.prefs.payload_le and tvb(10, 2):le_uint() or tvb(10, 2):uint()
            pinfo.cols.info:append(string.format(" dest=%s:%d", tostring(tvb(6, 4):ipv4()), port))
            trailing(tree, tvb, HDR_LEN + 6, ci)
        end
    elseif cmd == 0x0102 then
        trailing(tree, tvb, HDR_LEN, ci)
    elseif cmd == 0x0103 then
        if need(tree, tvb, HDR_LEN + 8, ci) then
            local li = add_num(tree, f.lo_hz, tvb(6, 8))
            local hz = num(tvb(6, 8))
            if hz < UInt64(LO_MIN) or hz > UInt64(LO_MAX) then
                li:add_proto_expert_info(e.lo_range)
            end
            pinfo.cols.info:append(" " .. tostring(hz) .. " Hz")
            trailing(tree, tvb, HDR_LEN + 8, ci)
        end
    elseif cmd == 0x0201 then
        if need(tree, tvb, HDR_LEN + 10, ci) then
            tree:add(f.radio_ip, tvb(6, 4))
            local pi = add_num(tree, f.radio_port, tvb(10, 2))
            local port = p.prefs.payload_le and tvb(10, 2):le_uint() or tvb(10, 2):uint()
            if port ~= HDSDR_PORT then pi:add_proto_expert_info(e.port_mis) end
            add_num(tree, f.dev_id, tvb(12, 4))
            pinfo.cols.info:append(string.format(" radio=%s:%d", tostring(tvb(6, 4):ipv4()), port))
            trailing(tree, tvb, HDR_LEN + 10, ci)
        end
    elseif cmd == 0x0202 then
        dissect_iq(tree, tvb, ci, pinfo)
    end
    return len
end

-- Port-table entry. If the payload has no HDSDR magic and the wfview
-- dissector is loaded (wfview mode can use the same ports), hand off to it.
function p.dissector(tvb, pinfo, root)
    if tvb:len() >= 4 and tvb(0, 4):uint() ~= MAGIC then
        local ok, wf = pcall(Dissector.get, "g7250_wfview")
        if ok and wf then
            return wf:call(tvb, pinfo, root)
        end
    end
    return dissect(tvb, pinfo, root)
end

-- Heuristic: magic plus a known command word (any UDP port).
local function heur(tvb, pinfo, root)
    if tvb:len() < HDR_LEN then return false end
    if tvb(0, 4):uint() ~= MAGIC then return false end
    if not cmd_names[tvb(4, 2):uint()] then return false end
    dissect(tvb, pinfo, root)
    pinfo.conversation = p
    return true
end

DissectorTable.get("udp.port"):add(HDSDR_PORT, p)
p:register_heuristic("udp", heur)
