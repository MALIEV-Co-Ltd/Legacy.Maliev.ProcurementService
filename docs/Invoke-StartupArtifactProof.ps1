[CmdletBinding()]
param([string]$Image = 'legacy-procurement-startup-acceptance:20260930')

$ErrorActionPreference = 'Stop'
function Invoke-DockerChecked {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw 'Docker acceptance command failed.' }
}
function ConvertTo-Base64Url([byte[]]$Value) {
    [Convert]::ToBase64String($Value).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

# Unique ephemeral names; no bind mounts, persistent volumes, external databases or deployment.
$suffix = [Guid]::NewGuid().ToString('N')
$network = "procurement-proof-$suffix"
$supplier = "supplier-$suffix"
$order = "order-$suffix"
$api = "api-$suffix"
$rsa = [Security.Cryptography.RSA]::Create(2048)
$previousPublicKey = $env:Jwt__PublicKey
try {
    $env:Jwt__PublicKey = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($rsa.ExportSubjectPublicKeyInfoPem()))
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $header = ConvertTo-Base64Url ([Text.Encoding]::UTF8.GetBytes('{"alg":"RS256","typ":"JWT"}'))
    $payload = ConvertTo-Base64Url ([Text.Encoding]::UTF8.GetBytes((@{
        sub = 'employee:acceptance'; iss = 'https://iam.maliev.com'; aud = 'maliev-services'; nbf = $now - 60; exp = $now + 300
        permission = @('legacy-procurement.suppliers.read', 'legacy-procurement.purchase-orders.read')
    } | ConvertTo-Json -Compress)))
    $unsigned = "$header.$payload"
    $signature = ConvertTo-Base64Url ($rsa.SignData([Text.Encoding]::UTF8.GetBytes($unsigned),
        [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1))
    $token = "$unsigned.$signature"
    Invoke-DockerChecked network create $network
    Invoke-DockerChecked run --rm -d --name $supplier --network $network -e POSTGRES_PASSWORD=test-only-acceptance -e POSTGRES_DB=supplier postgres:18-alpine
    Invoke-DockerChecked run --rm -d --name $order --network $network -e POSTGRES_PASSWORD=test-only-acceptance -e POSTGRES_DB=purchaseorder postgres:18-alpine
    # Connection strings are fixture-only and passed at runtime, never persisted or printed.
    Invoke-DockerChecked run --rm -d --name $api --network $network -p 127.0.0.1::8080 -e Jwt__PublicKey `
        -e ASPNETCORE_ENVIRONMENT=Production -e Cache__RedisEnabled=false -e Logging__LogLevel__Default=Information `
        -e "ConnectionStrings__SupplierDbContext=Host=$supplier;Database=supplier;Username=postgres;Password=test-only-acceptance" `
        -e "ConnectionStrings__PurchaseOrderDbContext=Host=$order;Database=purchaseorder;Username=postgres;Password=test-only-acceptance" $Image
    $binding = Invoke-DockerChecked port $api 8080
    $baseUrl = "http://$binding"
    $live = $null
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try { $live = Invoke-WebRequest "$baseUrl/procurement/liveness" -TimeoutSec 2; break } catch { Start-Sleep -Milliseconds 500 }
    }
    if ($live.StatusCode -ne 200) { throw 'Liveness failed.' }
    foreach ($database in $supplier, $order) {
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            & docker exec $database pg_isready -U postgres *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Milliseconds 500
        }
        if ($LASTEXITCODE -ne 0) { throw 'Disposable PostgreSQL readiness failed.' }
    }
    $incidents = @()
    foreach ($path in 'Suppliers/81927', 'PurchaseOrders/81927') {
        $anonymous = Invoke-WebRequest "$baseUrl/$path" -SkipHttpErrorCheck
        if ($anonymous.StatusCode -ne 401) { throw 'Anonymous boundary failed.' }
        $response = Invoke-WebRequest "$baseUrl/$path" -Headers @{ Authorization = "Bearer $token" } -SkipHttpErrorCheck
        $body = $response.Content | ConvertFrom-Json
        if ($response.StatusCode -ne 500 -or $body.details -ne $null -or -not $body.traceId) { throw 'Safe failure boundary failed.' }
        $incidents += $body.traceId
    }
    $logs = & docker logs $api 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Container logs unavailable.' }
    $events = @($logs | ForEach-Object { try { $_ | ConvertFrom-Json -ErrorAction Stop } catch {} } |
        Where-Object { $_.State.EventName -eq 'UnhandledRequestFailure' })
    if ($events.Count -ne 2 -or @($events | Where-Object { $_.severity -ne 'CRITICAL' -or $_.State.IncidentId -notin $incidents }).Count) {
        throw 'Critical incident event mismatch.'
    }
    if ($logs -match '42P01|does not exist|Npgsql.Internal|81927|test-only-acceptance' -or ($logs | Select-String -SimpleMatch $token)) {
        throw 'Protected provider/request information appeared in logs; values withheld.'
    }
    $files = Invoke-DockerChecked exec $api sh -c 'ls /app'
    if ($files -match 'NLog|NativeLogging|LoggerService') { throw 'Legacy logging dependency present.' }
    Invoke-DockerChecked exec $api test -f /app/Legacy.Maliev.ProcurementService.Api.xml
    $user = Invoke-DockerChecked inspect $api --format '{{.Config.User}}'
    if ($user -eq '0' -or [string]::IsNullOrWhiteSpace($user)) { throw 'Container runs as root.' }
    Write-Output "PASS: non-root UID $user; liveness200; both routes anonymous401/authenticated500; safe matching CRITICAL incidents; native/XML artifacts."
} finally {
    $rsa.Dispose()
    $env:Jwt__PublicKey = $previousPublicKey
    & docker rm -f $api $supplier $order 2>$null | Out-Null
    & docker network rm $network 2>$null | Out-Null
}
