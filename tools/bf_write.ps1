<#
  bf_write.ps1 - Escritura segura en Baofeng UV-S9X3 / UV-S Plus tri.

  1. Handshake y lectura COMPLETA de la radio (copia previa, se guarda).
  2. Aborta si la radio no coincide con -Base (la imagen sobre la que se hizo el plan).
  3. Escribe solo los bloques de 16 B que difieren entre -Base y -Target,
     y solo en 0x0000-0x07FF (canales) y 0x1000-0x17FF (nombres).
  4. Relee toda la radio y compara con -Target.

  Uso: .\bf_write.ps1 -Base base.bin -Target objetivo.bin [-Port COM6] [-DryRun]
#>
param(
    [Parameter(Mandatory)] [string]$Base,
    [Parameter(Mandatory)] [string]$Target,
    [string]$Port = "COM6",
    [string]$OutDir = "$PSScriptRoot\..\backups\writes",
    [switch]$DryRun,
    [switch]$AllowSettings,  # permite escribir ajustes de menu 0x0E20-0x0E4F
    [switch]$AllowFm         # permite escribir el bloque de emisora FM 0x0F40-0x0F4F
)
$ErrorActionPreference = "Stop"
$MAGIC = [byte[]](0x50,0xBB,0xFF,0x20,0x12,0x07,0x25)

function Hex([byte[]]$b) { if ($null -eq $b) { return "<nada>" }; ($b | ForEach-Object { $_.ToString("X2") }) -join " " }
function Read-Exact($sp, [int]$n) {
    $buf = New-Object byte[] $n; $got = 0
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($got -lt $n -and $sw.ElapsedMilliseconds -lt 1500) {
        if ($sp.BytesToRead -gt 0) { $got += $sp.Read($buf, $got, [Math]::Min($n - $got, $sp.BytesToRead)) }
        else { Start-Sleep -Milliseconds 5 }
    }
    if ($got -lt $n) { if ($got -eq 0) { return $null }; return ,([byte[]]$buf[0..($got-1)]) }
    return ,$buf
}
function Send($sp, [byte[]]$b) { $sp.Write($b, 0, $b.Length) }
function Ident($sp) {
    $sp.DiscardInBuffer(); Send $sp $MAGIC
    $a = Read-Exact $sp 1; if ($null -eq $a -or $a[0] -ne 6) { throw "Sin ACK al handshake ($(Hex $a))" }
    Send $sp ([byte[]](2))
    $id = Read-Exact $sp 8; if ($null -eq $id -or $id[0] -ne 0xAA -or $id[7] -ne 0xDD) { throw "Ident invalido ($(Hex $id))" }
    Send $sp ([byte[]](6))
    $a = Read-Exact $sp 1; if ($null -eq $a -or $a[0] -ne 6) { throw "Radio rechaza clonado" }
    return ,$id
}
function Read-Block($sp, [int]$addr, [int]$size, [bool]$expectAck) {
    Send $sp ([byte[]](0x53, (($addr -shr 8) -band 0xFF), ($addr -band 0xFF), $size))
    if ($expectAck) { $a = Read-Exact $sp 1; if ($null -eq $a -or $a[0] -ne 6) { throw ("Rechazo lectura 0x{0:X4}" -f $addr) } }
    $h = Read-Exact $sp 4
    if ($null -eq $h -or $h.Length -ne 4 -or $h[0] -ne 0x58 -or ((([int]$h[1] -shl 8) -bor $h[2]) -ne $addr) -or $h[3] -ne $size) { throw ("Cabecera invalida 0x{0:X4}: {1}" -f $addr, (Hex $h)) }
    $d = Read-Exact $sp $size
    if ($null -eq $d -or $d.Length -ne $size) { throw ("Bloque incompleto 0x{0:X4}" -f $addr) }
    Send $sp ([byte[]](6)); Start-Sleep -Milliseconds 50
    return ,$d
}
function Read-All($sp) {
    $null = Read-Block $sp 0x1E80 0x40 $false
    $null = Read-Block $sp 0x1EC0 0x40 $true
    $b2 = Read-Block $sp 0x1FC0 0x40 $true
    if ($b2[15] -eq 0xFF) { throw "Radio con 'dropped byte': no soportado por este script" }
    $mem = New-Object byte[] 0x2000
    for ($a = 0; $a -lt 0x2000; $a += 0x40) { [Array]::Copy((Read-Block $sp $a 0x40 $true), 0, $mem, $a, 0x40) }
    return ,$mem
}
function Same($x, $y, [int]$off, [int]$len) {
    for ($i = $off; $i -lt $off + $len; $i++) { if ($x[$i] -ne $y[$i]) { return $false } }; return $true
}
function Open-Port { $p = New-Object System.IO.Ports.SerialPort $Port, 9600, ([IO.Ports.Parity]::None), 8, ([IO.Ports.StopBits]::One); $p.Open(); return $p }

