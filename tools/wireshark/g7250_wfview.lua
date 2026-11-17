-- g7250_wfview.lua - Wireshark dissector for the Xiegu G7250 wfview LAN mode
--
-- Independent implementation written from the repository documentation
-- (main_unit/docs/network.md, main_unit/analysis/peripherals/ch394_network.csv,
-- docs/civ.md, docs/protocol.md). See README.md in this directory.
--
-- Documented facts used here:
--   * Three UDP sockets: control on the base port P (settings 0x180),
--     CI-V on P+1, audio on P+2. The base port is configurable on the radio,
--     so it is a preference here.
--   * The radio emulates an Icom network radio (IC-7300, CI-V address 0xA0).
--   * Handshake: are-you-there (or a plain-text probe) -> I-am-here,
--     handshake order: ready check, login, token, then capability and connection-info packets from the
--     radio, conninfo from the client -> status, then streaming.
--   * Pings every 100 ms (control, CI-V) / 500 ms (audio); retransmit
--     requests are served.
--   * CI-V frames are FE FE <to> <from> <cmd> ... FD; the radio accepts only
--     to-address 0xA0 or 0x00.
--   * RX audio: LPCM 16-bit or 8-bit mono, 48 or 16 kHz, chunks of at most
--     1364 bytes every 20 ms.
--
-- NOT in the repository documentation:
--   * The byte layout of the Icom-style packets. The 16-byte common header
--     decoded below (length, type, sequence, sender id, receiver id, all
--     little-endian) follows the generally known public description of the
--     Icom network protocol. It can be switched off in the preferences;
--     then every packet is shown as unknown bytes.
--   * The layout of the login, token, capabilities, conninfo and status
--     bodies. These packets are only *named* (by their usual length, marked
--     as a guess) and their bodies are shown as unknown bytes. Credentials
--     are not decoded.
--   * The CI-V sub-command numbers. Only the top-level command map from
--     docs/civ.md is named; sub-commands are shown as raw bytes.

local DEFAULT_BASE = 50001
local HDSDR_MAGIC  = 0xAA5555AA
local HDR_LEN      = 16
local CIV_ADDR     = 0xA0
local AUDIO_MAX    = 1364

local p = Proto("g7250_wfview", "Xiegu G7250 wfview LAN (Icom-style)")

local socket_names = { [0] = "Control", [1] = "CI-V", [2] = "Audio" }

-- Common header packet types (public Icom network protocol convention).
local type_names = {
    [0x00] = "Data / idle",
    [0x01] = "Retransmit request",
    [0x03] = "Are you there",
    [0x04] = "I am here",
    [0x05] = "Disconnect",
    [0x06] = "Are you ready / ready",
    [0x07] = "Ping / pong",
}

-- Control-socket data packets, named by their usual length only.
local ctrl_len_names = {
    [0x40] = "Token (guess by length)",
    [0x50] = "Status (guess by length)",
    [0x60] = "Login response (guess by length)",
    [0x80] = "Login (guess by length)",
    [0x90] = "Conninfo (guess by length)",
    [0xA8] = "Capabilities (guess by length)",
}

-- Top-level CI-V command map (docs/civ.md, Main Unit wfview CI-V).
local civ_cmds = {
    [0x00] = "Transceive frequency",
    [0x01] = "Transceive mode",
    [0x02] = "Band edges (inline 0x00-0x06 path)",
    [0x03] = "Read frequency",
    [0x04] = "Read mode",
    [0x05] = "Select/read VFO (G7250 quirk: no frequency set)",
    [0x06] = "Set mode",
    [0x07] = "VFO operation",
    [0x0F] = "Split",
    [0x11] = "Attenuator",
    [0x12] = "Antenna",
    [0x14] = "Level",
    [0x15] = "Meter",
    [0x16] = "Function",
    [0x19] = "Transceiver ID",
    [0x1A] = "Extended (band stack, filter width, AGC, data mode)",
    [0x1C] = "PTT / ATU",
    [0x21] = "RIT",
    [0x25] = "Frequency (selected/unselected VFO)",
    [0x26] = "Mode (selected/unselected VFO)",
    [0x27] = "Scope",
    [0x29] = "VFO prefix (selector ignored, inner command re-dispatched)",
    [0xFA] = "NG",
    [0xFB] = "OK",
}

