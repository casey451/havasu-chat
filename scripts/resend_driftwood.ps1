# resend_driftwood.ps1 — post the 2 Driftwood findings from the 2026-06-04 gather run
# (PowerShell 5.1 compatible; reads INGEST_API_TOKEN from .env, never prints it)
$ErrorActionPreference = "Stop"
$base = "https://havasu-chat-production.up.railway.app"

$line = (Get-Content .env | Where-Object { $_ -match '^INGEST_API_TOKEN=' } | Select-Object -First 1)
if (-not $line) { Write-Host "FAIL: no INGEST_API_TOKEN in .env"; exit 1 }
$tok = $line.Split('=',2)[1].Trim().Trim('"').Trim("'")

$loc = "Driftwood Acres Equine Center, 1807 Aztec Rd"
$payloads = @(
    @{
        entity_type = "program"; submission_name = "Driftwood Acres Equine Center"
        source_url = "https://www.driftwoodacresequinecenter.com/booking-calendar/riding-lessons"
        confidence = 0.65; target_entity_id = "be9e1db7-ad99-41df-886c-be153f5f6831"
        proposed_record = @{
            title = "Group Riding Lessons"
            description = "Group horseback riding lessons for all levels with two bookable 90-minute morning sessions on weekdays: 7:00-8:30am and 8:30-10:00am (MST), per the live Wix booking calendar (June 2026; some sessions sell out). `$40 per lesson; monthly/quarterly packages available. Recurrence inferred from one observed month of booking slots."
            schedule_days = @("monday","tuesday","wednesday","thursday","friday")
            schedule_start_time = "07:00"; schedule_end_time = "10:00"
            location_name = $loc; provider_name = "Driftwood Acres Equine Center"
            cost = "`$40 per 90-min lesson"
        }
    },
    @{
        entity_type = "program"; submission_name = "Driftwood Acres Equine Center"
        source_url = "https://www.driftwoodacresequinecenter.com/booking-calendar/roping-group"
        confidence = 0.70; target_entity_id = "be9e1db7-ad99-41df-886c-be153f5f6831"
        proposed_record = @{
            title = "Roping Group"
            description = "Group roping session, 90 minutes, Tuesdays and Thursdays at 3:30pm (MST) per the live booking calendar (consistent across June 2026). `$40 per session. Held at the new location, 1807 Aztec Rd."
            schedule_days = @("tuesday","thursday")
            schedule_start_time = "15:30"; schedule_end_time = "17:00"
            location_name = $loc; provider_name = "Driftwood Acres Equine Center"
            cost = "`$40 per session"
        }
    }
)

foreach ($p in $payloads) {
    $body = $p | ConvertTo-Json -Depth 6
    try {
        $r = Invoke-RestMethod -Uri "$base/api/ingest/contribution" -Method POST `
            -Headers @{ Authorization = "Bearer $tok" } -ContentType "application/json" -Body $body
        Write-Host ("{0,-22} -> {1}  id={2}" -f $p.proposed_record.title, $r.status, $r.id)
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        Write-Host ("{0,-22} -> FAILED HTTP {1}: {2}" -f $p.proposed_record.title, $code, $_.ErrorDetails.Message)
    }
}
