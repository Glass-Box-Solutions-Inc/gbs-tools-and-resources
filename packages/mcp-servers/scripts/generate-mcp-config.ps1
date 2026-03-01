# Generate .mcp.json from template + environment variables
# Usage: .\scripts\generate-mcp-config.ps1 -OutputPath "C:\path\to\project\.mcp.json"

param(
    [string]$OutputPath = ".mcp.json",
    [string]$TemplatePath = "$PSScriptRoot\..\\.mcp.json.template",
    [string]$McpServersDir = "$PSScriptRoot\.."
)

$template = Get-Content $TemplatePath -Raw

# Replace ${VARIABLE} patterns with environment variable values
$result = [regex]::Replace($template, '\$\{(\w+)\}', {
    param($match)
    $varName = $match.Groups[1].Value
    $value = [Environment]::GetEnvironmentVariable($varName)
    if ($varName -eq "MCP_SERVERS_DIR") {
        return (Resolve-Path $McpServersDir).Path -replace '\\', '/'
    }
    if ($value) { return $value }
    Write-Warning "Environment variable $varName not set - using placeholder"
    return $match.Value
})

$result | Set-Content $OutputPath -Encoding UTF8
Write-Host "Generated $OutputPath from template"
Write-Host "Variables not replaced will show as `${VARIABLE}` - set them as environment variables"