local f = {
    socket    = ProtoField.uint8("g7250_wfview.socket", "Socket", base.DEC, socket_names),
    probe     = ProtoField.string("g7250_wfview.probe", "Plain-text probe"),
    len       = ProtoField.uint32("g7250_wfview.len", "Length", base.DEC),
    ptype     = ProtoField.uint16("g7250_wfview.type", "Type", base.HEX, type_names),
    seq       = ProtoField.uint16("g7250_wfview.seq", "Sequence", base.DEC),
    sentid    = ProtoField.uint32("g7250_wfview.sentid", "Sender id", base.HEX),
    rcvdid    = ProtoField.uint32("g7250_wfview.rcvdid", "Receiver id", base.HEX),
    kind      = ProtoField.string("g7250_wfview.kind", "Packet"),
    rtx_seq   = ProtoField.uint16("g7250_wfview.rtx_seq", "Requested sequence", base.DEC),
    unknown   = ProtoField.bytes("g7250_wfview.unknown", "Unknown bytes"),
    -- CI-V
    civ       = ProtoField.bytes("g7250_wfview.civ", "CI-V frame"),
    civ_to    = ProtoField.uint8("g7250_wfview.civ.to", "To address", base.HEX),
    civ_from  = ProtoField.uint8("g7250_wfview.civ.from", "From address", base.HEX),
    civ_cmd   = ProtoField.uint8("g7250_wfview.civ.cmd", "Command", base.HEX, civ_cmds),
    civ_sub   = ProtoField.uint8("g7250_wfview.civ.sub", "Sub-command", base.HEX),
    civ_vfo   = ProtoField.uint8("g7250_wfview.civ.vfo", "VFO selector", base.HEX),
    civ_freq  = ProtoField.uint64("g7250_wfview.civ.freq", "Frequency (Hz, BCD)", base.DEC),
    civ_data  = ProtoField.bytes("g7250_wfview.civ.data", "Data"),
    -- Audio
    audio     = ProtoField.bytes("g7250_wfview.audio", "LPCM audio"),
    audio_len = ProtoField.uint16("g7250_wfview.audio.len", "Audio bytes", base.DEC),
    audio_n   = ProtoField.uint16("g7250_wfview.audio.samples", "Samples (mono)", base.DEC),
}
p.fields = f

local e = {
    short    = ProtoExpert.new("g7250_wfview.short", "Packet shorter than the common header",
                               expert.group.MALFORMED, expert.severity.ERROR),
    len_mis  = ProtoExpert.new("g7250_wfview.len_mismatch", "Header length does not match datagram length",
                               expert.group.MALFORMED, expert.severity.ERROR),
    unk_type = ProtoExpert.new("g7250_wfview.unknown_type", "Unknown packet type",
                               expert.group.UNDECODED, expert.severity.WARN),
    civ_trunc= ProtoExpert.new("g7250_wfview.civ_trunc", "CI-V frame without FD terminator",
                               expert.group.MALFORMED, expert.severity.ERROR),
    civ_addr = ProtoExpert.new("g7250_wfview.civ_addr", "To-address is neither 0xA0 nor 0x00: the radio ignores this frame",
                               expert.group.PROTOCOL, expert.severity.WARN),
    civ_none = ProtoExpert.new("g7250_wfview.civ_none", "No CI-V frame found in data packet",
                               expert.group.UNDECODED, expert.severity.NOTE),
    civ_bcd  = ProtoExpert.new("g7250_wfview.civ_bcd", "Invalid BCD digit in frequency",
                               expert.group.MALFORMED, expert.severity.WARN),
    civ_unk  = ProtoExpert.new("g7250_wfview.civ_unknown", "Command not in the documented map (radio ignores it, no FA)",
                               expert.group.UNDECODED, expert.severity.NOTE),
    civ_wfm  = ProtoExpert.new("g7250_wfview.civ_wfm", "Mode 06 (WFM) is applied as LSB by the G7250",
                               expert.group.PROTOCOL, expert.severity.NOTE),
    audio_big= ProtoExpert.new("g7250_wfview.audio_big", "Audio chunk larger than the documented 1364-byte maximum",
                               expert.group.PROTOCOL, expert.severity.WARN),
    audio_odd= ProtoExpert.new("g7250_wfview.audio_odd", "Odd byte count for 16-bit audio",
                               expert.group.MALFORMED, expert.severity.WARN),
}
p.experts = { e.short, e.len_mis, e.unk_type, e.civ_trunc, e.civ_addr, e.civ_none,
              e.civ_bcd, e.civ_unk, e.civ_wfm, e.audio_big, e.audio_odd }

