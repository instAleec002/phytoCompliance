<#
.SYNOPSIS
    Cómo va la corrida de variantes de troceado (troceado_variantes.ps1): qué variante y qué paso, cuánto lleva, el
    avance de la codificación en el equipo con GPU, la hora estimada de fin y los resultados de las que ya terminaron.

    Lee registro.log de la corrida (la más reciente, o -Carpeta) y, si está codificando, el estado del trabajo en el
    equipo con GPU. Las duraciones de cada paso se estiman con las variantes ya hechas de la misma corrida.

    pwsh -File ops/troceado_estado.ps1             # una vez
    pwsh -File ops/troceado_estado.ps1 -Seguir     # se actualiza cada 30 s hasta Ctrl+C o el fin de la corrida
    make troceado-estado [SEGUIR=si]
#>
param([string]$Carpeta, [switch]$Seguir, [int]$Segundos = 30, [switch]$SinGpu)
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$repo = Split-Path $PSScriptRoot -Parent
$gpu = $env:TP_GPU_DIR   # carpeta compartida con el equipo de la GPU
if (-not $Carpeta) {
    $Carpeta = Get-ChildItem (Join-Path $repo 'non_local\non_data\work\troceado') -Directory | Sort-Object Name | Select-Object -Last 1 | ForEach-Object FullName
}
# un paso por línea del registro: cuál termina con qué texto
$pasos = [ordered]@{ indexar = '· (ya )?indexado'; vectores = '· vectores:'; juicios = '· juicios:'; medir = '· idf/hibrido' }

function Read-Corrida {
    $inicio = [datetime]::ParseExact((Split-Path $Carpeta -Leaf), 'yyyy-MM-dd_HHmm', $null)
    $dia = $inicio.Date; $previa = $inicio
    $eventos = foreach ($l in Get-Content (Join-Path $Carpeta 'registro.log') -Encoding utf8) {
        if ($l -notmatch '^(\d\d:\d\d:\d\d)\s+(.*)$') { continue }
        $t = $dia + [timespan]::Parse($Matches[1])
        if ($t -lt $previa.AddMinutes(-1)) { $dia = $dia.AddDays(1); $t = $t.AddDays(1) }   # pasó la medianoche
        $previa = $t
        [pscustomobject]@{ Hora = $t; Texto = $Matches[2] }
    }
    $lista = @(); $vars = [ordered]@{}
    foreach ($e in $eventos) {
        if ($e.Texto -match '^inicio · variantes: (.+?) · carpeta') { $lista = @($Matches[1] -split ',\s*') }
        if ($e.Texto -match '^== (\S+) · (.+)$') {
            $v = $Matches[1]
            $vars[$v] = [pscustomobject]@{ Variante = $v; Nombre = $Matches[2]; Inicio = $e.Hora; Fin = $null; Pasos = [ordered]@{}; Firma = $null; Resultado = $null; Error = $null; Ultimo = $e.Hora }
            continue
        }
        if ($e.Texto -match '^(\S+) · (.*)$' -and $vars.Contains($Matches[1])) {
            $x = $vars[$Matches[1]]; $resto = $Matches[2]
            foreach ($p in $pasos.Keys) {
                if ("· $resto" -match $pasos[$p]) { $x.Pasos[$p] = ($e.Hora - $x.Ultimo).TotalMinutes; $x.Ultimo = $e.Hora }
            }
            if ($resto -match 'firma ([0-9a-f]{12})') { $x.Firma = $Matches[1] }
            if ($resto -match "^idf/hibrido (.*)$") { $x.Resultado = $Matches[1]; $x.Fin = $e.Hora }
            if ($resto -match '^FALLÓ: (.*)$') { $x.Error = $Matches[1]; $x.Fin = $e.Hora }
        }
    }
    [pscustomobject]@{ Lista = $lista; Variantes = $vars; Fin = [bool]($eventos | Where-Object Texto -eq 'fin') }
}

function Get-Metrica([string]$Texto, [string]$Nombre) {
    if ($Texto -match "'$([regex]::Escape($Nombre))': ([0-9.]+)") { [double]$Matches[1] } else { $null }
}

