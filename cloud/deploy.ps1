#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$AksName,
    [Parameter(Mandatory)][ValidatePattern('^[a-zA-Z0-9]+$')][string]$RegistryName,
    [Parameter(Mandatory)][string]$PostgresHost,
    [Parameter(Mandatory)][string]$PostgresDatabase,
    [Parameter(Mandatory)][System.Management.Automation.PSCredential]$PostgresCredential,
    [Parameter(Mandatory)][string]$OptionsFile,
    [Parameter(Mandatory)][ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$')][string]$ImageTag,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step selhal (exit $LASTEXITCODE)." }
}
foreach ($command in @('az', 'kubectl')) { Get-Command $command -ErrorAction Stop | Out-Null }
$repoRoot = Split-Path $PSScriptRoot -Parent
$optionsPath = (Resolve-Path $OptionsFile).Path
$options = Get-Content -Raw $optionsPath | ConvertFrom-Json
if ($null -eq $options.latitude -or $null -eq $options.longitude) { throw 'Chybí latitude/longitude.' }
if (-not $PostgresHost.EndsWith('.postgres.database.azure.com')) { throw 'Použij FQDN Azure PostgreSQL serveru.' }
az account set --subscription $SubscriptionId
Assert-Exit 'Výběr předplatného'
$loginServer = az acr show --name $RegistryName --query loginServer -o tsv
Assert-Exit 'Kontrola ACR'
$image = "$loginServer/astro-weather:$ImageTag"
Push-Location $repoRoot
try {
    if (-not $SkipBuild) {
        az acr build --registry $RegistryName --image "astro-weather:$ImageTag" --file cloud/Dockerfile .
        Assert-Exit 'Sestavení image'
    }
    # Kubeconfig je izolovaný pro toto nasazení; nemění aktivní lokální cluster.
    $kubeConfig = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString() + '.kubeconfig')
    try {
        az aks get-credentials --resource-group $ResourceGroup --name $AksName --file $kubeConfig
        Assert-Exit 'Připojení AKS'
        kubectl --kubeconfig $kubeConfig apply -f cloud/k8s/namespace.yaml
        Assert-Exit 'Namespace'
        $config = kubectl --kubeconfig $kubeConfig -n astro-weather create configmap astro-options "--from-file=options.json=$optionsPath" --dry-run=client -o json
        Assert-Exit 'Příprava konfigurace'
        $config | kubectl --kubeconfig $kubeConfig apply -f -
        Assert-Exit 'Konfigurace'
        # Heslo se předává přes stdin; není v argumentech procesu ani v souboru.
        $secret = @{
            apiVersion='v1'; kind='Secret'; type='Opaque'
            metadata=@{name='astro-postgres'; namespace='astro-weather'}
            stringData=@{
                PGHOST=$PostgresHost; PGPORT='5432'; PGDATABASE=$PostgresDatabase
                PGUSER=$PostgresCredential.UserName
                PGPASSWORD=$PostgresCredential.GetNetworkCredential().Password
                PGSSLMODE='verify-full'; PGSSLROOTCERT='/etc/ssl/certs/ca-certificates.crt'
            }
        }
        $secret | ConvertTo-Json -Depth 5 -Compress | kubectl --kubeconfig $kubeConfig apply --server-side --field-manager=astro-deploy -f -
        Assert-Exit 'Databázový secret'
        $secret.stringData.PGPASSWORD = $null
        $manifest = kubectl kustomize cloud/k8s
        Assert-Exit 'Sestavení Kubernetes manifestu'
        ($manifest -join "`n").Replace('astro-weather:local', $image) | kubectl --kubeconfig $kubeConfig apply -f -
        Assert-Exit 'Nasazení'
        # Promítne i změny konfigurace/secretu při použití stejného tagu.
        kubectl --kubeconfig $kubeConfig -n astro-weather rollout restart deployment/astro-weather
        Assert-Exit 'Restart konfigurace'
        kubectl --kubeconfig $kubeConfig -n astro-weather rollout status deployment/astro-weather --timeout=600s
        Assert-Exit 'Ověření nasazení'
        Write-Host 'Nasazeno. Pro otevření webu použij postup port-forward v cloud/README.md.'
    } finally {
        if (Test-Path $kubeConfig) { Remove-Item $kubeConfig -Force }
    }
} finally { Pop-Location }
