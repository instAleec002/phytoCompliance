<#
.SYNOPSIS
    Elige V7 (etapa 3) con la regla fijada el 24/11/2026 antes de mirar los datos (pendientes/26 de la tesis):
    en la partición de desarrollo de S2 se miden 20 configuraciones (troceados V0, V3, V5, V6b y V1b; sin MMR o con
    MMR 0,85; encabezado en el índice léxico con peso completo o reducido). Gana la de mayor MRR@10; con diferencia
    menor de 0,01, la de mayor utilidad@10; si sigue el empate, la de menos fragmentos. Después mide la ganadora y V0
    en la partición de prueba.

    Cada medición deja su carpeta en ml/evaluation/runs (metricas.json y por_pregunta.jsonl). El resumen queda en
    ml/evaluation/runs/<fecha>_seleccion_v7.json.

    pwsh -File ops/etapa3_seleccion.ps1
#>
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$repo = Split-Path $PSScriptRoot -Parent
$env:PYTHONIOENCODING = 'utf-8'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $repo 'non_local\non_venv'
$troceados = [ordered]@{
    V0  = @{ firma = '6223e6d20ce3'; fragmentos = 21807 }
    V3  = @{ firma = 'db7e71e57aec'; fragmentos = 21807 }
    V5  = @{ firma = 'c33f24be94bd'; fragmentos = 56155 }
    V6b = @{ firma = 'd0b351aecc40'; fragmentos = 22239 }
    V1b = @{ firma = 'd8a73b61c2fc'; fragmentos = 18988 }
}

function Medir([string]$Firma, [string]$Particion, $Mmr, [string]$Encabezado) {
    $a = @('run', '--no-sync', 'python', '-m', 'interfaces.jobs.evaluate', 'recuperacion-juzgada', '--ranking', 'idf', '--firma', $Firma,
           '--particion', $Particion, '--encabezado-lexico', $Encabezado)
    if ($Mmr) { $a += @('--mmr', "$Mmr") }
    $salida = uv @a 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE) { throw "falló la medición ($Firma, $Particion): $(($salida | Select-Object -Last 3) -join ' ')" }
    $run = Get-ChildItem (Join-Path $repo 'ml\evaluation\runs') -Directory -Filter '*_recuperacion_juzgada' | Sort-Object LastWriteTime | Select-Object -Last 1
    $m = Get-Content (Join-Path $run.FullName 'metricas.json') -Raw | ConvertFrom-Json
    $h = $m.'idf/hibrido'
    [pscustomobject]@{ mrr = $h.'mrr@10'; util10 = $h.'util@10'; util1 = $h.'util@1'; util5 = $h.'util@5'; ndcg = $h.'ndcg@10'
                       mh = $h.por_tipo.varios_saltos.'util@10'; run = $run.Name }
}

Push-Location (Join-Path $repo 'backend')
try {
    $filas = foreach ($v in $troceados.Keys) {
        foreach ($mmr in @($null, 0.85)) {
            foreach ($enc in @('con', 'peso')) {
                $r = Medir $troceados[$v].firma 'desarrollo' $mmr $enc
                $nombre = "$v$(if ($mmr) { ' + MMR' })$(if ($enc -eq 'peso') { ' + V3b' })"
                Write-Host ("{0,-18} MRR {1:N3}  util@10 {2:N3}  util@1 {3:N3}" -f $nombre, $r.mrr, $r.util10, $r.util1)
                [pscustomobject]@{ config = $nombre; troceado = $v; firma = $troceados[$v].firma; mmr = $mmr; encabezado = $enc
                                   fragmentos = $troceados[$v].fragmentos; mrr = $r.mrr; util10 = $r.util10; util1 = $r.util1
                                   util5 = $r.util5; ndcg = $r.ndcg; mh = $r.mh; run = $r.run }
            }
        }
    }
    # la regla: MRR@10; a menos de 0,01 del mejor, utilidad@10; luego menos fragmentos
    $mejorMrr = ($filas | Measure-Object mrr -Maximum).Maximum
    $empate = @($filas | Where-Object { $mejorMrr - $_.mrr -lt 0.01 })
    $ganadora = $empate | Sort-Object @{ Expression = 'util10'; Descending = $true }, @{ Expression = 'fragmentos'; Descending = $false }, @{ Expression = 'mrr'; Descending = $true } | Select-Object -First 1
    Write-Host "`nEmpatadas a menos de 0,01 del mejor MRR ($mejorMrr): $(($empate | ForEach-Object config) -join ', ')"
    Write-Host "Ganadora (V7): $($ganadora.config)"
    # prueba: la ganadora y V0 tal cual
    $pruebaV7 = Medir $ganadora.firma 'prueba' $ganadora.mmr $ganadora.encabezado
    $pruebaV0 = Medir $troceados.V0.firma 'prueba' $null 'con'
    Write-Host ("`nPrueba · V7 ({0}): MRR {1:N3} util@10 {2:N3} util@1 {3:N3} · V0: MRR {4:N3} util@10 {5:N3} util@1 {6:N3}" -f
        $ganadora.config, $pruebaV7.mrr, $pruebaV7.util10, $pruebaV7.util1, $pruebaV0.mrr, $pruebaV0.util10, $pruebaV0.util1)
    $resumen = [ordered]@{ fecha = (Get-Date).ToString('s'); regla = 'MRR@10; a menos de 0,01 del mejor, utilidad@10; luego menos fragmentos'
                           desarrollo = $filas; ganadora = $ganadora.config; prueba = [ordered]@{ V7 = $pruebaV7; V0 = $pruebaV0 } }
    $archivo = Join-Path $repo "ml\evaluation\runs\$(Get-Date -Format 'yyyy-MM-dd_HHmm')_seleccion_v7.json"
    $resumen | ConvertTo-Json -Depth 5 | Set-Content $archivo -Encoding utf8
    Write-Host "Resumen: $archivo"
} finally { Pop-Location }