function Show-Estado {
    $c = Read-Corrida
    $ahora = Get-Date
    $hechas = @($c.Variantes.Values | Where-Object Fin)
    # minutos típicos de cada paso: promedio de las variantes de esta corrida que lo hicieron
    $tipico = @{}
    foreach ($p in $pasos.Keys) {
        $vals = @($hechas | ForEach-Object { if ($_.Pasos.Contains($p)) { $_.Pasos[$p] } } | Where-Object { $_ -gt 0.2 })
        $tipico[$p] = if ($vals) { ($vals | Measure-Object -Average).Average } else { @{ indexar = 11; vectores = 30; juicios = 5; medir = 2 }[$p] }
    }
    $porVariante = ($tipico.Values | Measure-Object -Sum).Sum
    "== Corrida $(Split-Path $Carpeta -Leaf) · $($ahora.ToString('HH:mm:ss'))"

    # resultados de las que terminaron
    if ($hechas) {
        ''
        '{0,-5} {1,-34} {2,8} {3,8} {4,8} {5,8} {6,7}' -f 'var', 'qué', 'util@10', 'MRR@10', 'nDCG@10', 'R@10', 'min'
        foreach ($h in $hechas) {
            $min = [math]::Round(($h.Fin - $h.Inicio).TotalMinutes)
            if ($h.Error) { '{0,-5} {1,-34} FALLÓ: {2}' -f $h.Variante, $h.Nombre, $h.Error; continue }
            '{0,-5} {1,-34} {2,8} {3,8} {4,8} {5,8} {6,7}' -f $h.Variante, ($h.Nombre.Substring(0, [math]::Min(34, $h.Nombre.Length))),
                (Get-Metrica $h.Resultado 'util@10'), (Get-Metrica $h.Resultado 'mrr@10'), (Get-Metrica $h.Resultado 'ndcg@10'), (Get-Metrica $h.Resultado 'recall@10'), $min
        }
        '(V0, la línea base: util@10 0.783 · MRR@10 0.809 · nDCG@10 0.531 · R@10 0.359)'
    }

    # la que corre ahora
    $actual = @($c.Variantes.Values | Where-Object { -not $_.Fin }) | Select-Object -Last 1
    $restante = 0
    ''
    if ($actual) {
        $siguiente = @($pasos.Keys | Where-Object { -not $actual.Pasos.Contains($_) })[0]
        $lleva = ($ahora - $actual.Ultimo).TotalMinutes
        $linea = "Ahora: $($actual.Variante) · $($actual.Nombre) · paso «$siguiente» hace $([math]::Round($lleva)) min (suele tardar ~$([math]::Round($tipico[$siguiente])) min)"
        $faltaPaso = [math]::Max(1, $tipico[$siguiente] - $lleva)
        if ($siguiente -eq 'vectores' -and $actual.Firma -and -not $SinGpu) {
            $est = pwsh -NoProfile -File "$gpu\gpu_job.ps1" estado -Nombre "vectores_$($actual.Firma)" 2>&1 | ForEach-Object { "$_" }
            $cod = $est | Select-String 'codificando: (\d+)/(\d+)' | Select-Object -Last 1
            $gpuLinea = $est | Select-Object -Last 1
            if ($cod) {
                $k = [int]$cod.Matches[0].Groups[1].Value; $n = [int]$cod.Matches[0].Groups[2].Value
                $linea += "`n  equipo con GPU: $k/$n fragmentos ($([math]::Round(100 * $k / $n)) %)"
                # el trabajo arranca un par de minutos después de exportar: el ritmo se mide desde ahí
                $ritmo = $k / [math]::Max(0.5, $lleva - 2)
                if ($ritmo -gt 0) { $faltaPaso = ($n - $k) / $ritmo }
            } elseif ($est -match 'terminado') { $linea += "`n  equipo con GPU: codificación terminada, trayendo e importando"; $faltaPaso = 2 }
            else { $linea += "`n  equipo con GPU: todavía exportando o arrancando el trabajo" }
            if ($gpuLinea -match '^(\d+) %, (\d+) MiB, (\d+) MiB, (\d+), ([0-9.]+) W') {
                $linea += "  · GPU $($Matches[1]) % · VRAM $($Matches[2])/$($Matches[3]) MiB · $($Matches[4]) °C · $([math]::Round([double]$Matches[5])) W"
            }
        }
        $linea
        $restante += $faltaPaso
        $restante += (@($pasos.Keys | Where-Object { -not $actual.Pasos.Contains($_) }) | Select-Object -Skip 1 | ForEach-Object { $tipico[$_] } | Measure-Object -Sum).Sum
    } elseif ($c.Fin) { 'La corrida terminó.' }
    $pendientes = @($c.Lista | Where-Object { -not $c.Variantes.Contains($_) })
    if ($pendientes) { "Después: $($pendientes -join ', ')"; $restante += $pendientes.Count * $porVariante }
    if (-not $c.Fin -or $actual) {
        "Fin estimado: ~$($ahora.AddMinutes($restante).ToString('HH:mm')) (faltan ~$([math]::Round($restante)) min; cada variante tarda ~$([math]::Round($porVariante)) min)"
    }
    # lo que espera a que la corrida termine (V6b de la etapa 3)
    $v6b = Join-Path $Carpeta 'V6b-indexar.log'
    if ((Test-Path $v6b) -and -not $c.Variantes.Contains('V6b')) {
        $ok = Select-String $v6b -Pattern '"firma"' -Quiet
        "V6b: $(if ($ok) { 'indexada; codifica, juzga y mide cuando la corrida libere el equipo con GPU' } else { 'indexándose en esta PC' })"
        if ($ok) { "  con V6b: ~$($ahora.AddMinutes($restante + $porVariante - $tipico['indexar']).ToString('HH:mm'))" }
    }
    $script:Termino = $c.Fin -and -not $actual
}

do {
    if ($Seguir) { Clear-Host }
    Show-Estado
    if (-not $Seguir -or $script:Termino) { break }
    Start-Sleep -Seconds $Segundos
} while ($true)
