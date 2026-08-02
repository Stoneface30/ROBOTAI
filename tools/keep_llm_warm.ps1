# Keeps the voice LLM resident in VRAM so questions answer fast.
# The HA-side keep-warm automation proved unreliable (single-mode runs got
# stuck behind slow cold-start calls and stopped re-firing), so warming is
# done here, locally, against Ollama directly.
$body = '{"model":"qwen2.5:7b","prompt":"ok","stream":false,"keep_alive":3600}'
try {
    Invoke-RestMethod -Uri 'http://localhost:11434/api/generate' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 180 | Out-Null
    Write-Output "$(Get-Date -Format s) warmed"
} catch {
    Write-Output "$(Get-Date -Format s) failed: $($_.Exception.Message)"
}
