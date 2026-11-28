<#
.SYNOPSIS
    Etapa 3: indexa, codifica, juzga y mide cada variante de troceado, una tras otra, sin intervención (para dejarlo
    corriendo de noche). Por variante:
      1. corpus indexar --diferido con sus opciones (≈ 10 min, en esta PC)        -> su firma
      2. vectores.ps1 -Firma (codificación en el equipo con GPU, ≈ 40 min)
      3. evaluate juicios-s2 --firma (el juez califica solo los fragmentos nuevos del pool; el resto hereda)
      4. evaluate recuperacion-juzgada --firma --ranking idf
    Mantiene despiertas esta PC (pedido de energía de Windows) y el equipo con GPU (make despierto) mientras corre. Si una
    variante falla, se anota y sigue con la siguiente. Todo queda en non_local/non_data/work/troceado/<fecha>/.

    pwsh -File ops/troceado_variantes.ps1                       # todas, en el orden de abajo
    pwsh -File ops/troceado_variantes.ps1 -Variantes V2,V3      # solo esas
#>
param([string[]]$Variantes = @('V0', 'V1a', 'V2', 'V3', 'V6', 'V5', 'V1b'))
$Variantes = @($Variantes -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })   # con -File llega «V1a,V2» como un solo texto
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$repo = Split-Path $PSScriptRoot -Parent
$gpu = $env:TP_GPU_DIR   # carpeta compartida con el equipo de la GPU
$env:UV_PROJECT_ENVIRONMENT = "$repo\non_local\non_venv"
$env:PYTHONIOENCODING = 'utf-8'

# variante = nombre y opciones de «corpus indexar» (V0 es la actual: solo se mide). V4 se midió aparte (peso en la fusión).
$definicion = [ordered]@{
    V0  = @{ nombre = 'base: estructural 480, encabezado completo'; opciones = $null }
    V1a = @{ nombre = 'tamaño 256'; opciones = @('--max-tokens', '256'); kw = @('max_tokens=256') }
    V2  = @{ nombre = 'unir secciones de menos de 120 tokens'; opciones = @('--unir-secciones', '120'); kw = @('merge_section_tokens=120') }
    V3  = @{ nombre = 'encabezado corto'; opciones = @('--encabezado', 'corto'); kw = @('header=short') }
    V6  = @{ nombre = 'tablas grandes por filas'; opciones = @('--tablas-por-filas'); kw = @('table_rows=true') }
    V5  = @{ nombre = 'pequeño a grande (parent_child, hijos de 160)'; opciones = @('--chunker', 'parent_child'); kw = @('chunker=parent_child') }
    V1b = @{ nombre = 'tamaño 768'; opciones = @('--max-tokens', '768'); kw = @('max_tokens=768') }
}

$dir = Join-Path $repo ("non_local\non_data\work\troceado\" + (Get-Date -Format 'yyyy-MM-dd_HHmm'))
New-Item -ItemType Directory -Force $dir | Out-Null
$log = Join-Path $dir 'registro.log'
function Anotar([string]$t) { $l = "$(Get-Date -Format 'HH:mm:ss')  $t"; Add-Content $log $l -Encoding utf8; $l }

# esta PC despierta mientras corre (la pantalla puede apagarse)
Add-Type -Namespace T -Name Energia -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
[void][T.Energia]::SetThreadExecutionState([uint32]2147483649)   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

$resultados = @()
Push-Location "$repo\backend"
try {
    Anotar "inicio · variantes: $($Variantes -join ', ') · carpeta $dir"
    # un «despierto» anterior con límite de horas no se reemplaza solo: se quita y se pone uno sin límite
    make -s -C $gpu normal 2>&1 | Out-Null; Start-Sleep 30
    Anotar ('equipo con GPU: ' + ((make -s -C $gpu despierto 2>&1 | Select-Object -Last 1) -join ''))
    foreach ($v in $Variantes) {
        $d = $definicion[$v]
        if (-not $d) { Anotar "$v · no existe, se salta"; continue }
        $t0 = Get-Date
        try {
            Anotar "== $v · $($d.nombre)"
            $firma = '6223e6d20ce3'
            if ($d.opciones) {
                # si la firma ya tiene fragmentos (corrida anterior cortada), no se vuelve a indexar
                $ya = (uv run python "$repo\ops\firma_variante.py" @($d.kw) 2>$null | Select-Object -Last 1) -split ' '
                if ($ya.Count -eq 2 -and [int]$ya[1] -gt 0) { $firma = $ya[0]; Anotar "$v · ya indexado: firma $firma · $($ya[1]) fragmentos (se salta indexar)" }
                else {
                    $salida = uv run python -m interfaces.jobs.corpus indexar --diferido @($d.opciones) 2>&1 | ForEach-Object { "$_" }
                    $salida | Set-Content (Join-Path $dir "$v-indexar.log") -Encoding utf8
                    $json = ($salida -join "`n") -replace '(?s)^.*?(\{\s*"firma".*\}).*$', '$1' | ConvertFrom-Json
                    $firma = $json.firma
                    Anotar "$v · indexado: firma $firma · $($json.documentos) documentos · $($json.fragmentos) fragmentos · $([math]::Round($json.segundos / 60, 1)) min"
                }
                $vec = pwsh -NoProfile -File "$gpu\vectores.ps1" -Firma $firma 2>&1 | ForEach-Object { "$_" }
                $vec | Set-Content (Join-Path $dir "$v-vectores.log") -Encoding utf8
                if ($LASTEXITCODE) { throw "vectores.ps1 falló (código $LASTEXITCODE): $(($vec | Select-Object -Last 1) -join '')" }
                Anotar "$v · vectores: $(($vec | Select-Object -Last 1) -join '')"
                $jui = uv run python -m interfaces.jobs.evaluate juicios-s2 --firma $firma 2>&1 | ForEach-Object { "$_" }
                $jui | Set-Content (Join-Path $dir "$v-juicios.log") -Encoding utf8
                Anotar "$v · juicios: $(($jui | Select-Object -Last 1) -join '')"
            }
            $med = uv run python -m interfaces.jobs.evaluate recuperacion-juzgada --firma $firma --ranking idf 2>&1 | ForEach-Object { "$_" }
            $med | Set-Content (Join-Path $dir "$v-medicion.log") -Encoding utf8
            $hib = $med | Where-Object { $_ -match '^idf/hibrido' } | Select-Object -First 1
            Anotar "$v · $hib"
            $resultados += [pscustomobject]@{ variante = $v; nombre = $d.nombre; firma = $firma; hibrido = $hib; minutos = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1); error = $null }
        } catch {
            Anotar "$v · FALLÓ: $($_.Exception.Message)"
            $resultados += [pscustomobject]@{ variante = $v; nombre = $d.nombre; firma = $null; hibrido = $null; minutos = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1); error = $_.Exception.Message }
        }
        $resultados | ConvertTo-Json | Set-Content (Join-Path $dir 'resultados.json') -Encoding utf8
    }
} finally {
    Pop-Location
    Anotar ('equipo con GPU: ' + ((make -s -C $gpu normal 2>&1 | Select-Object -Last 1) -join ''))
    [void][T.Energia]::SetThreadExecutionState([uint32]2147483648)
    Anotar 'fin'
}
