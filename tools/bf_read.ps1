<#
  bf_read.ps1 - Lectura (SOLO LECTURA) de memoria de walkies Baofeng familia
  UV-5R / WP970I / UV-S9X3 (protocolo "S addr len" -> "X addr len data").
  Nunca envia comandos de escritura ('X'). Basado en el protocolo documentado
  en CHIRP (chirp/drivers/baofeng_common.py).

  Uso:  .\bf_read.ps1 -Port COM6 [-ProbeOnly] [-OutDir ..\backups]
#>
param(
    [string]$Port = "COM6",
    [switch]$ProbeOnly,
    [string]$OutDir = "$PSScriptRoot\..\backups"
)
$ErrorActionPreference = "Stop"

# Magics conocidos (nombre, bytes, clase CHIRP, modelo CHIRP)
$magics = @(
    @{ Name = "UV-S9X3 / 5RX (tribanda)"; Bytes = [byte[]](0x50,0xBB,0xFF,0x20,0x12,0x07,0x25); RClass = "UVS9X3"; Model = "UV-S9X3" },
    @{ Name = "WP970I / BF-A58S";         Bytes = [byte[]](0x50,0xBB,0xFF,0x20,0x14,0x04,0x13); RClass = "BFA58S"; Model = "BF-A58S" },
    @{ Name = "UV-9G";                    Bytes = [byte[]](0x50,0xBB,0xFF,0x20,0x12,0x05,0x25); RClass = "UV9G";   Model = "UV-9G" },
    @{ Name = "UV-5R (BFB291+)";          Bytes = [byte[]](0x50,0xBB,0xFF,0x20,0x12,0x07,0x25); RClass = "BaofengUV5R"; Model = "UV-5R" },
    @{ Name = "UV-5R (orig)";             Bytes = [byte[]](0x50,0xBB,0xFF,0x01,0x25,0x98,0x4D); RClass = "BaofengUV5R"; Model = "UV-5R" }
)

function Hex([byte[]]$b) { if ($null -eq $b) { return "<nada>" }; ($b | ForEach-Object { $_.ToString("X2") }) -join " " }

function Read-Exact($sp, [int]$n) {
    $buf = New-Object byte[] $n; $got = 0
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($got -lt $n -and $sw.ElapsedMilliseconds -lt 1500) {
        if ($sp.BytesToRead -gt 0) { $got += $sp.Read($buf, $got, [Math]::Min($n - $got, $sp.BytesToRead)) }
        else { Start-Sleep -Milliseconds 5 }
    }
    if ($got -lt $n) { if ($got -eq 0) { return $null }; return $buf[0..($got-1)] }
    return $buf
}

function Send($sp, [byte[]]$b) { $sp.Write($b, 0, $b.Length) }

function Try-Ident($sp, $m) {
    $sp.DiscardInBuffer()
    Send $sp $m.Bytes
    $ack = Read-Exact $sp 1
    if ($null -eq $ack -or $ack[0] -ne 0x06) { return @{ Ok = $false; Why = "ack1=" + (Hex $ack) } }
    Send $sp ([byte[]](0x02))
    $ident = Read-Exact $sp 8
    if ($null -eq $ident -or $ident.Length -ne 8 -or $ident[0] -ne 0xAA -or $ident[7] -ne 0xDD) {
        return @{ Ok = $false; Why = "ident=" + (Hex $ident) }
    }
    Send $sp ([byte[]](0x06))
    $ack2 = Read-Exact $sp 1
    if ($null -eq $ack2 -or $ack2[0] -ne 0x06) { return @{ Ok = $false; Why = "ack2=" + (Hex $ack2) } }
    return @{ Ok = $true; Ident = $ident }
}