p.prefs.base_port = Pref.uint("Base UDP port", DEFAULT_BASE,
    "Radio LAN base port (settings offset 0x180). Control = P, CI-V = P+1, audio = P+2.")
p.prefs.icom_header = Pref.bool("Decode Icom common header", true,
    "Decode the 16-byte Icom-style header. Its layout is NOT in the repository " ..
    "documentation; switch off to show raw bytes only.")
p.prefs.audio_8bit = Pref.bool("Audio is 8-bit", false,
    "The negotiated sample width is not visible here; default 16-bit LPCM.")
p.prefs.audio_hdr = Pref.uint("Audio header length", 0x18,
    "Bytes before the LPCM samples in an audio data packet (undocumented; default 0x18).")
p.prefs.civ_ofs = Pref.uint("CI-V search start", 0x10,
    "Offset from which the CI-V data packet is scanned for FE FE (undocumented header).")

-- Return 0/1/2 for control/CI-V/audio, or nil.
local function socket_of(pinfo)
    local b = p.prefs.base_port
    for _, port in ipairs({ pinfo.dst_port, pinfo.src_port }) do
        local d = port - b
        if d >= 0 and d <= 2 then return d end
    end
    return nil
end

local function bcd_freq(tvb, ofs, n, item)
    -- Icom BCD: least significant byte first, two digits per byte.
    local hz, mul, bad = 0, 1, false
    for k = 0, n - 1 do
        local b = tvb(ofs + k, 1):uint()
        local lo, hi = b % 16, math.floor(b / 16)
        if lo > 9 or hi > 9 then bad = true end
        hz = hz + lo * mul + hi * mul * 10
        mul = mul * 100
    end
    return hz, bad
end

local function civ_frame(tree, tvb, s, eof, pinfo)
    -- s = offset of first FE, eof = offset of FD (or nil if truncated)
    local stop = eof and eof or (tvb:len() - 1)
    local fr = tree:add(f.civ, tvb(s, stop - s + 1))
    if not eof then fr:add_proto_expert_info(e.civ_trunc) end
    local o = s + 2
    local data_end = eof and (eof - 1) or stop   -- last data byte (inclusive)
    if o + 1 > data_end then
        fr:add_proto_expert_info(e.civ_trunc)
        return "CI-V (no addresses)"
    end
    local to = tvb(o, 1):uint()
    local from = tvb(o + 1, 1):uint()
    local ti = fr:add(f.civ_to, tvb(o, 1))
    fr:add(f.civ_from, tvb(o + 1, 1))
    if from ~= CIV_ADDR and to ~= CIV_ADDR and to ~= 0x00 then
        ti:add_proto_expert_info(e.civ_addr)
    end
    o = o + 2
    if o > data_end then return "CI-V (no command)" end
    local cmd = tvb(o, 1):uint()
    local ci = fr:add(f.civ_cmd, tvb(o, 1))
    o = o + 1
    -- 0x29 VFO prefix: selector byte, then the inner command.
    if cmd == 0x29 and o + 1 <= data_end then
        fr:add(f.civ_vfo, tvb(o, 1))
        cmd = tvb(o + 1, 1):uint()
        ci = fr:add(f.civ_cmd, tvb(o + 1, 1))
        ci:append_text(" (inner)")
        o = o + 2
    end
    local name = civ_cmds[cmd]
    if not name then ci:add_proto_expert_info(e.civ_unk) end
    local dir = (from == CIV_ADDR) and "radio" or "PC"
    fr:append_text(string.format(": %02X->%02X cmd %02X %s", from, to, cmd, name or "?"))
    local summary = string.format("CI-V %02X %s", cmd, name and name:match("^[^(]+"):gsub("%s+$", "") or "?")
    local dlen = data_end - o + 1

    local function freq_at(ofs)
        local hz, bad = bcd_freq(tvb, ofs, 5)
        local fi = fr:add(f.civ_freq, tvb(ofs, 5), UInt64(hz))
        if bad then fi:add_proto_expert_info(e.civ_bcd) end
        summary = summary .. string.format(" %d Hz", hz)
    end

    if (cmd == 0x00 or cmd == 0x03) and dlen == 5 then
        freq_at(o); o = o + 5
    elseif cmd == 0x25 and dlen >= 1 then
        fr:add(f.civ_vfo, tvb(o, 1)); o = o + 1
        if dlen == 6 then freq_at(o); o = o + 5 end
    elseif cmd == 0x26 and dlen >= 1 then
        fr:add(f.civ_vfo, tvb(o, 1)); o = o + 1
    elseif (cmd == 0x14 or cmd == 0x15 or cmd == 0x16 or cmd == 0x1A
            or cmd == 0x1C or cmd == 0x21 or cmd == 0x27 or cmd == 0x07
            or cmd == 0x11 or cmd == 0x12) and dlen >= 1 then
        fr:add(f.civ_sub, tvb(o, 1)); o = o + 1
    elseif cmd == 0x06 and dlen >= 1 and from ~= CIV_ADDR then
        if tvb(o, 1):uint() == 0x06 then ci:add_proto_expert_info(e.civ_wfm) end
    end
    if o <= data_end then
        fr:add(f.civ_data, tvb(o, data_end - o + 1))
    end
    return summary .. " [" .. dir .. "]"