$baseImg = [IO.File]::ReadAllBytes((Resolve-Path $Base)); $tgt = [IO.File]::ReadAllBytes((Resolve-Path $Target))
if ($baseImg.Length -lt 0x2000 -or $tgt.Length -lt 0x2000) { throw "Imagenes de tamano incorrecto" }

# Bloques a escribir (solo zonas permitidas)
$blocks = @()
for ($a = 0; $a -lt 0x2000; $a += 0x10) {
    if (-not (Same $baseImg $tgt $a 0x10)) {
        if (-not ($a -lt 0x0800 -or ($a -ge 0x1000 -and $a -lt 0x1800) -or ($AllowSettings -and $a -ge 0x0E20 -and $a -lt 0x0E50) -or ($AllowFm -and $a -eq 0x0F40))) { throw ("Cambio en zona protegida 0x{0:X4}: abortado" -f $a) }
        $blocks += $a
    }
}
Write-Host ("Bloques a escribir: {0} -> {1}" -f $blocks.Count, (($blocks | ForEach-Object { $_.ToString("X4") }) -join " "))
New-Item -ItemType Directory -Force $OutDir | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"

$sp = Open-Port
try {
    $null = Ident $sp
    $cur = [byte[]](Read-All $sp)
    [IO.File]::WriteAllBytes((Join-Path $OutDir "prewrite_$ts.bin"), $cur)
    Write-Host "Copia previa guardada: prewrite_$ts.bin (SHA256 $((Get-FileHash (Join-Path $OutDir "prewrite_$ts.bin")).Hash))"
    if (-not (Same $cur $baseImg 0 0x2000)) {
        $d = @(); for ($i = 0; $i -lt 0x2000; $i++) { if ($cur[$i] -ne $baseImg[$i]) { $d += ("{0:X4}" -f $i) } }
        throw "La radio NO coincide con la imagen base ($($d.Count) bytes: $($d[0..9] -join ' ')...). Abortado sin escribir."
    }
    Write-Host "Radio coincide con la base. OK" -ForegroundColor Green
    if ($DryRun) { Write-Host "DryRun: no se escribe nada."; return }

    foreach ($a in $blocks) {
        $frame = [byte[]](0x58, (($a -shr 8) -band 0xFF), ($a -band 0xFF), 0x10) + [byte[]]$tgt[$a..($a + 15)]
        Send $sp $frame; Start-Sleep -Milliseconds 50
        $ack = Read-Exact $sp 1
        if ($null -eq $ack -or $ack[0] -ne 6) { throw ("ACK erroneo escribiendo 0x{0:X4} ({1})" -f $a, (Hex $ack)) }
    }
    Write-Host "Escritura completada ($($blocks.Count) bloques)." -ForegroundColor Green
}
finally { $sp.Close() }

if (-not $DryRun) {
    Start-Sleep -Seconds 4
    $sp = Open-Port
    try { $null = Ident $sp; $after = [byte[]](Read-All $sp) } finally { $sp.Close() }
    [IO.File]::WriteAllBytes((Join-Path $OutDir "postwrite_$ts.bin"), $after)
    $okZones = (Same $after $tgt 0 0x0800) -and (Same $after $tgt 0x1000 0x0800) -and (-not $AllowSettings -or (Same $after $tgt 0x0E20 0x30)) -and (-not $AllowFm -or (Same $after $tgt 0x0F40 0x10))
    $d = @(); for ($i = 0; $i -lt 0x2000; $i++) { if ($after[$i] -ne $tgt[$i]) { $d += ("{0:X4}" -f $i) } }
    if (-not $okZones) { throw "VERIFICACION FALLIDA en canales/nombres: $($d.Count) bytes difieren: $($d[0..19] -join ' ')" }
    if ($d.Count -eq 0) { Write-Host "VERIFICADO: la radio coincide byte a byte con el objetivo." -ForegroundColor Green }
    else { Write-Host "VERIFICADO canales y nombres. Otras diferencias (estado de la radio): $($d -join ' ')" -ForegroundColor Yellow }
}