function Read-Block($sp, [int]$addr, [int]$size, [bool]$expectAck) {
    Send $sp ([byte[]](0x53, (($addr -shr 8) -band 0xFF), ($addr -band 0xFF), $size))
    if ($expectAck) {
        $a = Read-Exact $sp 1
        if ($null -eq $a -or $a[0] -ne 0x06) { throw ("Radio rechaza bloque 0x{0:X4} (ack={1})" -f $addr, (Hex $a)) }
    }
    $hdr = Read-Exact $sp 4
    if ($null -eq $hdr -or $hdr.Length -ne 4 -or $hdr[0] -ne 0x58 -or ((([int]$hdr[1] -shl 8) -bor $hdr[2]) -ne $addr) -or $hdr[3] -ne $size) {
        throw ("Cabecera invalida en 0x{0:X4}: {1}" -f $addr, (Hex $hdr))
    }
    $d = Read-Exact $sp $size
    if ($null -eq $d -or $d.Length -ne $size) { throw ("Bloque incompleto 0x{0:X4}" -f $addr) }
    Send $sp ([byte[]](0x06)); Start-Sleep -Milliseconds 50
    return ,$d
}

$sp = New-Object System.IO.Ports.SerialPort $Port, 9600, ([System.IO.Ports.Parity]::None), 8, ([System.IO.Ports.StopBits]::One)
$sp.ReadTimeout = 1500; $sp.WriteTimeout = 1500
$sp.Open()
try {
    $found = $null; $ident = $null
    foreach ($m in $magics) {
        Write-Host ("Probando handshake {0} ({1}) ..." -f $m.Name, (Hex $m.Bytes))
        $r = Try-Ident $sp $m
        if ($r.Ok) { $found = $m; $ident = $r.Ident; Write-Host ("  OK -> ident {0}" -f (Hex $ident)) -ForegroundColor Green; break }
        Write-Host ("  sin respuesta valida: {0}" -f $r.Why) -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
    if (-not $found) { throw "La radio no respondio a ningun handshake de la familia UV-5R/WP970I." }

    # Version de firmware / deteccion de 'dropped byte' (igual que CHIRP)
    $null = Read-Block $sp 0x1E80 0x40 $false
    $b1 = Read-Block $sp 0x1EC0 0x40 $true
    $b2 = Read-Block $sp 0x1FC0 0x40 $true
    $fw = [Text.Encoding]::ASCII.GetString($b1, 48, 14)
    $dropped = ($b2[15] -eq 0xFF)
    Write-Host ("Firmware: '{0}'  | dropped-byte: {1}" -f $fw.Trim([char]0, [char]0xFF, ' '), $dropped)
    if ($ProbeOnly) { return }

    $mem = New-Object System.Collections.Generic.List[byte]
    $end = if ($dropped) { 0x2000 - 0x40 } else { 0x2000 }
    for ($a = 0; $a -lt $end; $a += 0x40) {
        $mem.AddRange([byte[]](Read-Block $sp $a 0x40 $true))
        Write-Progress -Activity "Leyendo radio" -PercentComplete ([int](100 * $a / 0x2000))
    }
    if ($dropped) { for ($a = 0x2000 - 0x40; $a -lt 0x2000; $a += 0x10) { $mem.AddRange([byte[]](Read-Block $sp $a 0x10 $true)) } }
    Write-Progress -Activity "Leyendo radio" -Completed

    New-Item -ItemType Directory -Force $OutDir | Out-Null
    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
    $raw = [byte[]]$mem.ToArray()
    $base = Join-Path (Resolve-Path $OutDir) ("UV-SPlus_{0}" -f $ts)
    [IO.File]::WriteAllBytes("$base.bin", $raw)

    # .img compatible CHIRP: mmap + ident + MAGIC + base64(json)
    $meta = @{ rclass = $found.RClass; vendor = "Baofeng"; model = $found.Model; variant = ""; chirp_version = "bf_read.ps1"; firmware = $fw } | ConvertTo-Json -Compress
    $magic = [byte[]](0x00,0xFF) + [Text.Encoding]::ASCII.GetBytes("chirp") + [byte[]](0xEE) + [Text.Encoding]::ASCII.GetBytes("img") + [byte[]](0x00,0x01)
    $img = $raw + $ident + $magic + [Text.Encoding]::ASCII.GetBytes([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($meta)))
    [IO.File]::WriteAllBytes("$base.img", $img)
    $sha = (Get-FileHash "$base.bin" -Algorithm SHA256).Hash
    Write-Host "Guardado: $base.bin ($($raw.Length) bytes, SHA256 $sha)" -ForegroundColor Green
    Write-Host "Guardado: $base.img (abrible en CHIRP como $($found.Model))" -ForegroundColor Green
}
finally { $sp.Close() }