end

-- Scan a range for FE FE ... FD frames.
local function dissect_civ(tree, tvb, start, pinfo, hint_item)
    if start >= tvb:len() then
        if hint_item then hint_item:add_proto_expert_info(e.civ_none) end
        return nil
    end
    local n = tvb:len()
    local o = start
    local found = {}
    while o + 1 < n do
        if tvb(o, 1):uint() == 0xFE and tvb(o + 1, 1):uint() == 0xFE then
            local s = o
            while o + 1 < n and tvb(o + 1, 1):uint() == 0xFE do o = o + 1 end
            s = o - 1 -- keep exactly two FE as the preamble
            local eof = nil
            for k = o + 1, n - 1 do
                if tvb(k, 1):uint() == 0xFD then eof = k; break end
            end
            if #found == 0 and s > start then
                tree:add(f.unknown, tvb(start, s - start)):append_text(" (before CI-V preamble, undocumented)")
            end
            table.insert(found, civ_frame(tree, tvb, s, eof, pinfo))
            if not eof then break end
            o = eof + 1
        else
            o = o + 1
        end
    end
    if #found == 0 then
        if hint_item then hint_item:add_proto_expert_info(e.civ_none) end
        return nil
    end
    return table.concat(found, "; ")
end

local function dissect_audio(tree, tvb, pinfo)
    local hl = p.prefs.audio_hdr
    if tvb:len() <= hl then return nil end
    if hl > HDR_LEN then tree:add(f.unknown, tvb(HDR_LEN, hl - HDR_LEN)):append_text(" (audio header, undocumented)") end
    local n = tvb:len() - hl
    local ai = tree:add(f.audio, tvb(hl, n))
    ai:add(f.audio_len, n):set_generated()
    local w = p.prefs.audio_8bit and 1 or 2
    ai:add(f.audio_n, math.floor(n / w)):set_generated()
    if n > AUDIO_MAX then ai:add_proto_expert_info(e.audio_big) end
    if w == 2 and n % 2 == 1 then ai:add_proto_expert_info(e.audio_odd) end
    return string.format("Audio %d B", n)
end

local function is_printable(tvb)
    if tvb:len() == 0 then return false end
    local text = 0
    for k = 0, tvb:len() - 1 do
        local b = tvb(k, 1):uint()
        if b >= 32 and b < 127 then
            text = text + 1
        elseif not (b == 9 or b == 10 or b == 13 or b == 0) then
            return false
        end
    end
    return text > 0
end

local function dissect(tvb, pinfo, root)
    local len = tvb:len()
    local sock = socket_of(pinfo)
    pinfo.cols.protocol = "G7250-wfview"
    local tree = root:add(p, tvb())
    if sock then
        tree:add(f.socket, sock):set_generated()
        tree:append_text(", " .. socket_names[sock])
    end
    local prefix = sock and (socket_names[sock] .. ": ") or ""

    -- Plain-text probe (documented, content undocumented).
    local hdr_ok = len >= HDR_LEN and tvb(0, 4):le_uint() == len
    if not hdr_ok and is_printable(tvb) then
        tree:add(f.probe, tvb())
        pinfo.cols.info = prefix .. "Plain-text probe"
        return len
    end

    if not p.prefs.icom_header then
        tree:add(f.unknown, tvb())
        pinfo.cols.info = prefix .. string.format("%d bytes", len)
        return len
    end

    if len < HDR_LEN then
        tree:add_proto_expert_info(e.short)
        tree:add(f.unknown, tvb())
        pinfo.cols.info = prefix .. "Malformed (short)"
        return len
    end

    local li = tree:add_le(f.len, tvb(0, 4))
    if not hdr_ok then li:add_proto_expert_info(e.len_mis) end
    local ptype = tvb(4, 2):le_uint()
    local ti = tree:add_le(f.ptype, tvb(4, 2))
    tree:add_le(f.seq, tvb(6, 2))
    tree:add_le(f.sentid, tvb(8, 4))
    tree:add_le(f.rcvdid, tvb(12, 4))
    local seq = tvb(6, 2):le_uint()

    local info
    if not type_names[ptype] then
        ti:add_proto_expert_info(e.unk_type)
        info = string.format("Unknown type 0x%04X", ptype)
        if len > HDR_LEN then tree:add(f.unknown, tvb(HDR_LEN)) end
    elseif ptype == 0x00 and len == HDR_LEN then
        info = "Idle"
    elseif ptype == 0x00 then
        if sock == 1 then
            info = dissect_civ(tree, tvb, math.min(p.prefs.civ_ofs, len), pinfo, ti)
            info = info or "CI-V socket data"
        elseif sock == 2 then
            info = dissect_audio(tree, tvb, pinfo) or "Audio socket data"
        else
            local nm = ctrl_len_names[len]
            if nm and sock == 0 then
                tree:add(f.kind, nm):set_generated()
                info = nm
            else
                info = string.format("Data (%d bytes)", len)
            end
            tree:add(f.unknown, tvb(HDR_LEN)):append_text(" (body layout undocumented)")
        end
    elseif ptype == 0x01 then
        info = "Retransmit request"
        if len == HDR_LEN then
            tree:add_le(f.rtx_seq, tvb(6, 2)):set_generated()
            info = info .. string.format(" seq=%d", seq)
        else
            for o = HDR_LEN, len - 2, 2 do
                tree:add_le(f.rtx_seq, tvb(o, 2))
            end
            info = info .. string.format(" (%d seqs)", math.floor((len - HDR_LEN) / 2))
        end
    else
        info = type_names[ptype]
        if len > HDR_LEN then
            tree:add(f.unknown, tvb(HDR_LEN)):append_text(" (body layout undocumented)")
        end
    end
    tree:append_text(", " .. info)
    pinfo.cols.info = prefix .. info .. string.format(" seq=%d", seq)
    return len
end

function p.dissector(tvb, pinfo, root)
    -- HDSDR packets can share these ports (the modes are exclusive).
    if tvb:len() >= 6 and tvb(0, 4):uint() == HDSDR_MAGIC then
        local ok, h = pcall(Dissector.get, "g7250_hdsdr")
        if ok and h then return h:call(tvb, pinfo, root) end
    end
    return dissect(tvb, pinfo, root)
end

local registered = nil
local function register_ports()
    local t = DissectorTable.get("udp.port")
    if registered then
        for d = 0, 2 do t:remove(registered + d, p) end
    end
    registered = p.prefs.base_port
    for d = 0, 2 do t:add(registered + d, p) end
end

function p.prefs_changed()
    if registered ~= p.prefs.base_port then register_ports() end
end

register_ports()
